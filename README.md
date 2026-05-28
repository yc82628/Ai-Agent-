# Midknight Watcher

42 Berlin x Needle Hackathon: May 21-22, 2026
Team: Midknight Watcher

## Overview

An autonomous coding agent that reads a hidden technical specification, plans an implementation, writes code, runs tests, inspects failures, and iteratively repairs its work — using free-tier remote LLMs with local Ollama as disaster-recovery fallback.

## Architecture

A single Python loop (`agent.py`) drives an implementation-and-repair cycle. It reads `workspace/secret_spec/SECRET_SPEC.md`, then iterates: ask the primary model for the next action, execute it, observe results, log everything. Inference uses a three-tier fallback chain: Cerebras Qwen3-235B-A22B-Instruct-2507 (primary, ~2000 tok/sec) → Groq Llama 3.3 70B (failover, different model family) → local Ollama Qwen3.5 9B (disaster recovery). All prompts, decisions, commands, test runs, and human interventions are logged with timestamps in `agent_logs/`.

A checkpoint is written to `.agent-state/checkpoint.json` after every iteration. If the agent crashes overnight, restarting with `--resume` continues from the last checkpoint rather than from iteration 1.

## How to run

```
pip install -r requirements.txt
python agent.py --spec workspace/secret_spec/SECRET_SPEC.md
```

## To resume from a crash:

```
python agent.py --spec workspace/secret_spec/SECRET_SPEC.md --resume
```
## To verify the inference stack is working:

```
python agent.py --test
```

## Python version

3.11+

## 19:45 checkpoint

Tagged `agent-readiness-1945` per hackathon rules.

## Models used

See `agent_manifest.json` for the complete disclosure.

## Result

92/150 public tests passed (61.3%) on the Knitting Compiler spec. Per-level breakdown and full intervention history in `agent_logs/final_report.md`.

## Logs and process evidence

All six required log files live in `agent_logs/`:

- `prompts.log` — every prompt sent to a model
- `decisions.log` — every action the agent chose
- `commands.log` — every file write and shell command
- `test_runs.log` — every test invocation and its result
- `errors.log` — every failure, including tier failovers
- `human_interventions.log` — every manual intervention (if any)

`final_report.md` is auto-generated at the end of every agent run.

## Team

- Sushi (Shrish Arunesh) — Orchestrator, agent author, primary inference routing
- Partner — Monitoring, Friday morning manual cleanup

The two team members operate remotely from separate locations on Discord — no machine-to-machine LAN.