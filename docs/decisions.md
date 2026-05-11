# Decisions

Stable project decisions go here. Keep entries short and numbered.

## D001: Theme and core problem

Theme 4 (Evaluation & Data Quality). The problem is the asymmetry of context growth: AI product builders accumulate instructions in CLAUDE.md, system prompts, skills, and memory with no feedback loop to remove or update them. We are building the first slice of a profiler for context, analogous to dead-code elimination and tree shaking for source code.

## D002: Scope of the v0 artifact

A single CLAUDE.md is the artifact under analysis. Multi-source bundles (skills, tool descriptions, retrieved docs) are deliberately out of scope to allow depth over breadth. Assembled context-window snapshots are also out of scope: too dynamic and they lose provenance.

## D003: Granularity and chunking

Instructions, not rules. Granularity is paragraph-level, produced by an Opus-based chunker that may merge tightly-coupled bullets but never rewrites text. Each instruction carries one or more contiguous source spans of the original CLAUDE.md so the UI can highlight against the source. Headings are stripped from instruction text.

## D004: Verdict and status vocabulary

Assessor emits one verdict per instruction: `keep`, `update`, `remove`, or `add_test`. Internal status is `supported | unobserved`. Concerns (orthogonal flags that can co-occur with status): `conflicting`, `stale`. Stale is detected against the codebase, not the trace, so it can co-occur with supported (model followed an outdated rule).

Default mapping (assessor may override with rationale):

- supported -> keep
- unobserved -> add_test, or remove if the instruction looks decorative
- conflicting -> update with reconciled text
- stale -> remove, or update if salvageable

## D005: Assessor design

The assessor is an LLM (Claude Agent SDK) that reads agent traces and emits verdicts plus rationales. Heuristic thresholds are not used in v0; the point of the profiler is to surface human-quality reasoning over evidence the human could not gather alone.

## D006: Ablation deferred to iteration 2

The v0 pipeline runs the full context only and infers verdicts from compliance and conflict signals in the trace. Ablation (run each task with each instruction removed and compare) is required to make causal claims and must be added before assignment submission. The data model accommodates this from day one via a `context_variant` field on each run record (`"full"` in v0; `"ablate:<instruction_id>"` later) so adding ablation does not change schemas.

## D007: Pipeline shape

Nine stages, file-per-stage in `.profiler/`, hash-based caching:

1. Demo repo (stage 0; not in `.profiler/`).
2. Profiler workspace (`.profiler/`).
3. Extract instructions -> `.profiler/instructions/instructions.json`.
4. Define or generate tasks -> `.profiler/inputs/tasks.json`. Hand-authored for v0.
5. Run agent traces -> `.profiler/traces/sessions-index.json` plus per-run raw SDK events.
6. Score attribution -> `.profiler/attribution/instruction-evidence.json` and `assessor-raw.json`.
7. Build review items -> `.profiler/review/review-items.json`.
8. Validate artifacts (offsets, schema, path leakage, action presence).
9. UI consumes only review artifacts plus source CLAUDE.md.

Each stage writes a cache metadata file at `.profiler/stages/<stage>.cache.json` containing the input hash, timestamp, and output path. Reruns skip stages whose input hash is unchanged unless `--force` is passed.

