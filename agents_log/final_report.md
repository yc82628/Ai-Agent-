# Midknight Watcher Final Report

**Hackathon:** 42 Berlin x Needle - "Build What Works", May 21-22, 2026
**Team:** Midknight Watcher (Sushi + remote partner)
**Repo:** https://github.com/ShashQuash/midknight_watcher_42Hackathon
**Hidden task:** Knitting Compiler (`knit.py`)
**Generated:** 2026-05-22, post-final test run, pre-submission

---

## Headline Result

**92/150 public tests passed (61.3%)**, produced by an autonomous coding agent across two runs totaling roughly 50 minutes of wall-clock model time.

| Level | Passed | Total |
|-------|--------|-------|
| level_01_valid_basics | 19 | 20 |
| level_02_stitches | **25** | **25** |
| level_03_brackets | 0 | 25 |
| level_04_row_repeats | 18 | 20 |
| level_05_single_errors | 18 | 30 |
| level_06_multi_error_recovery | 1 | 15 |
| level_07_cli_output | **5** | **5** |
| level_08_stress | 6 | 10 |

Two levels solved completely (`stitches`, `cli_output`). One level effectively unimplemented (`brackets`) - see Section 4 below for the diagnosis. The remaining levels are partial, with failures concentrated on bracket-dependent features that cascade through `multi_error_recovery` and parts of `single_errors` and `stress`.

---

## 1. Run Summary

