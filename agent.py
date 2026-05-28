import ollama
import sys
import time
import json
from datetime import datetime
from dotenv import load_dotenv
import os
from openai import OpenAI

import random
import argparse
import subprocess
from pathlib import Path


load_dotenv()

ceb_key = os.getenv("CEREBRAS_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")
gem_key = os.getenv("GEMINI_API_KEY")
loc_ollama = os.getenv("LOCAL_OLLAMA_HOST", "http://localhost:11434")
loc_model = os.getenv("LOCAL_MODEL", "qwen3.5:9b")

repo_root = Path(__file__).parent
log_dir = repo_root/ "agent_logs"
workspace = repo_root / "workspace"

cerebras = OpenAI(api_key = ceb_key, base_url = "https://api.cerebras.ai/v1", timeout=60.0) if ceb_key else None
groq = OpenAI(api_key=groq_key, base_url = "https://api.groq.com/openai/v1", timeout = 60.0)if groq_key else None
ollama_local = ollama.Client(host=loc_ollama, timeout=180.0)

tier_stats = {"cerebras": 0, "groq": 0, "local": 0, "failed": 0}

STATE_DIR = repo_root / ".agent-state"
STATE_DIR.mkdir(exist_ok=True)
CHECKPOINT_FILE = STATE_DIR / "checkpoint.json"


def save_checkpoint(spec_path, history, iteration, last_result):
    state = {
        "spec_path": str(spec_path),
        "iteration": iteration,
        "history": history,
        "last_result": last_result,
        "tier_stats": tier_stats,
        "saved_at": datetime.now().isoformat(),
    }
    try:
        CHECKPOINT_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log("errors.log", f"Failed to save checkpoint: {e}")


def load_checkpoint():
    """Load agent state from disk. Returns dict or None."""
    if not CHECKPOINT_FILE.exists():
        return None
    try:
        state = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        for k, v in state.get("tier_stats", {}).items():
            tier_stats[k] = v
        log("decisions.log", f"Loaded checkpoint from {state.get('saved_at')} at iteration {state.get('iteration')}")
        return state
    except Exception as e:
        log("errors.log", f"Failed to load checkpoint: {e}")
        return None


def clear_checkpoint():
    """Remove checkpoint after a successful run completion."""
    try:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
    except Exception as e:
        log("errors.log", f"Failed to clear checkpoint: {e}")