## D008: Repo layout

  context-profiler/
    demo-repo/
      src/ tests/ CLAUDE.md pyproject.toml
      .profiler/   (committed for the demo so reviewers can see outputs without running)
        config.json
        instructions/instructions.json
        inputs/tasks.json
        traces/sessions-index.json
        attribution/{instruction-evidence.json, assessor-raw.json}
        review/review-items.json
        stages/<stage>.cache.json
        runs/
          pipeline/latest/{result.json, report.md}
          tasks/<task-id>/<run-id>/
            workspace/    (cp -r of demo-repo)
            agent-home/   (CLAUDE_CONFIG_DIR target)
            output/{sdk-events.jsonl, result.json, agent-output.json}
    profiler/
      src/ schemas/*.schema.json cli.py
    app/        (UI; reads review artifacts only, never writes)
    docs/

`.profiler/runs/` is gitignored everywhere; the per-stage canonical outputs are committed for the demo repo.

## D009: SDK isolation pattern

Per-task agent runs use the Claude Agent SDK with the following options (validated by the isolation spike on 2026-05-10):

- `cwd` set to the per-task workspace.
- `env` sets `CLAUDE_CONFIG_DIR` to the per-task `agent-home/`, exports `ANTHROPIC_API_KEY` from `.env`, blanks `CLAUDE_CODE_OAUTH_TOKEN`.
- `setting_sources=[]`.
- `strict_mcp_config=True`.
- `extra_args={"bare": None, "append-system-prompt-file": <CLAUDE.md absolute path>}`.

`--bare` is what disables CLAUDE.md auto-discovery (the upward walk from `cwd`); without it, the agent would pick up the project's CLAUDE.md and pollute the trace. `--append-system-prompt-file` injects the demo CLAUDE.md explicitly. `HOME` is left alone so shell tools (git, ssh) keep working.

## D010: Per-task isolation strategy

Each task run gets its own `runs/tasks/<task-id>/<run-id>/workspace/` (a `cp -r` of `demo-repo/`) and `agent-home/`. Sequential execution in v0; parallel later. The raw SDK trace lands at `agent-home/projects/<encoded-cwd>/<uuid>.jsonl` and is symlinked or copied to `output/sdk-events.jsonl` for predictable addressing.

## D011: Review items contract (UI <-> pipeline boundary)

The UI consumes exactly two files: the source CLAUDE.md and `review-items.json`. No raw traces, no scorer prompts, no stage cache metadata. The pipeline compresses everything else into the review item shape.

The pipeline is offline. It writes durable JSON artifacts under `demo-repo/.profiler/`. The React SPA reads those artifacts directly via Vite static imports (`import review from ".../review-items.json"`, `import source from ".../CLAUDE.md?raw"`). There is no HTTP API in v0. An API layer can be added later if we need runtime repo selection or in-browser pipeline execution; the contract is the same JSON shape so adding it is non-breaking.

Top level: `version`, `source { repoName, contextPath, contextHash, generatedAt }`, `summary`, `items[]`. `contextHash` is the SHA256 of the source CLAUDE.md so the UI can warn on drift.

Each item has orthogonal axes (do not collapse them):

- `verdict`: `keep | update | remove | add_test` (the recommended action; mirrors D004)
- `status`: `supported | unobserved` (whether traces exercised it)
- `flags`: subset of `["conflicting", "stale"]` (independent concerns)

Other item fields: `id` (stable; `instr-<sha8>` of the normalized text), `title` (~6 words, imperative, no period), `snippet`, `sourceFile`, `startOffset`, `endOffset`, `tokenCount`, `tokenDelta`, `metrics { sessionsObserved, totalSessions, traceEvents }`, `reason`, `evidence[]`, `proposedChange`.

`evidence[]` items: `id`, `kind` (`trace | absence | conflict | ablation`), `context_variant` (`full` in v0; reserved for ablation), `label`, `source` (provenance path; UI does not read it), `excerpt` (inlined so the UI never opens trace files), `explanation`.

`proposedChange.kind` mirrors `verdict`. For `update` -> `replacement` text. For `remove` -> no replacement. For `add_test` -> the suggested check, not a CLAUDE.md edit. For `keep` -> `proposedChange` is omitted.

Derivable fields are not in the contract: `reviewable` is `verdict != "keep"` and is computed in the UI.

## D012: Model selection per stage

Sonnet 4.6 (`claude-sonnet-4-6`) is the minimum for agentic stages (Stage 5: agent runs in the demo workspace). Opus 4.7 (`claude-opus-4-7`) for chunking (Stage 3) and assessing (Stage 6). If cost becomes a constraint, reduce task count or run length before reducing model quality. This supersedes the model field of the SDK isolation spike (D009 used Haiku for spike-only purposes); the SDK isolation knobs in D009 are unchanged.

## D013: Stable instruction id and Stage 3 cache key

Instruction id: `instr-<sha8>` where `sha8` is the first 8 hex chars of `sha256(sourceFile + ":" + collapse_internal_whitespace(snippet).trim())`. Survives reformatting (whitespace edits) but rewording produces a new id and orphans evidence (correct behavior).

Stage 3 cache key: `sha256(source_text || prompt_version || model || prompt_bundle)`. The prompt bundle is a stable serialization of `SYSTEM_PROMPT`, `USER_PROMPT_RULES`, and `EXTRACT_TOOL` (JSON, sorted keys). Any edit to the prompt text, tool schema, or extraction rules invalidates the cache without requiring a manual `PROMPT_VERSION` bump. The cache record at `.profiler/stages/extract-instructions.cache.json` stores the cache key, source hash, prompt version, model name, generated_at, and output path. Reruns skip the LLM call when the key matches and the output file exists.

Anchor recovery: the extractor returns an instruction snippet that may differ from the source by whitespace. Anchoring is done in source order using a moving cursor (`search_from`) so that repeated phrases resolve to the correct occurrence. Rules:

1. Try exact `source.find(snippet, search_from)`.
2. If not found, build a regex by escaping the snippet then replacing each whitespace run with `\s+`, search `source[search_from:]`, and use the matched span. The final stored snippet is `source.slice(start, end)` (source-derived), not what the model returned. Increment a per-run counter and log the fallback.
3. If still not found, raise. No silent skip.
4. Advance cursor to `end` before processing the next instruction.

The schema validator proves `snippet === source.slice(startOffset, endOffset)` on every emitted instruction.
