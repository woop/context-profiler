# Context Profiler

[![Tests](https://github.com/woop/context-profiler/actions/workflows/test.yml/badge.svg)](https://github.com/woop/context-profiler/actions/workflows/test.yml)
[![Deploy](https://github.com/woop/context-profiler/actions/workflows/deploy.yml/badge.svg)](https://github.com/woop/context-profiler/actions/workflows/deploy.yml)

A prototype that profiles CLAUDE.md instructions against real agent traces to determine which are followed, which are dead, and which conflict. Uses LLM-as-judge assessment over Claude Code session traces, with targeted ablation to test causal impact. See [RATIONALE.md](RATIONALE.md) for why this problem and why this approach.

**[Live demo](https://context-profiler.pages.dev)**

## How the pipeline works

<img src="docs/img/pipeline.png" alt="Context Profiler pipeline" width="720">

**Extract** (profiler/extract.py): Opus reads the CLAUDE.md and returns each instruction as a verbatim snippet. The pipeline anchors each snippet back to exact byte offsets in the source file, validating that `source[start:end]` matches the snippet byte-for-byte.

**Run** (profiler/run_task.py): Each task runs via the Claude Agent SDK in an isolated workspace (copied repo, sandboxed config directory, bare mode). The agent sees only the demo CLAUDE.md and the repo. All SDK events are serialized to JSONL.

**Ablate**: The same task is re-run with a specific instruction removed from the CLAUDE.md. The resulting trace is compared against the full-context trace to determine whether behavior changed.

**Assess** (profiler/assess.py): Opus reads all traces (full and ablated) alongside the repo file listing and produces a structured verdict per instruction: keep, update, remove, or add_test. Each verdict includes evidence excerpts and an explanation.

**Review** (app/frontend): A React SPA renders the CLAUDE.md with each instruction span highlighted by verdict. Clicking a span shows the assessor's reasoning, evidence, and recommended action.

## What this prototype does

The prototype runs against a demo Python repo (csv-stats) with a 9-instruction CLAUDE.md constructed to exercise each verdict path (instructions that are followed, instructions that reference things that don't exist, instructions with conflicting clauses). This is a controlled test environment with known ground truth, not an evaluation against unknown inputs. Four tasks exercise different instruction surfaces:

- **add-tsv-loader**: add a TSV loading function (exercises type hints, pathlib, logging, pytest)
- **use-load-error**: refactor to domain-specific exceptions (exercises error handling, testing)
- **add-delimiter-flag**: add a CLI flag (exercises style, CLI conventions, testing)
- **add-median-stat**: add median calculation to reports (exercises style, testing, report module)

Each task is run twice with full context (control pair), and every instruction is ablated once (removed, same task re-run). Results across 8 full-context runs and 7 ablation runs: keep 4, update 2, remove 2, add_test 1.

## Limitations

- **n=1 ablations**: trace-based verdicts draw on 8 full-context runs (4 tasks, each run twice as a control pair). Ablations are n=1 per instruction: each instruction was removed once against one task. Control pairs establish a noise floor, but meaningful causal claims would require multiple seeds per ablation averaged across tasks.
- **Planted demo**: the demo CLAUDE.md is authored to exercise each verdict path. The profiler is confirming known ground truth, not discovering unknowns. Running against a real, uncontrolled CLAUDE.md is the next validation step.
- **Single context source**: the prototype profiles one CLAUDE.md file. System prompts, skills, tool descriptions, memory entries, and retrieved documents are all context that accumulates the same way but is not handled here.
- **LLM-as-judge, not measurement**: verdicts are qualitative judgments from a single Opus call, not quantitative scores. There is no inter-rater reliability, no rubric calibration, and no ground-truth labels to evaluate assessor accuracy against.
- **Offline only**: the pipeline runs against pre-defined tasks. It does not integrate with live agent sessions or continuous profiling.
- **No automated remediation**: the UI shows recommendations but does not apply them to the source file.

See [roadmap.md](docs/roadmap.md) for where this could go.

## Run it yourself

Requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 18+.

```bash
# Replay from committed artifacts (no API key needed)
uv run profiler/cli.py --replay

# Start the review UI
cd app/frontend && npm install && npm run dev

# Full pipeline (requires ANTHROPIC_API_KEY in .env)
uv run profiler/cli.py

# Re-assess without re-running tasks
uv run profiler/cli.py --skip-runs
```

All pipeline stages cache their outputs. The committed artifacts (traces, assessments, review items) allow full replay without an API key.

## Architecture

```
profiler/
  extract.py       Opus extracts instructions from CLAUDE.md
  run_task.py       Claude SDK runs tasks in isolated workspaces
  assess.py         Opus assesses instructions against traces
  cli.py            Chains all stages

demo-repo/          Target repository with CLAUDE.md
  .profiler/
    instructions/   Extracted instruction spans with byte offsets
    inputs/         Task definitions
    runs/           SDK session traces (full + ablated)
    attribution/    Assessor output (raw + normalized)
    review/         review-items.json (UI contract)

app/frontend/       React SPA rendering the annotated CLAUDE.md
```

## Tests

65 tests across two suites:

- **profiler/** (38 Python): extract helpers (stable IDs, anchor recovery, cache keys) + artifact integrity (schema validation, offset round-trip, cross-artifact ID consistency, ablation function, evidence variant alignment, summary counts)
- **app/frontend/** (27 vitest): highlight rendering, popover behavior, drift detection, real artifact integration

## FAQ

<details>
<summary>Why CLAUDE.md and not system prompts or tool descriptions?</summary>

CLAUDE.md is the most accessible context source for a prototype: it is a plain text file checked into the repo, it is read by Claude Code on every session, and its instructions are paragraph-sized units that map cleanly to the extract/assess/ablate loop. The same methodology applies to any injected context, but CLAUDE.md let us build the full pipeline without needing to intercept system prompt injection or tool registration.
</details>

<details>
<summary>Why use an LLM (Opus) for extraction instead of a deterministic parser?</summary>

A deterministic paragraph splitter works for well-structured files but fails on compound paragraphs where two independent instructions share a block. Opus can judge whether to split, and the pipeline validates its output by anchoring every snippet back to exact byte offsets. If the model hallucinates or paraphrases, the anchor step fails and the pipeline raises. The extraction prompt is versioned and included in the cache key, so changing it invalidates all downstream artifacts.
</details>

<details>
<summary>Why use the Claude Agent SDK instead of direct API calls for task runs?</summary>

The prototype needs to observe how a real coding agent responds to CLAUDE.md instructions: reading files, editing code, running tests. The Agent SDK provides tool use (Read, Edit, Bash, Grep, Glob) with permission control and session tracing. Direct API calls would require reimplementing tool execution and wouldn't produce the same behavioral signal.
</details>

<details>
<summary>How are verdicts determined? Is there a rubric?</summary>

The assessor (Opus) receives all instructions, all traces (full and ablated), and the repo file listing in a single prompt. It uses forced tool_use to emit structured output per the review-items schema. There is no numeric scoring rubric. The assessor is prompted with definitions of each verdict (keep, update, remove, add_test), status (supported, unobserved), and flag (stale, conflicting), plus rules for grounding verdicts in evidence. The full prompt is in profiler/assess.py.
</details>

<details>
<summary>What does the ablation actually prove?</summary>

An ablation removes one instruction from the CLAUDE.md and re-runs the same task. If the agent's behavior changes (e.g., stops running ruff), the instruction is causally necessary for that behavior. If the behavior is identical (e.g., the agent still uses logging.error), the instruction is redundant with other signals (codebase convention, task prompt, model priors). Ablation is stronger evidence than trace correlation, but it is still n=1 per instruction per task. A production system would ablate across many tasks and average.
</details>

<details>
<summary>How is the demo repo constructed?</summary>

The demo repo (csv-stats) is a small Python package with a CLI, tests, and a CLAUDE.md containing 9 instructions. Some instructions are well-grounded (style, testing, logging), some reference things that don't exist (Jenkins pipeline, admin UI). This is a controlled test environment: the pipeline's findings are verifiable against known ground truth, not surprising discoveries. The pipeline is designed to run against any repo with a CLAUDE.md, but using a known-good demo lets us validate the methodology before pointing it at unknown inputs.
</details>

<details>
<summary>Can I run this against my own repo?</summary>

In principle, yes: create a .profiler/config.json pointing at your CLAUDE.md, define tasks in .profiler/inputs/tasks.json, and run the pipeline. In practice, the task definitions need to be realistic for your repo, and the pipeline currently assumes a single CLAUDE.md file. There is no multi-file support or automatic task generation.
</details>

## Details

- [Design rationale](RATIONALE.md)
- [Design decisions](docs/decisions.md)
- [Coordination log](docs/worklog.md)
- [Roadmap](docs/roadmap.md)
