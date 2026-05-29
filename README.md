# Context Profiler

[![Tests](https://github.com/woop/context-profiler/actions/workflows/test.yml/badge.svg)](https://github.com/woop/context-profiler/actions/workflows/test.yml)
[![Deploy](https://github.com/woop/context-profiler/actions/workflows/deploy.yml/badge.svg)](https://github.com/woop/context-profiler/actions/workflows/deploy.yml)

**[Demo](https://context-profiler.pages.dev)** · **[Design rationale](RATIONALE.md)**

Agent context grows monotonically because there is no feedback loop for knowing which instructions still matter. Context Profiler is a prototype of that feedback loop.

This prototype profiles each CLAUDE.md instruction against real session traces to determine whether the agent followed it, ignored it, or contradicted it, and whether removing the instruction changes behavior.

## What to try in the demo

The demo shows a synthetic `CLAUDE.md` for a Python package after being profiled against 8 baseline Claude Code runs and 9 single-instruction ablations. Click **Start review** to walk through the 3 recommended edits: update the testing convention, remove the stale admin UI instruction, and remove the obsolete Jenkins deploy instruction. The final screen shows the resulting `CLAUDE.md` diff and lets you copy the updated file.

## How the pipeline works

<img src="docs/img/pipeline.png" alt="Context Profiler pipeline" width="720">

**[Extract](profiler/extract.py)**: Parses the context file and returns each instruction as a verbatim snippet, anchored to exact byte offsets in the source.

**[Run](profiler/run_task.py)**: Runs each task in an isolated copy of the repo. All agent events are serialized to JSONL traces.

**[Ablate](profiler/run_task.py#L61)**: Re-runs the same task with a specific instruction removed. The resulting trace is compared against the full-context trace.

**[Assess](profiler/assess.py)**: Reads all traces (full and ablated) and produces a structured verdict per instruction: keep, update, remove, or add_test, with evidence and explanation.

**[Review](app/frontend/)**: Renders the context file with each instruction span highlighted by verdict. Clicking a span shows evidence and recommended actions.

The submitted demo artifacts contain 4 tasks run as 8 full-context baseline traces plus 9 single-instruction ablations. `--replay` rebuilds the review from those committed artifacts without an API key. See [RATIONALE.md](RATIONALE.md) for methodology, tradeoffs, and limitations.

## Run it yourself

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 18+.

```bash
# Replay the submitted 17-run demo artifacts (no API key needed)
uv run profiler/cli.py --replay

# Start the review UI
cd app/frontend && npm install && npm run dev

# Run the lightweight pipeline against the demo repo (requires ANTHROPIC_API_KEY in .env)
uv run profiler/cli.py

# Re-assess without re-running tasks
uv run profiler/cli.py --skip-runs
```

The submitted demo is designed for artifact replay: the committed traces make the evaluation deterministic and API-key-free. A production version would add idempotent orchestration for regenerating the exact 8-baseline + 9-ablation run matrix from scratch.

## Project layout

- [profiler/](profiler/) — extraction, task running, ablation, assessment, artifact replay, and integrity tests.
- [demo-repo/](demo-repo/) — synthetic Python package, demo CLAUDE.md, task definitions, and committed profiler artifacts.
- [app/frontend/](app/frontend/) — React review UI rendered from the committed review artifact.
- [traces/main-thread-and-backend/](traces/main-thread-and-backend/) — primary Claude Code development transcript, including 3 subagent traces.
- [traces/frontend/](traces/frontend/) — review UI implementation transcript.
- [traces/deployment/](traces/deployment/) — Cloudflare Pages and GitHub Actions setup transcript.
- [traces/readme-diagrams/](traces/readme-diagrams/) — README diagram iteration transcript.

## Tests

65 tests across two suites:

- **profiler/** (38 Python): extract helpers, artifact integrity (schema validation, offset round-trip, cross-artifact ID consistency, ablation, evidence alignment)
- **app/frontend/** (27 vitest): highlight rendering, popover behavior, drift detection, real artifact integration