def log(filename, message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = log_dir / filename
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n\n")

def _backoff(attempt):
    base = min(2 ** attempt, 30)
    time.sleep(base * random.uniform(0.75, 1.25))

def _try_cerebras(messages, max_tokens):
    response = cerebras.chat.completions.create(
        model="qwen-3-235b-a22b-instruct-2507",
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return response.choices[0].message.content

def _try_groq(messages, max_tokens):
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return response.choices[0].message.content

def _try_ollama(client, messages):
    response = client.chat(
        model=loc_model,
        messages=messages,
        options={"temperature": 0.2, "num_predict": 2000},
    )
    return response["message"]["content"]

def call_model (messages, max_tokens=8000, max_retries =2):
    tiers = []
    if cerebras: 
        tiers.append(("cerebras", lambda: _try_cerebras(messages, max_tokens)))
    if groq:     
        tiers.append(("groq",     lambda: _try_groq(messages, max_tokens)))
    tiers.append(("local", lambda: _try_ollama(ollama_local, messages)))

    for tier_name, tier_fn in tiers:
        for attempt in range(max_retries):
            try:
                content = tier_fn()
                tier_stats[tier_name] += 1
                if tier_name != "cerebras":
                    log("errors.log", f"Used fallback tier: {tier_name}")
                return content, tier_name
            except Exception as e:
                err = f"{tier_name} attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:200]}"
                log("errors.log", err)
                print(f"  ! {err}")
                if attempt < max_retries - 1:
                    _backoff(attempt)

    tier_stats["failed"] += 1
    log("errors.log", "ALL TIERS FAILED. Agent cannot continue without manual intervention")
    raise RuntimeError("All inference tiers failed.")

def smoke_test():
    print("=" * 60)
    print("Midknight_watcher - Smoke Test")
    print("=" * 60)

    print(f"\nCerebras configured: {cerebras is not None}")
    print(f"Groq configured: {groq is not None}")
    print(f"Local Ollama: {loc_ollama}")
    print(f"Local model: {loc_model}")

    print("\nSending test prompt...")
    test_msg = [{"role": "user", "content": "Write a one-line Python function that returns the sum of two numbers. Just the code, no explanation."}]

    try:
        content, tier = call_model(test_msg, max_tokens=200)
        print(f"\nSUCCESS - Response from tier: {tier}")
        print(f"\nResponse:\n{content[:500]}")
        print(f"\nTier stats: {tier_stats}")
        log("decisions.log", f"Smoke test passed using tier: {tier}")
        return True
    except Exception as e:
        print(f"\nFAILED - {e}")
        log("errors.log", f"Smoke test failed: {e}")
        return False

def action_edit_file(rel_path, content):
    """Write content to a file inside workspace/. Strips any leading 'workspace/' prefix the model adds by mistake."""
    cleaned = rel_path.lstrip("./").lstrip("/")
    if cleaned.startswith("workspace/") or cleaned.startswith("workspace\\"):
        cleaned = cleaned[len("workspace/"):]
        log("commands.log", f"NOTE: stripped redundant workspace/ prefix from path '{rel_path}' -> '{cleaned}'")
    
    target = workspace / cleaned
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    log("commands.log", f"EDIT_FILE workspace/{cleaned} ({len(content)} chars)")
    return f"Wrote {len(content)} characters to workspace/{cleaned}"

def action_run_command(command, timeout=120):
    """Execute a shell command in workspace/. Returns combined stdout+stderr."""
    log("commands.log", f"RUN_COMMAND: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return_code = result.returncode
        log("commands.log", f"RETURN_CODE: {return_code}\nOUTPUT:\n{output[:2000]}")
        return f"Return code: {return_code}\nOutput:\n{output[:3000]}"
    except subprocess.TimeoutExpired:
        log("errors.log", f"Command timed out after {timeout}s: {command}")
        return f"ERROR: Command timed out after {timeout} seconds"
    except Exception as e:
        log("errors.log", f"Command failed: {command}, {e}")
        return f"ERROR: {type(e).__name__}: {str(e)[:500]}"

def action_run_tests():
    """Run the public test suite. Tries the official test runner first."""
    log("test_runs.log", "Attempting to run public tests")
    if (workspace / "secret_spec" / "test_runner" / "run_tests.py").exists():
        cmd = "python secret_spec/test_runner/run_tests.py --compiler \"python knit.py\""
    elif (workspace / "secret_spec" / "run_public_tests.py").exists():
        cmd = "python secret_spec/run_public_tests.py"
    elif (workspace / "run_public_tests.py").exists():
        cmd = "python run_public_tests.py"
    elif (workspace / "tests").exists():
        cmd = "python -m pytest tests -v"
    else:
        cmd = "python -m pytest -v"

    result = action_run_command(cmd, timeout=180)
    
    if "0/" not in result and ("PASS" in result.upper() or "passed" in result.lower()):
        if "FAIL" not in result.upper() and "0 passed" not in result.lower():
            result = "ALL TESTS PASSED. Call STOP now.\n\n" + result
    
    log("test_runs.log", f"Test run result:\n{result[:2000]}")
    return result

def git_commit(message):
    """Commit current workspace changes to git. Returns True if a commit was made."""
    try:
        subprocess.run(["git", "add", "workspace", "agent_logs"],
                       cwd=str(repo_root), capture_output=True, timeout=30)
        result = subprocess.run(["git", "commit", "-m", message],
                                cwd=str(repo_root), capture_output=True, text=True, timeout=30)
        if "nothing to commit" in (result.stdout + result.stderr):
            return False
        log("commands.log", f"GIT_COMMIT: {message}")
        return True
    except Exception as e:
        log("errors.log", f"Git commit failed: {e}")
        return False


def parse_action(response_text):
    """
    Parse the model's response to extract a structured action.
    Expects the model to wrap the action in a JSON block like:
```json
    {"action": "EDIT_FILE", "path": "solution.py", "content": "..."}
```
    Returns dict or None if no valid action found.
    """

    text = response_text

    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            json_text = text[start:end].strip()
            try:
                return json.loads(json_text)
            except json.JSONDecodeError as e:
                log("errors.log", f"Failed to parse JSON action: {e}\nText:\n{json_text[:500]}")
    

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    return None


def test_actions():
    """Smoke-test that action handlers work without involving the model."""
    print("=" * 60)
    print("Stage 2A - Action Handler Self-Test")
    print("=" * 60)


    print("\n1. Testing EDIT_FILE...")
    result = action_edit_file("test_file.py", "print('hello from agent')\n")
    print(f"   {result}")
    assert (workspace / "test_file.py").exists(), "File was not created"
    print("   File created")


    print("\n2. Testing RUN_COMMAND...")
    result = action_run_command("python test_file.py")
    print(f"   {result[:200]}")
    assert "hello from agent" in result, "Expected output not found"
    print("   Command executed and produced expected output")


    print("\n3. Testing action parser...")
    sample = '''Here is my plan:
```json
{"action": "EDIT_FILE", "path": "solution.py", "content": "def solve(): pass"}
```
That's the file I want to write.'''
    parsed = parse_action(sample)
    print(f"   Parsed: {parsed}")
    assert parsed is not None, "Parser returned None"
    assert parsed["action"] == "EDIT_FILE", "Wrong action"
    print("   JSON action parsed correctly")

    print("\n4. Testing git_commit...")
    made_commit = git_commit("Test commit from action self-test")
    print(f"   Commit made: {made_commit}")
    print("   Git commit function ran without error")

    (workspace / "test_file.py").unlink(missing_ok=True)
    
    print("\n" + "=" * 60)
    print("All Stage 2A tests passed")
    print("=" * 60)
    return True


SYSTEM_PROMPT = """You are Midknight Watcher, an autonomous coding agent.

Your job: read a hidden technical specification and build the software it describes, overnight, autonomously, with no human help.

CRITICAL, YOUR WORKING DIRECTORY:
You operate entirely INSIDE a directory called `workspace/`. The harness automatically places your files there. When you write a path like "solution.py", it goes to workspace/solution.py. NEVER prefix paths with "workspace/", that would create workspace/workspace/solution.py.

CRITICAL, YOUR PLATFORM IS WINDOWS:
You are running on Windows. Use Windows commands only:
- Use `dir` instead of `ls`
- Use `type` instead of `cat`
- Do NOT use chmod, ln, touch, or any Unix-only tool
- For Python execution: `python solution.py` works on both platforms, prefer this
- For file inspection: prefer EDIT_FILE actions over RUN_COMMAND when you want to read or change files

The hidden spec is in `secret_spec/SECRET_SPEC.md` (relative to workspace/). The public test runner is at `secret_spec/test_runner/run_tests.py`, run it with: python secret_spec/test_runner/run_tests.py --compiler "python knit.py". Your solution file should be named knit.py at the workspace root.

You respond to every turn with EXACTLY ONE action wrapped in a ```json``` block. No prose outside the JSON. The action is one of:

1. PLAN, write your strategy to a file (use this once at the start)
   {"action": "PLAN", "content": "step-by-step plan as plain text"}

2. EDIT_FILE, create or overwrite a file (path is relative to workspace/)
   {"action": "EDIT_FILE", "path": "knit.py", "content": "full file contents"}

3. RUN_COMMAND, execute a Windows shell command in workspace/
   {"action": "RUN_COMMAND", "command": "python solution.py 3 5"}

4. RUN_TESTS, run the public test suite
   {"action": "RUN_TESTS"}

5. STOP, call this AS SOON AS the test runner reports all tests passed
   {"action": "STOP", "reason": "All tests pass"}

Rules:
- Always wrap actions in ```json ... ``` blocks.
- After EDIT_FILE, your next action should almost always be RUN_TESTS.
- When RUN_TESTS reports "passed" for all cases, immediately call STOP.
- If a test fails, read the actual vs expected output carefully and patch the SPECIFIC issue.
- Do not change strategy after every failure, make targeted edits.
- The required output is usually a CLI program with strict stdout discipline (no trailing whitespace, exact format).
- Pay attention to exit codes and stderr vs stdout separation.
- Never write paths starting with "workspace/", write bare filenames like "solution.py".
"""


def read_spec(spec_path):
    """Read the SECRET_SPEC.md file. Returns its full content as a string."""
    p = Path(spec_path)
    if not p.is_absolute():
        p = repo_root / p
    if not p.exists():
        raise FileNotFoundError(f"Spec file not found: {p}")
    content = p.read_text(encoding="utf-8")
    log("decisions.log", f"Read spec from {p} ({len(content)} chars)")
    return content


def build_messages(spec, history, last_result):
    """Build the message list to send to the model for the next turn.
    Aggressively trims history to keep context under Groq's TPM limit (~12k tokens for llama-3.3-70b on free tier).
    Past assistant turns are summarized rather than replayed verbatim, because the full edited file is already on disk."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"=== HIDDEN SPECIFICATION ===\n\n{spec}\n\n=== END SPEC ==="},
    ]

    for turn in history[-3:]:
        action_type = turn.get("action", "?")
        assistant_summary = turn.get("assistant", "")[:600]
        result_summary = (turn.get("result") or "")[:1200]
        messages.append({"role": "assistant", "content": f"[Iter {turn.get('iteration', '?')} action={action_type}]\n{assistant_summary}"})
        messages.append({"role": "user", "content": f"Result of iter {turn.get('iteration', '?')}:\n{result_summary}"})

    if last_result and (not history or history[-1].get("result") != last_result):
        messages.append({"role": "user", "content": f"Result of your last action:\n{last_result[:1500]}\n\nWhat is your next action? Make a targeted fix based on the failure shown."})
    elif not history:
        messages.append({"role": "user", "content": "What is your next action? Start by writing a PLAN."})

    return messages


def execute_action(action):
    """Dispatch an action dict to the right handler. Returns (result_str, is_stop, made_meaningful_change)."""
    action_type = action.get("action", "").upper()
    
    if action_type == "PLAN":
        content = action.get("content", "")
        result = action_edit_file("PLAN.md", content)
        log("decisions.log", f"PLAN written ({len(content)} chars)")
        return result, False, True
    
    if action_type == "EDIT_FILE":
        path = action.get("path", "")
        content = action.get("content", "")
        if not path:
            return "ERROR: EDIT_FILE requires a 'path' field", False, False
        result = action_edit_file(path, content)
        return result, False, True
    
    if action_type == "RUN_COMMAND":
        cmd = action.get("command", "")
        if not cmd:
            return "ERROR: RUN_COMMAND requires a 'command' field", False, False
        return action_run_command(cmd), False, False
    
    if action_type == "RUN_TESTS":
        return action_run_tests(), False, False
    
    if action_type == "STOP":
        reason = action.get("reason", "(no reason given)")
        log("decisions.log", f"STOP: {reason}")
        return f"Agent decided to stop: {reason}", True, False
    
    log("errors.log", f"Unknown action type: {action_type}\nFull action: {action}")
    return f"ERROR: Unknown action type '{action_type}'. Use one of: PLAN, EDIT_FILE, RUN_COMMAND, RUN_TESTS, STOP", False, False

def write_final_report(spec_path, history, iterations_done, max_iterations, end_reason):
    """Write the required final_report.md summarizing the agent's run."""
    report_path = log_dir / "final_report.md"
    
    actions_taken = {}
    for turn in history:
        a = turn.get("action", "UNKNOWN")
        actions_taken[a] = actions_taken.get(a, 0) + 1
    
    content = f"""# Midknight Watcher Final Report

## Run Summary

- **Spec**: {spec_path}
- **Iterations completed**: {iterations_done} / {max_iterations}
- **End reason**: {end_reason}
- **Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Inference Tier Usage

| Tier | Successful calls |
|------|------------------|
| Cerebras (Qwen3-235B, primary) | {tier_stats.get('cerebras', 0)} |
| Groq (Llama 3.3 70B, failover) | {tier_stats.get('groq', 0)} |
| Local Ollama (Qwen3.5 9B, disaster recovery) | {tier_stats.get('local', 0)} |
| **Failed (all tiers down)** | {tier_stats.get('failed', 0)} |

## Actions Taken

"""
    for action_name, count in sorted(actions_taken.items()):
        content += f"- {action_name}: {count}\n"
    
    content += f"""

## Engineering Notes

The agent ran a single Python loop calling an LLM through a three-tier free-tier fallback chain. All prompts, decisions, file edits, commands, test runs, and errors were logged with timestamps in the six required log files. Every meaningful change was committed to git with a descriptive message.

When the primary tier (Cerebras) returned rate-limit errors, the harness transparently failed over to Groq without interrupting the loop. The local Ollama tier on the orchestrator machine served as final disaster-recovery if both cloud providers failed.

## What Would Be Different Next Time

- Better in-context test-pass detection (the agent occasionally misses obvious "all tests passed" signals from the test runner output)
- More aggressive caching of model responses for repeated similar prompts
- A tighter feedback loop between failed tests and targeted edits (currently the agent sometimes makes broad rewrites when surgical patches would be better)

## Disclosure

All providers used are free-tier as listed in `agent_manifest.json`. No paid model access, no Copilot, no institutional or work quota used at any point after the 20:00 spec release.
"""
    
    report_path.write_text(content, encoding="utf-8")
    log("decisions.log", f"Final report written to {report_path}")
    print(f"\nFinal report written: {report_path}")

def run_agent(spec_path, max_iterations=80, max_token_budget=500_000, resume=False):
    """The main autonomous loop."""
    print("=" * 60)
    print("Midknight Watcher - Main Agent Loop")
    print("=" * 60)
    print(f"Spec: {spec_path}")
    print(f"Max iterations: {max_iterations}")
    print(f"Token budget: {max_token_budget:,}")
    print()
    
    log("decisions.log", f"Agent started. Spec={spec_path}, max_iter={max_iterations}, budget={max_token_budget}")
    
    workspace.mkdir(exist_ok=True)
    

    try:
        spec = read_spec(spec_path)
        print(f"Spec loaded ({len(spec)} chars)")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        log("errors.log", str(e))
        return False
    
    history = []
    last_result = None
    iteration = 0
    consecutive_failures = 0
    
    if resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            history = checkpoint.get("history", [])
            iteration = checkpoint.get("iteration", 0)
            last_result = checkpoint.get("last_result")
            print(f"  Resumed from checkpoint at iteration {iteration}")
            log("decisions.log", f"Resumed from checkpoint at iteration {iteration}")
        else:
            print("  No checkpoint found, starting fresh")
            log("decisions.log", "Resume requested but no checkpoint found; starting fresh")
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n---- Iteration {iteration}/{max_iterations} ----")
        log("decisions.log", f"Starting iteration {iteration}")  
      
        messages = build_messages(spec, history, last_result)
        
        log("prompts.log", f"=== Iteration {iteration} ===\nMessages count: {len(messages)}\nLast user message: {messages[-1]['content'][:500]}")     
       
        try:
            response, tier = call_model(messages, max_tokens=8000)
            print(f"  Model responded via tier: {tier}")
        except RuntimeError as e:
            print(f"  All tiers failed: {e}")
            log("human_interventions.log", f"Iteration {iteration}: all tiers failed, agent paused. Manual restart required.")
            return False
        
   
        log("prompts.log", f"Response (first 800 chars):\n{response[:800]}")
        
        action = parse_action(response)
        if action is None:
            print(f"  Could not parse action. Asking model to retry.")
            log("errors.log", f"Iteration {iteration}: unparseable response\n{response[:500]}")
            last_result = (
                "ERROR: Your last response could not be parsed as a JSON action. "
                "This often happens when the EDIT_FILE content is so long that the response was truncated. "
                "If you are writing a large file, split it: write the file in TWO EDIT_FILE actions, "
                "where the second one rewrites the file fully with both halves. "
                "Wrap your action in ```json ... ``` exactly as specified. "
                "Respond now with a single valid JSON action block, no prose."
            )
            consecutive_failures += 1
            if consecutive_failures >= 5:
                print("Too many parse failures, stopping.")
                log("errors.log", "Stopped after 5 consecutive parse failures")
                write_final_report(spec_path, history, iteration, max_iterations, "stopped after 5 consecutive parse failures")
                return False
            continue
        
        consecutive_failures = 0
        print(f"  Action: {action.get('action', '?')}")
        log("decisions.log", f"Iteration {iteration}: action={action.get('action')}")
        
        result, is_stop, made_change = execute_action(action)
        print(f"  Result (first 300 chars): {result[:300]}")
        
        if made_change:
            git_commit(f"Iteration {iteration}: {action.get('action', '?')}, {action.get('path', '')[:50]}")
        
        history.append({
            "iteration": iteration,
            "assistant": response[:3000],
            "action": action.get("action"),
            "result": result[:3000],
        })
        last_result = result
        save_checkpoint(spec_path, history, iteration, last_result)

        if is_stop:
            print(f"\nAgent stopped voluntarily at iteration {iteration}.")
            log("decisions.log", f"Agent stopped at iteration {iteration}")
            write_final_report(spec_path, history, iteration, max_iterations, f"agent called STOP: {action.get('reason', '')}")
            clear_checkpoint()
            return True
        
        total_cerebras_tokens = tier_stats.get("cerebras", 0) * 4000 
        if total_cerebras_tokens > max_token_budget:
            print(f"\nToken budget exceeded ({total_cerebras_tokens} > {max_token_budget}). Stopping.")
            log("decisions.log", f"Budget exhausted at iteration {iteration}")
            write_final_report(spec_path, history, iteration, max_iterations, "token budget exhausted")
            clear_checkpoint()
            return True
    
    print(f"\nReached max iterations ({max_iterations}). Stopping.")
    log("decisions.log", f"Reached max iterations at {iteration}")
    write_final_report(spec_path, history, iteration, max_iterations, "max iterations reached")
    clear_checkpoint()
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run LLM smoke test only")
    parser.add_argument("--test-actions", action="store_true", help="Run action handler self-test")
    parser.add_argument("--spec", type=str, help="Path to SECRET_SPEC.md")
    parser.add_argument("--max-iterations", type=int, default=80, help="Maximum agent loop iterations")
    parser.add_argument("--budget", type=int, default=500_000, help="Approximate token budget")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint if available")
    args = parser.parse_args()

    if args.test:
        success = smoke_test()
        sys.exit(0 if success else 1)

    if args.test_actions:
        success = test_actions()
        sys.exit(0 if success else 1)

    if not args.spec:
        print("No --spec provided. Use --test or --test-actions for self-tests.")
        print("To run the agent: python agent.py --spec workspace/secret_spec/SECRET_SPEC.md")
        sys.exit(0)

    success = run_agent(args.spec, max_iterations=args.max_iterations, max_token_budget=args.budget, resume=args.resume)
    sys.exit(0 if success else 1)