- **Spec:** `workspace/secret_spec/SECRET_SPEC.md` (38326 chars, 927 lines)
- **Iterations completed across all runs:** 30 (with one rollback to iteration 28's output)
- **Final artifact:** `workspace/knit.py`, 26698 chars, written by the agent at iteration 28
- **End reason:** Friday-morning recovery session concluded after one regression rollback; submission frozen at the agent's last known-good autonomous output

## 2. Inference Tier Usage

| Tier | Provider | Model | Successful calls |
|------|----------|-------|------------------|
| Cerebras (primary) | cloud.cerebras.ai | qwen-3-235b-a22b-instruct-2507 | ~28 |
| Groq (failover) | console.groq.com | llama-3.3-70b-versatile | ~2 |
| Local Ollama (disaster recovery) | localhost:11434 | qwen3.5:9b | 0 |
| **Failed (all tiers down)** | — | — | 1 episode (recovered) |

The three-tier fallback chain handled multiple Cerebras 429 rate-limit events and one Groq 413 "request too large" event during recovery. Local Ollama was never invoked because the cloud tiers covered all needs, but it remained warm as last-resort insurance. Architecture details in `agent_manifest.json` and `README.md`.

## 3. Actions Taken (across all iterations)

- **PLAN:** 3
- **EDIT_FILE:** ~9 (writing/rewriting `knit.py` and `PLAN.md`)
- **RUN_TESTS:** ~12
- **RUN_COMMAND:** small number, mostly inspection
- **STOP:** 0 (agent never reached a state where it self-declared done; we froze the run manually after the rollback)

## 4. Engineering Notes

The agent is a single ~620-line Python loop in `agent.py`. Each iteration: assemble messages (system prompt + spec + recent history) → call the model through the fallback chain → parse a JSON action from the response → dispatch to an action handler → log everything → commit to git → save checkpoint. Persistence is granular: after every iteration the full state writes to `.agent-state/checkpoint.json`, which means `--resume` can pick up from any point.

The fallback chain is the strongest engineering story. Cerebras 429'd repeatedly during both the Thursday-evening drills and the overnight run; each time, the agent transparently moved to Groq within seconds without losing state. The `errors.log` shows these transitions with timestamps. The choice to use **different model families** for primary and failover (Qwen for Cerebras, Llama for Groq) was deliberate - same-family fallback would have shared blind spots.

The biggest single design choice was **rejecting OpenHands** and writing a custom loop. For a two-person team operating under time pressure, 620 lines of code we fully understood and could debug live was worth more than a framework that would have required hours of configuration time we didn't have. This decision paid off directly during Friday-morning recovery, when we needed to patch the harness three times in under 30 minutes - moves that would have been much harder against an opaque framework.

## 5. What Worked

- **Three-tier fallback chain.** Survived every Cerebras 429 and one Groq 413 with no loss of work.
- **Per-iteration git commits.** The commit history *is* the autonomy proof — every PLAN, every EDIT_FILE, every RUN_TESTS is traceable.
- **Checkpoint-based resume.** Made it possible to recover from the overnight crash without losing 25 iterations of model context.
- **Defensive `workspace/` prefix stripping.** Caught the predictable LLM mistake of double-prefixing paths.
- **Cross-family model choice (Qwen + Llama).** Different blind spots = better effective coverage.
- **Pre-spec testing.** The agent solved a fake calculator spec in 9 iterations before the real spec landed, which is why we had the confidence to ship.

## 6. What Didn't Work

- **Parse-failure threshold too strict.** The 5-consecutive-failures hard stop killed the overnight run prematurely. With a longer threshold or smarter recovery, the agent might have produced a much better score before sleep.
- **No final report written on crash exit.** Bug in `run_agent` - the parse-failure exit path returned `False` without calling `write_final_report()`. Caught and fixed Friday morning.
- **Default `max_tokens=4000` was too small for an agent emitting large file contents through a JSON envelope.** When `knit.py` grew past ~6KB the response got truncated mid-string, which is why JSON parsing failed five times in a row. Fixed Friday morning to 8000.
- **History window blew Groq's TPM limit on resume.** After the agent wrote a 25KB `knit.py` at iteration 26, the next call included that response verbatim in the 6-turn history window, plus the 38KB spec, plus other turns. Groq 413'd; trimmed to 3 turns + per-turn truncation, problem solved.
- **Iteration 30 introduced an infinite loop.** The agent's edit at iteration 30 caused at least one public test input to hang. We rolled `knit.py` back to iteration 28's output via `git checkout`, preserving the 92/150 score.
- **No internal per-test timeout in the test runner's invocation.** When iteration 30 hung, multiple Python subprocesses stalled and we noticed only because `tasklist` showed five live `python.exe` instead of the expected one or two.

## 7. Human Interventions

Per the rules, every manual intervention is logged in `agent_logs/human_interventions.log`. Summary:

**Thursday, pre-spec (allowed: harness development phase):**
- All agent code was built and tested with AI assistance during the daytime build window.

**Thursday ~23:50 (allowed: harness improvements only):**
- Fixed `action_run_tests` path to point at the real `secret_spec/test_runner/run_tests.py`.
- Updated SYSTEM_PROMPT to reference `knit.py` (not `solution.py`).
- Committed transparently before launching the agent at 23:55.

**Friday morning (recovery session, all harness-level):**
- Touched `.expected.json` mtimes to bypass the test runner's `is_stale_expected()` false-positive (file extraction artifact, not a content modification).
- Bumped `max_tokens` from 4000 to 8000 in `call_model` and the `run_agent` call site.
- Added `write_final_report` call to the parse-failure exit path.
- Trimmed `build_messages` history window from 6 to 3 turns, with per-turn content caps, to fit Groq's TPM ceiling.
- Killed a hung agent run that had produced an infinite-loop `knit.py` at iteration 30 (5 Python processes stuck).
- Restored `knit.py` from commit `84410d5` (iteration 28's autonomous output, scoring 92/150) via `git checkout`, after iteration 30's edit hung the test runner.

**What we did NOT do:**
- Did not manually edit `knit.py`. Every line in the submitted file came from the agent.
- Did not use paid AI assistants, Copilot, or institutional/work API quotas after 20:00 Thursday.
- Did not give the agent spec-domain hints in the system prompt after the spec was released.

## 8. What We'd Do Differently

1. **Larger default `max_tokens`** (or chunked file writes via multiple EDIT_FILE actions). The JSON-envelope-around-large-file pattern was fragile.
2. **JSON repair on parse failure** before counting toward the consecutive-failure threshold. Truncated JSON is often recoverable.
3. **Per-test subprocess timeout** in any wrapper around the public test runner. An infinite loop on one test shouldn't stall the whole sweep for 11+ minutes.
4. **Detect regression and auto-revert.** If `score_after < score_before`, automatically `git checkout` the prior version of the artifact and feed the diff back to the model as "this edit caused regression."
5. **Progress sentinel file.** A `status.txt` updated every iteration with current score, last action, last error - would have made the half-asleep 04:00 check trivial.
6. **Token accounting, not just call accounting.** `tier_stats["cerebras"] += 1` is too coarse — we want actual tokens consumed per call so the budget tracker is real.
7. **Smaller initial code, growth by feature.** Instead of having the agent write the whole compiler at iteration 2, prompt for a minimal stub first and have it grow incrementally. This also keeps EDIT_FILE responses small enough not to truncate.

## 9. Disclosure

All inference providers used during the autonomous run were free-tier as listed in `agent_manifest.json`:
- Cerebras free tier (signup-only, no payment)
- Groq free tier (signup-only, no payment)
- Local Ollama (free, runs on team hardware)

No paid Claude, no paid ChatGPT, no Copilot, no Cursor or other IDE AI features were used after the 20:00 Thursday spec release for anything that touched the artifact `knit.py`. AI assistance was used during the harness recovery session Friday morning for diagnosing the test-runner staleness check, planning the three harness patches, and writing this report - none of which constitutes authoring or hinting at the artifact's logic. The exact commands run, files touched, and reasoning are documented commit-by-commit and in `human_interventions.log`.

---

## End of Report

The agent built 60% of a 38KB-spec compiler from scratch, autonomously, while we slept and then while we debugged its infrastructure. The score reflects both what worked and the specific places where our harness fell short - primarily around large-file emission and regression detection. The engineering story underneath the score is, we believe, worth more than the score itself.