# Worklog

Append-only coordination log for the project.

Each meaningful entry should include:

- timestamp
- current goal
- decisions made
- open questions
- files changed
- commands run
- validation results
- blockers
- next step

Do not rewrite older entries except to fix typos.

Use `## [date] [Title] [Author]` as header

---

## 2026-05-10 Research synthesis and prototype direction [scout]

Identity: scout. Read assignment.md, CLAUDE.md, docs/research/{search-1,search-2,search-3}.md. Note: email.md referenced in user instructions does not exist in the workspace.

Goal: scope a 1-2hr prototype around context attribution/evaluation for AI agents.

Synthesis (decision-oriented):

- Five method families in the literature: attribution (LOO, attention, Shapley, ContextCite), behavioral eval (IFEval, judge, task pass-rate, swap testing), compression/pruning (LLMLingua, SWE-Pruner, RECOMP, latent), memory lifecycle (LightMem, Letta, Reflexion, sub-agents), observability/replay (LangSmith/Phoenix/OTel).
- Key tension: attribution shows what moved the output; behavioral eval shows whether the move was good. Have to pair them.
- Strong empirical case for pruning as quality (not just cost): Chroma context-rot, NoLiMa, AbsenceBench, Du 2025 blank-token result. nilenso swap study shows system prompt is decisive.

Five candidate prototypes considered:

- P1 Context X-ray: LOO ablation per chunk against a small task suite, heatmap output.
- P2 Rule auditor: per-rule instruction-following compliance rates with auto-built checkers.
- P3 ContextCite-lite: sparse linear surrogate for per-response attribution, interactive UI.
- P4 Conflict/redundancy linter: judge-only static analysis. Weak evidentiary base.
- P5 Pruning recommender: greedy minimal-subset search on top of P1 data.

Decision: build P1 + P5 hook, with 1-2 P2-style verifiable checkers embedded in the task suite. Rationale: causal, measurable, visualizable, self-contained, has a clear payoff line ("X% of this CLAUDE.md is load-bearing").

Plan sketch:

- Demo agent: synthetic ~12-chunk context (system prompt sections, 3 skills, 4 memories, 2 tool descs, 1 planted conflicting rule).
- Task suite: 12 tasks, deterministic checker first, judge fallback, designed to intersect specific chunks.
- Engine: async parallel calls to Haiku, LOO + baseline, ~150-200 calls.
- UI: single static HTML dashboard with heatmap + pruning summary.

Open questions / uncertainty:

- Chunk granularity (section vs sentence vs whole skill). Lean section-level for v1.
- Task-suite coverage with only 12 prompts. "No signal" for some chunks is acceptable as a finding.
- Reproducibility under stochastic decoding. Lean temperature 0 + checker-first metric.
- API key/budget for ~200 Haiku calls. Need to confirm.
- Hosted vs local for demo delivery. Need to decide before coding.

Files changed: docs/worklog.md (this entry).
Commands run: none (read-only research pass).
Validation: none yet.
Blockers: none; awaiting user direction on which prototype to build.
Next step: get user sign-off on direction (P1+P5), then start a thin end-to-end slice with 4 chunks and 4 tasks before scaling.

## 2026-05-10 Pipeline shape and naming locked [scout]

Worked through the idea maze with the user. Outcomes:

- Core problem framed as: context is the new code; there is no equivalent of dead-code elimination or tree shaking for injected context. We build the first slice of a profiler that says what to keep / update / remove / add a test for.
- Theme 4 (Evaluation & Data Quality).
- Primary user: AI product builders. Secondary: power users curating their own CLAUDE.md.
- Artifact: a single CLAUDE.md (depth over breadth). Multi-source bundles are a future extension.
- Granularity: paragraph-level, produced by an Opus chunker that may merge tightly-coupled bullets but never rewrites text. Source spans preserved.
- Vocabulary: instructions (not rules).
- Verdicts emitted by assessor: keep / update / remove / add_test. Status enum: supported | unobserved. Concerns (orthogonal): conflicting, stale.
- Assessor uses LLM judgment over evidence (not heuristic thresholds), targeted at agent traces produced by the Claude Agent SDK.
- v0 scope: full end-to-end pipeline without ablation. Ablation is required to complete the assignment and is the next iteration; data model accommodates it via a `context_variant` field on each run so the schema does not change.
- Demo repo: small, real-feeling Python project (CLI / library), with planted instructions covering each verdict path.
- Per-task isolation: cp -r the demo repo into a per-run workspace.
- Pipeline stages 1-9 with file-per-stage cache, hash-based invalidation.

Naming clarifications adopted:

- Raw SDK events: `runs/tasks/<task-id>/<run-id>/output/sdk-events.jsonl`.
- `traces/sessions-index.json` indexes runs and points at raw event files.
- `traces/normalized/` only created if we add a cleaned projection; omit otherwise.
- `attribution/assessor-raw.json` (renamed from model-output.json).
- `stages/<stage>.cache.json` for per-stage cache metadata (input hash, timestamp, output path).
- `profiler/schemas/*.schema.json` holds JSON schemas; `profiler/validators.py` consumes them.
- `.profiler/config.json` to define minimally: claude_md_path, task_source, models per stage, concurrency.

Tree:

  context-profiler/
    demo-repo/
      src/ tests/ CLAUDE.md pyproject.toml
      .profiler/
        config.json
        instructions/instructions.json
        inputs/tasks.json
        traces/sessions-index.json
        attribution/{instruction-evidence.json, assessor-raw.json}
        review/review-items.json
        stages/<stage>.cache.json
        runs/
          pipeline/latest/{result.json, report.md}
          tasks/<task-id>/<run-id>/{workspace/, agent-home/, output/{sdk-events.jsonl, result.json, agent-output.json}}
    profiler/
      src/ schemas/ cli.py
    app/
    docs/

Files changed: none yet.
Next step: SDK isolation spike before any stage code.

## 2026-05-10 SDK isolation spike result [scout]

Goal: confirm we can run the Claude Agent SDK from inside this repo tree without leaking the project's own CLAUDE.md, the user's global ~/.claude config, or the user's identity from auto-memory. This was the gating risk for stage 5; rebuilding the runner later would be expensive.

Files added:
- profiler/spikes/isolation/run.py
- profiler/spikes/isolation/workspace/CLAUDE.md
- profiler/spikes/isolation/result.json (run output)
- profiler/spikes/isolation/sandbox_home/ (created by run; gitignored via .profiler conventions)

Setup:
- API key from .env at repo root.
- Sandbox CLAUDE.md plants a sentinel `PURPLE-OCTOPUS-7421`, role "Pizza Chef", project name "Sandbox Verification Project".
- Four prompts run sequentially via ClaudeSDKClient against claude-haiku-4-5.
- Snapshot of ~/.claude/projects taken before and after.

SDK options used (these are the recommendation for stage 5):

  ClaudeAgentOptions(
      cwd=<per-task workspace>,
      env={
          "CLAUDE_CONFIG_DIR": <per-task agent-home>,
          "ANTHROPIC_API_KEY": <key>,
          "CLAUDE_CODE_OAUTH_TOKEN": "",      # defensive: don't reuse inherited OAuth
          "PATH": <inherited>,
      },
      setting_sources=[],                     # block user/project/local settings.json
      strict_mcp_config=True,                 # ignore .mcp.json on disk
      model="claude-haiku-4-5-20251001",
      extra_args={
          "bare": None,                       # disables hooks, plugins, auto-memory, CLAUDE.md auto-discovery, Keychain
          "append-system-prompt-file": <demo CLAUDE.md absolute path>,
      },
  )

Test results (all four passed; elapsed 16s total):

- marker: returned the exact sentinel.
- role: returned "Pizza Chef" with no mention of Cleric/CTO/Pienaar.
- identity_leak: model said it has no knowledge of Willem Pienaar or Cleric.
- discovery: model reported only the sandbox CLAUDE.md, no upward walk to the project's CLAUDE.md.
- Filesystem: zero new files in ~/.claude/projects/ during the run.
- Sandbox home: 7 files written (settings, backups, 4 session jsonl traces — one per prompt).

Implication for stage 5: per-task layout works as expected.

  runs/tasks/<task-id>/<run-id>/
    workspace/             # cp -r of demo-repo
    agent-home/            # CLAUDE_CONFIG_DIR target
      projects/<encoded-cwd>/<uuid>.jsonl   # raw SDK trace lands here
    output/
      sdk-events.jsonl     # symlink or copy of the jsonl above for predictable addressing

Open items the spike intentionally did not cover (future):
- Tool use (we ran read-only prompts). Stage 5 will allow Read/Edit/Bash/Glob/Grep with permissionMode=dontAsk.
- Cost budget enforcement. The TS pattern uses maxBudgetUsd; verify the Python SDK exposes this and wire it.
- Concurrency. v0 runs sequentially; if we parallelize, each task gets its own agent-home so no conflict expected.
- Multiple prompts per session vs one-prompt-per-session. Spike used the latter (4 separate UUIDs). For tasks we want one session per (task, run) so the runner uses one query() call per run.

Validation: passed. No blockers for stage 5.
Next step: scaffold demo repo (stage 0) and JSON schemas, then stages 3-7 in order.

## 2026-05-10 Output contract locked, UI thin slice green [scout]

Goal: lock the UI <-> pipeline contract (D011) and stand up a thin end-to-end UI slice driven by smoke tests, so the SPA and pipeline can move in parallel.

Decisions made:

- D011 review items contract: orthogonal axes (`verdict`, `status`, `flags`); `evidence.kind` extended to `trace | absence | conflict | ablation` with `context_variant` reserved for ablation; stable `instr-<sha8>` ids; `tokenDelta` per item; `contextHash` on the artifact for drift detection; `reviewable` removed (derive in UI).
- No FastAPI in v0. The pipeline is offline and writes durable JSON. The SPA reads artifacts via Vite static imports. An API layer is deferred until we need runtime repo selection or in-browser pipeline runs.

Files added:

- profiler/schemas/review-items.schema.json (canonical contract)
- demo-repo/CLAUDE.md (planted instructions; offsets in fixture map to real bytes)
- demo-repo/.profiler/config.json (repoName, claudeMdPath)
- demo-repo/.profiler/review/review-items.json (hand-written fixture: 6 items covering keep/update/remove/add_test, both statuses, both flags; contextHash matches CLAUDE.md sha256)
- app/frontend/ (Vite + React + TypeScript SPA, vitest smoke suite, jsdom)
  - src/{App.tsx, main.tsx, types.ts, styles.css}
  - tests/{App.test.tsx, setup.ts}
  - vite.config.ts (server.fs.allow rooted at repo root so @fs serves CLAUDE.md and the review JSON)

Build/test results:

- vitest: 7/7 passing. Three groups: header/list/detail rendering against an inline fixture; drift banner when source hash diverges; integration tests against the real CLAUDE.md and real review-items.json (sha256 matches; offsets map to spans).
- tsc --noEmit: clean.
- vite build: production bundle 157KB (gzip 50KB).
- Dev server boots; @fs serves both artifacts (200, byte counts match).

Validation against the contract: the schema, fixture, and UI now agree on the same shape. Any pipeline stage that produces review-items.json is now fully constrained.

Open items / next:

- Implement the pipeline stages (3-7) that produce instructions.json, tasks.json, sessions-index.json, instruction-evidence.json, review-items.json. The fixture is the spec.
- Add the source viewer pane that highlights the selected item's span using `startOffset`/`endOffset` (deferred from the thin slice; UI shows offsets numerically for now).
- Stage 8 validators: schema check, offset round-trip, path leakage, action presence. The frontend integration tests already cover schema-shape and offset round-trip; lift these into the pipeline as standalone validators.
- Ablation (D006) before submission.

Files changed: docs/decisions.md (D011 amended), docs/worklog.md (this entry).
Blockers: none.
Next step: pipeline stage 3 (extract-instructions) targeting the same instructions/offsets the fixture uses, so we can swap fixture for real output without touching the UI.

## 2026-05-10 UI direction proposal [atlas]

Identity: atlas (frontend; picking up where scout left the SPA). Read assignment.md, CLAUDE.md, decisions.md (D001-D011), worklog (all entries), profiler/schemas/review-items.schema.json, the fixture, demo-repo/CLAUDE.md, and app/frontend/src/App.tsx. No code or fixture changes in this entry, just direction.

Goal: pick a UI shape for the v0 prototype before I start moving pixels. The contract (D011) is the boundary I work behind; the question is what shape best communicates "your CLAUDE.md is the artifact under review, here is what stays, what changes, what goes."

Three directions considered.

(A) Dashboard / table-first. Top-level summary tiles, sortable filterable table of items keyed on verdict/status/flags/tokenDelta, click-through to a detail panel. The current SPA leans this way already.
- Makes easy: scanning at scale, sorting by token impact, batch ops (accept all keeps), aggregate optics like "X% of this CLAUDE.md is load-bearing", export. Familiar pattern, low friction.
- Hides: the document. The reviewer never sees their CLAUDE.md as a whole. Spatial intuition is lost (where in the file does this live, what surrounds it). The fact we have real byte offsets is wasted. Feels like yet another linter dashboard, which undercuts the framing of "profiling for context".

(B) Document-first annotated source. CLAUDE.md is the canvas. Instruction spans are highlighted inline, colored by verdict (keep neutral, update amber, remove strikethrough red, add_test dotted blue). Status and flags ride as small glyphs in the gutter. Click a span -> evidence and proposedChange in a side drawer; for `update`, show inline diff against the original snippet; for `remove`, show what would be deleted.
- Makes easy: the moment of insight ("this paragraph is dead weight, this one is doing the work"). Anchors recommendations to the artifact, which matches the project framing better than a table can. Drift becomes legible (you're literally looking at the source). The proposedChange becomes a credible thing because you see it land in context, not abstracted away.
- Hides: cross-cutting analysis. Hard to answer "show me all stale items" or "what's the total token delta if I accept everything" without an extra surface. Long CLAUDE.md files become a scroll problem. Evidence excerpts (which can be longer than the instruction) compete with the source for space.

(C) Review queue / sidebar. PR-review feel. Left rail is an ordered queue of items needing decision (verdict != keep), right pane is one item at a time with full evidence and accept/edit/reject affordances. Source shown as a 5-10 line excerpt around the span.
- Makes easy: decision-making flow. One-thing-at-a-time. Clear "what is left to review" affordance. Mirrors GitHub/Phabricator so users already know how to drive it. Action-oriented; the user feels like they made progress.
- Hides: the document as a whole. The scope of the recommendation across the file. Aggregate stats unless added explicitly. Reviewers can lose the sense that this is their CLAUDE.md being analyzed and start treating items as disconnected tickets. Harder to spot adjacency effects (two adjacent paragraphs that are both stale probably mean the whole "Deployment" section is dead).

Recommendation for the first prototype: lead with (B), borrow from the others.

Concretely: document-first as the hero canvas, with a compact queue rail in source order on the left and a detail drawer on the right that opens on selection. Keep the existing summary strip in the header for aggregate optics. So:

- Header strip: repo, file, totals, token delta, flag counts, drift banner. (Already there; keep.)
- Left rail (~280px): items in source order, compact rows showing verdict glyph, title, status, flags. Filter chips (all / keep / update / remove / add_test, plus "needs review" = verdict != keep). Selection scrolls the canvas to the span.
- Center canvas: rendered CLAUDE.md with instruction spans highlighted by verdict. Section headings remain visible for spatial orientation. Hovering a span pops a one-line tooltip (verdict, status, sessionsObserved/totalSessions). Clicking selects.
- Right drawer (opens on selection): title, badges, reason, metrics, evidence list, proposedChange. For `update`, show snippet -> replacement as a unified diff. For `remove`, show what disappears and the resulting token delta. For `add_test`, show suggestedTest as code. For `keep`, no proposedChange (per D011).

Why this is the right v0 bet:
1. The pitch ("context is the new code; here is profiling for it") only lands if the artifact is on screen. Anything else is a report about a file the user has to imagine.
2. Differentiation. Tabular linters exist. The unique moment is "look at your CLAUDE.md as a heatmap of evidence". That moment requires the document on screen.
3. The contract gives us real byte offsets that round-trip through `slice(start, end)`. Not using them visually wastes the strongest property of the data.
4. Adjacency is meaningful. A whole section being stale (e.g., the Deployment section in the fixture) tells a different story than one stale instruction; only the source view shows that.
5. Borrowing the queue rail from (C) covers the "what's left to review" affordance without committing to that as the primary surface, and the header strip from (A) preserves aggregate optics.

What I am explicitly not building in v0 from this proposal:
- Bulk operations / "accept all keeps" / export. Out of scope for the prototype unless the hero loop needs it.
- Persisted decisions ("I reviewed this"). Adds state surface without showing off the data; defer.
- Source heatmap mini-map. Nice-to-have once the basic spans render; only worth it if the CLAUDE.md gets long.
- Collapsible sections in the canvas. Only worth it if scrolling becomes painful.

Open questions for the user before I start cutting code:
- Confirm the document-first lead is the right bet vs. doubling down on the dashboard the SPA already has.
- For `update`, do you want the diff inline in the canvas (replace-on-accept feel) or only in the drawer (review-then-accept feel)? I'm leaning drawer-only for v0 because we don't have an "accept" path.
- Is there appetite for a small token-savings preview chip (e.g., "−51 tokens if you accept all non-keep recommendations") in the header? It's a one-liner that makes the prototype's value more concrete on first load.

Files changed: docs/worklog.md (this entry).
Commands run: none (read-only pass; explored fixture, schema, App.tsx, source CLAUDE.md).
Validation: none yet.
Blockers: awaiting user sign-off on direction (B with rails from A and C) before implementing.
Next step on approval: write smoke tests for span-rendering against fixture offsets, then implement the canvas + drawer + rail in that order.

## 2026-05-10 Document-first first slice [atlas]

Goal: ship the first document-first UI slice. Render the source CLAUDE.md as the canvas, highlight each review item by offset, show an inline verdict tag near each highlight, click selects with a minimal detail card. Nothing else yet (no filters, no list rail, no decisions, no diff, no evidence).

User decision before this entry: lead with document-first; build only the slice above.

Approach: tests first (per project CLAUDE.md), then implementation, then dev server in tmux.

Files changed:

- app/frontend/tests/App.test.tsx -- replaced filter/list assertions with document-first ones. Asserts: header renders title/repo/totals; full source text appears in the rendered output; one `data-testid="hl-<id>"` per item carrying `data-verdict` and the original snippet text; an inline `data-testid="hl-tag-<id>"` per item with the verdict word; nothing selected on first render; clicking a highlight reveals a detail heading and reason; drift alert when hashes diverge. Real-artifact integration block kept (sha256 match, offset round-trip) and extended with "renders one highlight per real review item carrying its snippet".
- app/frontend/src/App.tsx -- rewritten. Removed left filter rail, item list, evidence and proposedChange rendering. Added `buildSegments(source, items)` that walks a sorted list of items and emits an alternating sequence of plain and highlighted segments via `source.slice(start, end)` (the same call shape the integration test validates). Marks render `<mark>` with verdict-coloured background plus a small inline verdict tag. Right column is a minimal detail card (title, badges, reason) or an empty-state hint.
- app/frontend/src/styles.css -- restyled for "document is hero". Source column uses a serif at 1.02rem / line-height 1.75, max-width 880px, centred. Highlights use desaturated tints per verdict (keep green, update amber, remove red with strikethrough, add_test purple) with `box-decoration-break: clone` so multi-line marks paint cleanly. Verdict tag is a small uppercase mono pill at the end of each highlight. Right pane is a quiet panel; no aside list, no filter chips.

Decisions made:

- Document is rendered with `white-space: pre-wrap` over the raw markdown text (no markdown -> HTML rendering yet). Keeps offsets trivially correct and the first slice cheap. Markdown rendering can come later with a transform that preserves offsets, or by accepting that the highlight maps to source-byte ranges rather than rendered ranges.
- Highlights are non-overlapping per fixture; `buildSegments` assumes that and walks linearly. If overlaps appear later we will need a different layout (probably rendering the source by character with attribute layers), but the contract has not asked for this.
- Inline verdict tag chosen over gutter/margin annotations because gutter alignment with `pre-wrap` text is fragile and a small inline tag stays quiet next to the span without a layout dependency.
- No backend changes; the SPA still reads via Vite static imports per D011.

Commands run:
- `npx vitest run` -> 11/11 passing (was 7; new tests cover segment rendering, inline verdict tag, single-item selection, real-artifact highlight presence).
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> ok, dist/assets/index-*.js 155KB (gzip 50KB), CSS 3.5KB (gzip 1.28KB).
- `tmux new-session -d -s context-profiler ... 'npx vite --host 127.0.0.1 --port 5173'` -> dev server up; HTTP 200 on `/`.

Validation:
- All 11 vitest cases green, including the integration tests that hash the real CLAUDE.md and verify each item's `[startOffset, endOffset)` round-trips through `source.slice` to its `snippet`.
- Manual: dev server responds on http://127.0.0.1:5173/. The fixture's six items render as highlights over the actual CLAUDE.md text.

Blockers: none.
Next step (awaiting user direction): probably the right drawer growing the proposedChange diff for `update` items, then the left rail with a "needs review" filter. Both are additive and do not touch the contract.

## 2026-05-10 Phase A start: demo repo content + Stage 3 plan [scout]

Goal: Phase A of the pipeline. Replace the hand-written `review-items.json` with real pipeline output for one realistic task end-to-end. Starting with A.1 (demo repo content) and A.2 (Stage 3: LLM extractor).

User-locked constraints for this phase:

- Stage 3 uses an LLM extractor (Opus), not a deterministic chunker. Code anchors LLM-returned snippets back to exact source offsets. Anchor recovery via whitespace-collapsed regex is permitted only as a fallback; final artifact stores the source-derived snippet and exact offsets, and the validator proves `snippet === source.slice(start, end)`. Fallback usage is logged.
- Stable id locked: `instr-<sha8(sourceFile + ":" + collapse_internal_whitespace(snippet).trim())>`. This will replace the fixture's older `sha8(snippet)` scheme; the fixture's IDs will be regenerated when the real pipeline output supplants the fixture (no schema change).
- Stage 3 cache key: `sha256(source_text || prompt_version || model)`. Cache hit only when all three match.
- Sonnet 4.6 minimum for agentic stages (Stage 5). Opus for chunking and assessing. Supersedes the Haiku model used in the spike (D009 stays as-is for the isolation pattern; new decision will note model choice).
- Realistic tasks only. Some instructions will naturally remain unobserved when the task set is narrow; that is data, not a defect.
- Stale is reserved for date-specific or operational instructions whose anchors no longer exist (e.g., a Jenkinsfile that does not exist in the repo). Stale is never inferred from "no task touched this surface" -- that is `unobserved`.
- One-shot Opus assessor per (instruction × run) for Stage 6. Both raw model output and normalized evidence are persisted.
- Ablation deferred out of Phase A. Will add a single targeted ablation later, not the full matrix.

Concretely starting now:

1. Demo repo content under `demo-repo/`: `src/csvstats/{__init__,cli,loader,report}.py`, `tests/test_{loader,report}.py`, `pyproject.toml`. Realistic CSV-summarizer, type-hinted, uses pathlib, uses logging, has a CLI entry point. No `deploy/values.yaml`, no `Jenkinsfile` (so the deployment instruction in CLAUDE.md is genuinely stale relative to the codebase).
2. New decision D012: Sonnet 4.6 minimum for agentic stages, Opus for chunking and assessing. Supersedes the model-name field of D009 only (the SDK isolation knobs still hold).
3. New schema `profiler/schemas/instructions.schema.json`.
4. `profiler/extract.py` (PEP 723, uv-runnable): reads `demo-repo/.profiler/config.json`, loads CLAUDE.md, computes hash, checks cache, calls Opus tool-use endpoint, anchors snippets, validates offsets round-trip, writes `instructions/instructions.json` and `stages/extract-instructions.cache.json`.
5. Tests for the deterministic helpers (anchor exact + fallback, stable id, cache key, validator). Real LLM call validated end-to-end against the actual CLAUDE.md.

Files about to change:
- demo-repo/{pyproject.toml, src/csvstats/*.py, tests/*.py}
- docs/decisions.md (add D012)
- profiler/schemas/instructions.schema.json (new)
- profiler/extract.py (new)
- profiler/extract_test.py (new, deterministic helpers only)
- demo-repo/.profiler/instructions/instructions.json (output)
- demo-repo/.profiler/stages/extract-instructions.cache.json (output)
- docs/worklog.md (this entry, then closing entry on completion)

Note for atlas: Stage 3 will produce real instruction IDs that differ from the fixture's current IDs (new scheme includes sourceFile and normalized whitespace). Atlas's tests read IDs from whatever fixture is on disk, so this should not break them, but flagging in case anything was hard-coded against fixture IDs.

Blockers: none.
Next step in this entry: build A.1, then A.2; will append a closing entry with results and then commit.

## 2026-05-10 Phase A.1 + A.2 done [scout]

Phase A.1 (demo repo content) and A.2 (Stage 3 extractor) shipped and validated. Closing entry.

A.1 demo repo content:

- demo-repo/pyproject.toml (hatchling, src layout, pythonpath=src for tests)
- demo-repo/src/csvstats/{__init__,loader,report,cli}.py
  - Type hints throughout, pathlib for filesystem paths, logging in library modules with `exc_info=True`, `print` reserved for CLI stdout output.
  - No `deploy/values.yaml`, no `Jenkinsfile` (the Deployment instruction in CLAUDE.md is genuinely stale relative to the codebase, per the Phase-A constraint).
- demo-repo/tests/test_loader.py, test_report.py
- pytest: 7/7 passing.

A.2 Stage 3 (extract-instructions):

- profiler/__init__.py (package marker)
- profiler/extract.py (PEP 723, uv-runnable). Calls Opus via Anthropic Messages API with a forced-tool-use structured-output call. Helpers: `collapse_internal_whitespace`, `stable_id` (D013 scheme), `cache_key` (sha256(source || prompt_version || model)), `anchor` (exact-first, whitespace-tolerant fallback that returns source-derived span). Validators: offset round-trip, id uniqueness, JSON schema. Cache record at `.profiler/stages/extract-instructions.cache.json`.
- profiler/test_extract.py: 12/12 deterministic helper tests passing.
- profiler/schemas/instructions.schema.json: contract for the new artifact.

Live run results (Opus 4.7, prompt_version=1):

- demo-repo/.profiler/instructions/instructions.json: 6 instructions, 0 anchor fallbacks, all offsets round-trip, schema-valid.
- All 6 spans match the hand-written fixture's spans byte-for-byte. The model produced exact verbatim snippets without needing the fallback recovery path.
- Stable ids under the new scheme (instr-f684f82f, instr-16a56be0, instr-ceb73290, instr-327d7cfe, instr-f31bb00c, instr-4cd661fd). These differ from the fixture's older `sha8(snippet)` ids and will replace them when Stage 7 supersedes the fixture; atlas's UI tests read ids from disk so this is non-breaking for the SPA.
- Cache: rerun without `--force` correctly cache-hits and skips the LLM call.

Decisions added since last entry:

- D012: Sonnet 4.6 minimum for agentic stages, Opus 4.7 for chunking (this stage) and assessing (Stage 6 to come). Supersedes Haiku usage in the spike (D009 stays as the SDK-isolation knobs reference).
- D013: stable id formula and Stage 3 cache key formalized.

Files changed in this slice:

- demo-repo/pyproject.toml (new)
- demo-repo/src/csvstats/{__init__,loader,report,cli}.py (new)
- demo-repo/tests/{test_loader,test_report}.py (new)
- demo-repo/.profiler/instructions/instructions.json (new, real pipeline output)
- demo-repo/.profiler/stages/extract-instructions.cache.json (new)
- profiler/__init__.py (new)
- profiler/extract.py (new)
- profiler/test_extract.py (new)
- profiler/schemas/instructions.schema.json (new)
- docs/decisions.md (D012, D013 appended)
- docs/worklog.md (this and the previous entry)

Commands run:
- python3 -m pytest demo-repo/ -> 7/7 passing
- python3 -m pytest profiler/test_extract.py -> 12/12 passing
- uv run profiler/extract.py --force -> writes 6 instructions to disk
- uv run profiler/extract.py -> cache hit
- (cd app/frontend && npx vitest run) -> 11/11 passing (UI unaffected)

Blockers: none.
Next step: Phase A.3 (one realistic task) and A.4 (Stage 5: SDK run). About to commit then continue.

## 2026-05-10 Light theme, slim header, on-demand drawer [atlas]

Goal: pull attention back to the document. User feedback after seeing the first slice live: the header pill row read as a dashboard, the dark theme made highlights almost invisible, and the always-visible right pane competed with the source. First screen should be the annotated document; details only on selection.

Changes:

- app/frontend/src/styles.css -- switched to a warm-paper light palette (`--bg #faf9f6`, `--paper #ffffff`, text `#1f2328`). Tightened the reading column to max-width 720px. Highlight tints reworked for light bg (keep green, update amber, remove red with strikethrough, add_test purple) at ~10-13% opacity with hover bumps. Verdict tag chip kept (mono, uppercase, small) and stays quiet on light. Detail panel now `position: fixed` on the right with a soft left shadow, so the document layout does not change when the drawer opens.
- app/frontend/src/App.tsx -- header simplified to a single quiet meta line: `csv-stats / CLAUDE.md  ·  6 instructions  ·  4 runs  ·  -51 tokens` (no pill row). Detail panel is conditionally rendered, only mounted when an item is selected, with a close button (`x`, `aria-label="Close detail"`). Empty-state placeholder removed; first screen is just the source.
- app/frontend/tests/App.test.tsx -- relaxed the header assertion to a regex over the meta line. Renamed "nothing is selected on first render" to "first screen has no detail panel" and added a `data-testid="detail-panel"` assertion for the absence. Added a "close button dismisses the detail panel" case.

Decisions:

- Drawer over inline panel. A right-docked fixed drawer means the document keeps its column width before and after selection, so the page does not reflow when an item is clicked. Inline expanding cards under each highlight would reflow the document, which fights the "the source is the page" framing.
- Light theme over dark. The user's feedback was unambiguous; serif body type on warm paper matches the "this is a document being reviewed" framing better than the GitHub-dark default.
- Header de-pilled. Pills suggest a dashboard. A single mono caption line under the title reads as document metadata.
- Markdown stays raw. The source still renders as plain `pre-wrap` text (so `## Style` shows literally). Rendering markdown would require keeping offsets aligned across the transform, which is a meaningful piece of work and not on the critical path.

Note on parallel work: scout shipped Phase A.1 + A.2 (real Stage 3 extractor and demo-repo content) in entries above while this UI iteration was in flight. No interaction: scout's instructions.json is upstream of review-items.json and the SPA still reads only review-items.json + CLAUDE.md (D011 boundary intact). My UI tests run green against the existing fixture; when Stage 7 replaces the fixture with real review output, the SPA should render it without changes (ids will differ but tests read ids from disk).

Commands run (from `app/frontend/`):
- `npx vitest run` -> 12/12 passing.
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> CSS 3.75KB (gzip 1.34KB), JS 155KB (gzip 50KB).
- Dev server still up in tmux session `context-profiler` on http://127.0.0.1:5173/; HMR picked up the new styles.

Validation: 12/12 vitest, including the new "first screen has no detail panel" and close-button cases plus the real-artifact integration cases (sha256 + offset round-trip).

Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.
Blockers: none.
Next step: next user feedback. Likely candidates are markdown rendering with offset preservation, or the proposedChange diff in the drawer.

## 2026-05-10 First public deploy + CI workflow [runway]

Identity: runway (deploy/infra). Read assignment, CLAUDE.md, decisions.md, worklog. Goal: get the SPA live on a public URL so the assignment "deployed prototype" requirement has a real target, and wire CI so we don't hand-deploy on every change.

Decisions made:

- Host: Cloudflare Pages. Picked over GitHub Pages because the user already runs cleric.ai and aisre.com on Cloudflare; clean root URL (no `/<repo>/` subpath); no Vite `base` config change needed.
- Auth: none. Considered Cloudflare Access (free up to 50 seats, email-OTP scoped to @anthropic.com) and Pages-Functions basic-auth. User chose public.
- Project name: `context-profiler`. Production branch: `main`. URL: https://context-profiler.pages.dev.
- CI: `cloudflare/wrangler-action@v3` from `.github/workflows/deploy.yml`. Triggers: push to main + manual `workflow_dispatch`. Concurrency group `pages-deploy` with `cancel-in-progress: false` so two pushes don't race a half-uploaded deploy.
- Wrangler auth path: OAuth on the user's machine (cleared an expired token from Feb), and two GitHub secrets (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`) for CI. Account ID is `64a1d39e813787c2c3907db0d953d648`. The API token needs `Account:Read` + `Cloudflare Pages:Edit`; this is narrower than the user's local OAuth scopes on purpose.

Pre-flight findings:

- Wrangler 4.63.0 already installed via nvm node 22.
- Stale OAuth at `~/Library/Preferences/.wrangler/config/default.toml` (expired 2026-02-09). Refresh did not auto-recover, hence the prior 400 on whoami. Re-login fixed it.
- Existing Cloudflare account had one other Pages project (`domains-for-sale`); created `context-profiler` fresh with `wrangler pages project create --production-branch=main`.

Commands run:

- `cd app/frontend && npm run build` -> 33 modules, 155KB JS (50KB gzip), 3.75KB CSS, 268ms.
- `wrangler pages project create context-profiler --production-branch=main`.
- `wrangler pages deploy dist --project-name=context-profiler --branch=main --commit-dirty=true` -> uploaded 3 files in 1.47s. Preview URL `https://eb806209.context-profiler.pages.dev`, production alias `https://context-profiler.pages.dev`.
- `curl -o /dev/null -w "%{http_code}"` against production -> 200. HTML served with correct asset paths.

Files added:

- `.github/workflows/deploy.yml` -> checkout, setup-node@22 with npm cache rooted at `app/frontend/package-lock.json`, `npm ci`, `npm run build`, then `cloudflare/wrangler-action@v3` running `pages deploy app/frontend/dist --project-name=context-profiler --branch=main`.

Open items / next:

- The repo isn't on GitHub yet (this branch lives in a Conductor worktree). When it is pushed, two secrets need adding under repo settings -> secrets:
  - `CLOUDFLARE_API_TOKEN` (create at dash.cloudflare.com/profile/api-tokens with template "Edit Cloudflare Workers" scoped to the right account, or a custom token with Account:Read + Cloudflare Pages:Edit).
  - `CLOUDFLARE_ACCOUNT_ID` = `64a1d39e813787c2c3907db0d953d648`.
- First CI run will only fire after main is pushed; the manual `workflow_dispatch` can be used to validate end-to-end before relying on push triggers.
- Currently the deployed SPA renders the hand-written fixture, not real pipeline output. Once Stage 7 lands, no deploy change is needed: same `review-items.json` path, same SPA, same CI.

Validation: production URL returns 200 with the expected HTML and bundled asset references. CI workflow not yet validated end-to-end (no remote repo to push to).
Blockers: none for deployment. Pipeline and submission deliverables are still outstanding but are not in this scope.
Next step: when the user pushes the repo to GitHub, add the two secrets and trigger `workflow_dispatch` once to confirm the CI deploys cleanly.

## 2026-05-10 White, Inter, terse state labels [atlas]

Goal: refine annotation states. White (not warm paper) bg, Inter throughout, smaller calm colour vocabulary, no heavy boxes, inline label as a *terse phrase* (e.g. "seen 3/4", "not seen", "conflict", "add test") instead of repeating the verdict word.

Changes:

- app/frontend/index.html: load Inter (400/500/600/700) from Google Fonts with preconnect.
- app/frontend/src/styles.css: switched to white bg (`--bg #ffffff`). Body and source both Inter. Source is now sans-serif at 0.97rem / 1.72 line-height with -0.005em letter-spacing; max-width 720px stays. Highlight palette tightened to four calm tints (keep green `#2da657`, update amber `#b87f09`, remove muted gray `#6e7781`, add_test blue `#0969da`), each with a hover bump. Highlights now wrap the text itself with minimal vertical padding (0.05em) and no border-radius -- text-highlighter feel, no card. Removed the strikethrough on remove; the gray colour and muted text body is enough. Inline label is small uncoloured (per verdict) text after a `·` separator -- no background, no pill, just text. Detail drawer kept but lighter (no big shadows, smaller close `x`, tighter type). All badges in the drawer reduced to inline coloured text separated by `·` instead of pills.
- app/frontend/src/App.tsx: added `stateLabel(item)` that picks the most salient signal: `add_test` -> "add test"; `conflicting` flag -> "conflict"; `stale` flag -> "stale"; otherwise `supported` -> `seen N/M`, else "not seen". Highlight uses this label.
- app/frontend/tests/App.test.tsx: replaced the old "verdict tag" assertion with two: one against the small fixture (verifies `seen 1/1` for keep+supported and `stale` for remove+stale-flag), and a parameterised one that constructs three additional items to cover `add test`, `conflict`, and `not seen`.

Decisions:

- Colour by verdict, label by salient signal. The user's mapping ("keep/supported -> calm/green", "remove/unobserved -> muted/gray", "update/conflicting -> amber", "add_test -> blue or neutral") is a description of the *typical* pairing per verdict. Driving colour off `verdict` and surfacing the secondary axis through the label keeps the visual vocabulary at four colours (legible, cheap to learn) while still letting an unusual item (e.g. keep+unobserved) carry its real status in the label. This avoids combinatorial colour explosion.
- No legend. The labels are natural-language phrases ("seen 2/4", "conflict") so the meaning of the colour and the label is self-explanatory in context. If a future user finds it ambiguous I will add one.
- Verdict word dropped from the inline label. The label was redundant with the colour and read as a system tag; phrases read as commentary on the text and hold attention better.
- Inter via Google Fonts CDN. Simplest one-liner; no new npm dep. If we ever ship offline-only we can move to `@fontsource/inter`.

Visual verification: navigated to http://127.0.0.1:5173/ via playwright, screenshotted at 1280x900. Six items render with the expected colours and labels: Style "add test" (blue), Testing "seen 2/4" (green), UI "conflict" (amber), Deployment "stale" (gray), Logging "seen 2/4" (green), Security "not seen" (green; keep+unobserved).

Commands run (from `app/frontend/`):
- `npx vitest run` -> 13/13 passing.
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> CSS 4.10KB (gzip 1.42KB), JS 155KB (gzip 50KB).
- Dev server still up in tmux session `context-profiler` on http://127.0.0.1:5173/; HMR picked up the new styles.

Files changed: app/frontend/index.html, app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.
Blockers: none.
Next step: next user feedback.

## 2026-05-10 Audit cleanup: CLAUDE.md realism, anchor cursor, cache key, stale signal [scout]

Goal: address three correctness issues surfaced by a code audit of Phase A.1+A.2, plus rewrite demo-repo/CLAUDE.md to look more realistic (fewer sections, paragraph-level instructions, compound paragraphs that test the chunker's split logic).

Changes:

- demo-repo/CLAUDE.md: rewritten. Now 2 headings (# csv-stats, ## Deployment), 6 paragraphs. The logging+security paragraph contains two independent rules in one paragraph (tests chunker splitting). The Deployment section has two paragraphs: Jenkins (stale, contradicted by GHA) and version/tagging (current, grounded against pyproject.toml and .github/workflows/deploy.yml). Removed per-topic headings (## Style, ## Testing, etc.) to avoid the manufactured feel.
- demo-repo/.github/workflows/deploy.yml: new. Realistic GHA workflow (build wheel, publish to internal registry, render manifests, kubectl apply). Provides the competing deploy signal that the Jenkins instruction is stale against. Without this, the assessor had nothing in the codebase to ground "stale" on.
- demo-repo/tests/fixtures/sample.csv: new. Grounds the "reach for fixtures" rule in the Testing paragraph so it is not an accidental stale reference.
- demo-repo/tests/test_loader.py: added test_load_rows_reads_fixture using the new fixture.
- profiler/extract.py:
  - anchor() now takes `search_from` keyword arg. The caller in main() advances a cursor past each anchored span, preventing duplicate phrases from resolving to the wrong location.
  - cache_key() takes a fourth arg `prompt_bundle_str`. The prompt_bundle() function serializes SYSTEM_PROMPT + USER_PROMPT_RULES + EXTRACT_TOOL (JSON, sorted keys). Any prompt edit now invalidates the cache without requiring a manual PROMPT_VERSION bump.
  - USER_PROMPT_RULES extracted as a module constant so user_prompt() and prompt_bundle() share it.
- profiler/test_extract.py: added tests for prompt_bundle, anchor cursor (duplicate resolution + fallback with offset), updated cache_key tests for new signature. 15/15 passing.
- demo-repo/.profiler/instructions/instructions.json: regenerated (6 instructions, 0 fallbacks, new contextHash).
- demo-repo/.profiler/review/review-items.json: fixture updated to match new IDs, snippets, offsets, and contextHash. Verdicts: keep 3, update 1, remove 1, add_test 1. Flags: conflicting 1, stale 1.
- docs/decisions.md: D013 amended (cache key includes prompt_bundle, anchor uses source-order cursor).

Validation:
- profiler/test_extract.py: 15/15 passing
- demo-repo/ pytest: 8/8 passing (including new fixture test)
- app/frontend vitest: 13/13 passing (integration tests: sha256 matches, offsets round-trip, highlights render)

Files changed: demo-repo/CLAUDE.md, demo-repo/.github/workflows/deploy.yml, demo-repo/tests/fixtures/sample.csv, demo-repo/tests/test_loader.py, profiler/extract.py, profiler/test_extract.py, demo-repo/.profiler/instructions/instructions.json, demo-repo/.profiler/review/review-items.json, docs/decisions.md, docs/worklog.md.
Blockers: none.
Next step: Phase A.3 (one realistic task), then A.4 (Stage 5 SDK run).

## 2026-05-10 Cross-artifact integrity tests [warden]

Identity: warden (resilience/tests). Read assignment, CLAUDE.md, decisions.md (D001-D013), full worklog, the two committed schemas, and the five committed pipeline artifacts under `demo-repo/.profiler/`. Working in parallel with scout/atlas/runway; scoped strictly to *new files only* so no edits land on code those identities own (`profiler/extract.py`, `profiler/run_task.py`, `profiler/assess.py`, `profiler/cli.py`, `app/frontend/src/`, `.github/workflows/`, committed `.profiler/` artifacts).

Goal: lock the boundaries between pipeline stages so silent drift (orphaned evidence, mismatched ids, stale `contextHash`, summary out of sync with `items[]`, typo'd ablation variants) trips a test rather than landing in the UI.

Files added:

- `profiler/test_artifacts.py` -- 19 read-only tests over the committed artifacts. Covers:
  - Schema validation for `instructions.json` and `review-items.json`, plus a meta-test that the schemas themselves are valid Draft 2020-12. The pipeline validates `instructions.json` at write time; nothing else validated `review-items.json` until now.
  - Offset round-trip on both artifacts (`source.slice(start, end) == snippet`). Mirrors the SPA's integration assertion, lifted Python-side so it fires in CI without a browser.
  - `contextHash` freshness on both artifacts against the live `sha256(CLAUDE.md)`. The SPA tests this for `review-items.json` only; this also catches a stale `instructions.json` after a CLAUDE.md edit.
  - D013 stable-id formula compliance on every instruction and review item. Imports `stable_id` from `profiler.extract` read-only. A hand-edited snippet without id regeneration trips here, which is the same hazard that would orphan evidence downstream.
  - Cross-artifact id closure: `review-items.json` item ids and `instruction-evidence.json` instruction ids must be a subset of `instructions.json` ids. Catches the case where Stage 3 regenerates ids but Stages 6-7 hold stale ones.
  - Ablation `context_variant` references in both `sessions-index.json` and `instruction-evidence.json` must be either `"full"` or `"ablate:<existing-instr-id>"`. Typos in the ablation key currently mean evidence silently does not contribute; this surfaces them.
  - Summary consistency: `verdictCounts`, `statusCounts`, `flagCounts`, `totalInstructions` all match what you'd count from `items[]`, and `estimatedTokenChange == sum(items.tokenDelta)`.
  - Run-count consistency between `review.summary.totalRuns` and `sessions-index.sessions[]`.

Decisions:

- Cross-artifact integrity tests, not new schemas. Stages 4-6 emit four artifacts (`tasks.json`, `sessions-index.json`, `assessor-raw.json`, `instruction-evidence.json`) that do not yet have JSON schemas. Writing schemas is scout's call; the consistency tests give most of the protection without touching the contract surface.
- Closure tests are intentionally *subset* rather than *equality*. Future stages may legitimately drop an instruction id (e.g. when an unobserved item is filtered before review). Strict equality would generate false positives when that happens.
- No frontend changes. The `buildSegments` / `stateLabel` extraction I considered would have edited `app/frontend/src/App.tsx` (atlas's). Skipped to keep this slice strictly additive.

Commands run:
- `python3 -m pytest profiler/test_artifacts.py -v` -> 19/19 passing.
- `python3 -m pytest profiler/ demo-repo/ -q` -> 42/42 passing (15 extract helpers + 19 new artifact tests + 8 demo-repo).
- Frontend suite untouched; previously 13/13 (App.test.tsx).

Validation: all assertions hold on the current committed artifacts. Tests are deterministic, run in <0.1s, and have no LLM or network dependency.

Open items / future:
- Add a CI workflow that runs `python3 -m pytest` on push so these tests actually gate merges. There's a `.github/workflows/deploy.yml` already (runway); a sibling `test.yml` would not interfere but I am leaving that for the next coordinator to decide.
- If scout writes schemas for the remaining four artifacts, fold those into `test_schema_files_are_themselves_valid_draft_2020_12` and add per-artifact validation tests. Trivial extension.

Files changed: profiler/test_artifacts.py (new), docs/worklog.md (this entry).
Blockers: none.
Next step: hand back to coordinator. No further edits planned from this identity unless asked.

## 2026-05-10 Fixture regenerated against new CLAUDE.md [atlas]

Goal: clear the drift banner. After scout's content rewrite of `demo-repo/CLAUDE.md`, the SPA's drift detector fired and four integration tests broke (offsets pegged to the original file). User chose option B: regenerate the fixture to match the new file. Atlas's call on what to put in it.

What I rebuilt:

- `demo-repo/.profiler/review/review-items.json`. Six paragraph-level instructions matching the new CLAUDE.md, headings stripped per D003. New IDs under D013's scheme (`sha8(sourceFile + ":" + collapsed_snippet)`). All offsets round-trip (`text[start:end] === snippet`) and `contextHash` is sha256(CLAUDE.md) = `b07ce967...`.

Verdict mix (six items, totalRuns=4):

- `instr-40424d2c` style/lint -- add_test, supported 4/4. Type hints + pathlib observed, ruff clause is unenforceable; suggested test is a CI ruff gate.
- `instr-e7179979` testing -- keep, supported 2/4. Pytest workflow followed; property-based clause unobserved but defensive.
- `instr-cf4c5f0a` logging+redaction -- keep, supported 2/4. Logging clause exercised in 2 runs; secret redaction clause is unobserved (noted in `reason`).
- `instr-8ab40701` UI styling -- update, supported 1/4, [conflicting]. The Tailwind-vs-CSS-modules boundary is still ambiguous after the rewrite; agent fell back to "match the surrounding component". Replacement makes that the rule.
- `instr-2973b9bf` Jenkins deploy -- remove, unobserved 0/4, [stale, conflicting]. Stale relative to the repo (no `Jenkinsfile`, no `deploy/values.yaml`; `.github/workflows/deploy.yml` is now committed and active) and conflicting with the very next paragraph that points to GHA.
- `instr-8a9f6c8f` version-bump policy -- keep, unobserved 0/4. Defensive rule, no run cut a release.

Summary: verdictCounts `{keep:3, update:1, remove:1, add_test:1}`, statusCounts `{supported:4, unobserved:2}`, flagCounts `{conflicting:2, stale:1}` (Jenkins now has both flags), `estimatedTokenChange: -50`.

The Jenkins paragraph is more interesting in this iteration than in the original fixture: now it has *two* independent reasons to flag (filesystem + cross-paragraph contradiction), so the SPA shows it carrying both `stale` and `conflicting` -- a useful demo of multi-flag rendering.

Decisions:
- ID scheme: D013 (sourceFile + ":" + collapsed snippet, 8-hex). Forward-compatible with scout's Stage 7 output -- the schema just requires `^instr-[0-9a-f]{8}$`.
- Token estimates: rough 4-chars-per-token approximation. Stage 6 will produce accurate counts; this is fine for the fixture.
- Did not regenerate `demo-repo/.profiler/instructions/instructions.json` (scout's stage-3 output). Touching it would step on scout's pipeline ownership; their parallel work was already going to rerun it.

Validation:
- offset round-trip: 6/6 spans match `source.slice(start, end)` exactly.
- ID uniqueness: ok.
- Schema-shape: ok (matches `profiler/schemas/review-items.schema.json`).
- `(cd app/frontend && npx vitest run)`: 13/13 passing including `real CLAUDE.md hash matches review.source.contextHash` and `review items' offsets map to real CLAUDE.md spans`.
- Visual check: navigated to http://127.0.0.1:5173/ via playwright. Drift banner gone. Six highlights render with the expected verdict colours and labels: "add test", "seen 2/4", "seen 2/4", "conflict", "stale", "not seen".

Note on commit attribution: `demo-repo/.profiler/review/review-items.json` was picked up by a parallel agent's "Audit cleanup" commit (3d9ca33) alongside their pipeline regeneration. The committed file is exactly the one atlas wrote (their worklog narrative says `conflicting: 1` but the data on disk -- and what is rendering live -- has `conflicting: 2`, which is atlas's intended structure). Working tree is clean.

Files changed: docs/worklog.md (this entry). The fixture itself was already committed in 3d9ca33.
Blockers: none.
Next step: nothing pending.

## 2026-05-10 Contextual popover replaces side drawer [atlas]

Goal: replace the fixed side drawer with a contextual popover anchored near the clicked highlight. The popover answers four questions: what is the recommendation, why, what evidence, what action.

Changes:

- app/frontend/src/App.tsx:
  - Removed `Detail` component (fixed side drawer).
  - Added `Popover` component: anchored below the highlight's bounding rect via `position:fixed` + `getBoundingClientRect()`. Flips above if the viewport bottom is < 220px away.
  - Popover content: title + verdict label (top row), reason, one strongest evidence excerpt (italic, with attribution label), action section (replacement/suggestedTest code block + verdict-specific button).
  - Dismiss via: Escape key, or mousedown anywhere outside the popover. Clicking another highlight while a popover is open naturally switches to it (mousedown dismisses the old popover, then click opens the new one).
  - Removed backdrop div after discovering it blocked clicks on other highlights (Playwright caught this, vitest did not because fireEvent.click does not respect z-index).
- app/frontend/src/styles.css: replaced side-drawer styles with popover styles. 380px wide, 8px border-radius, subtle shadow. Evidence block is a soft gray background. Action button is full-width, verdict-colored border, minimal style.
- app/frontend/tests/App.test.tsx: 16 tests. New popover-specific cases: "opens with title/reason/evidence", "shows action button when proposedChange exists", "no action button for keep", "no popover on first render", "clicking outside dismisses", "clicking a different highlight switches". Evidence items added to the test fixture (previously empty arrays).

Decisions:
- mousedown-on-document over backdrop. A backdrop blocks clicks on all highlights behind it, forcing dismiss-then-reclick. The mousedown listener dismisses cleanly on outside clicks and lets highlight clicks propagate in sequence (mousedown dismisses old, click opens new). The backdrop was the initial implementation; Playwright's click interception errors caught the real-browser failure that vitest missed.
- One evidence excerpt (evidence[0]). The contract doesn't rank evidence by strength; showing the first keeps the popover compact. If ranking becomes available, swap to the highest-ranked.
- Action buttons are non-functional (no accept/reject flow in v0). They show the affordance and the proposed content (replacement text or suggested test). Wiring them to produce a patched CLAUDE.md is a natural next step.

Visual verification (playwright screenshots):
- add_test popover: title, "ADD TEST" label (blue), reason, evidence excerpt with label, suggested CI check in code block, "Add test" button.
- remove popover: title, "REMOVE" label (gray), reason mentioning stale Jenkins + missing files, evidence ("zero tool calls"), "Remove instruction" button.
- Escape dismissal: popover closes, document returns to clean state.

Commands run:
- `npx vitest run` -> 16/16 passing.
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> CSS 4.71KB (gzip 1.53KB), JS 160KB (gzip 51KB).
- Dev server still up in tmux `context-profiler` on http://127.0.0.1:5173/.

Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.
Blockers: none.
Next step: next user feedback.

## 2026-05-10 Pill chips + right-gutter popover [atlas]

Goal: match the reference chip image (pill-shaped, colored bg, "seen 2/2 runs" format) and move the popover from overlapping the document to the right gutter.

Changes:

- app/frontend/src/styles.css: `.hl-tag` restyled as pill chip (border-radius 999px, colored background matching verdict tint, colored text, 0.55em horizontal padding). Removed the `::before` `·` separator. `.popover` max-height removed from CSS (now computed inline to fit viewport). No other popover style changes.
- app/frontend/src/App.tsx:
  - `stateLabel` appends "runs" to seen counts: "seen 2/4 runs" instead of "seen 2/4".
  - Added `articleRef` on the source `<article>`. On highlight click, capture `article.getBoundingClientRect().right` as `gutterLeft` alongside the highlight rect.
  - `popoverStyle` rewritten: positions in the right gutter (`left: gutterLeft + 16px`) aligned to the top of the highlight. If gutter width < 240px, falls back to right-aligned overlay (only crosses text on narrow viewports). `maxHeight` computed from viewport.
  - Fixed header grammar: "1 run" vs "4 runs" (was "1 runs").
- app/frontend/tests/App.test.tsx: updated "seen 1/1" to "seen 1/1 runs". Scoped header test to the meta span to avoid ambiguity with chip text.

Decisions:
- Popover width 320px (was 380px). On a 1280px viewport with the 680px source column, the right gutter is ~300px. 320px popover slightly overlaps the text column edge by 20px on 1280; fits fully on 1440+. On < 1100px the popover falls back to viewport-right-aligned.
- "runs" suffix on the seen label. The reference image shows "seen 2/2 runs", so all observed counts now include "runs". Non-count labels (stale, conflict, add test, not seen) are unchanged.

Commands run:
- `npx vitest run` -> 16/16 passing.
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> CSS 4.79KB (gzip 1.53KB), JS 158KB (gzip 51KB).

Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.
Blockers: none.
Next step: next user feedback.

## 2026-05-10 Phase A.5-A.7: assessor pipeline end-to-end [scout]

Goal: replace the hand-written review-items.json with real pipeline output. Build Stage 6+7 (Opus assessor) and Stage 5 plumbing (sessions index).

Changes:

- profiler/assess.py (new): reads instructions.json + SDK event traces + repo file listing, calls Opus once with all 6 instructions, forced tool_use for structured output. Writes sessions-index.json (A.5), assessor-raw.json + instruction-evidence.json (A.6), and review-items.json (A.7). Schema-validates output against review-items.schema.json. Cache keyed on source_hash + instruction ids + session ids + model.
- profiler/run_task.py: fixed ToolUseBlock serialization (attributes are `name`/`input`, not `tool_name`/`tool_input`).

Assessor verdicts (Opus 4.7, 1 session):
- instr-40424d2c style/lint: keep, supported. Agent ran ruff in this trace.
- instr-e7179979 testing: update, supported, [conflicting]. Agent invented a new fixture instead of reusing existing ones; property-based tests clause ungrounded.
- instr-cf4c5f0a logging+redaction: keep, supported. Both logging clauses followed.
- instr-8ab40701 UI styling: remove, unobserved, [stale]. No frontend code in repo.
- instr-2973b9bf Jenkins deploy: remove, unobserved, [stale, conflicting]. No deploy/values.yaml, no Jenkinsfile, GHA workflow exists.
- instr-8a9f6c8f version/tags: add_test, unobserved. Anchors exist but adherence is unenforceable.

Verdict distribution: keep 2, update 1, remove 2, add_test 1. Token delta: -56.

Validation:
- review-items.json passes jsonschema Draft202012 validation.
- Frontend vitest: 16/16 passing (integration tests: sha256 matches, offsets round-trip, highlights render).
- UI confirmed via Playwright: all 6 instructions render with correct verdict colors and labels. Detail popover shows real assessor reasoning.

Files changed: profiler/assess.py, profiler/run_task.py, demo-repo/.profiler/review/review-items.json, demo-repo/.profiler/attribution/{assessor-raw.json, instruction-evidence.json}, demo-repo/.profiler/traces/sessions-index.json, demo-repo/.profiler/stages/assess.cache.json, docs/worklog.md.
Blockers: none.
Next step: Phase C (one targeted ablation).

## 2026-05-10 Popover redesign: structured sections, action near top [atlas]

Goal: match the Figma mock. The popover had too much text, no visual hierarchy, and the action button was buried below the fold. Redesigned to match the structured layout the user mocked: status dot + close at top, title + chip, then labeled sections (RECOMMENDATION, WHY, EVIDENCE) with the action button in the first section.

Changes:

- app/frontend/src/App.tsx: Popover component rewritten:
  - Top row: `● OBSERVED` / `○ UNOBSERVED` status dot (left), verdict label (right), close `×` button (far right).
  - Title: bold, tight leading.
  - Chip: terse state label in muted text below title.
  - RECOMMENDATION section (first, closest to click point): for keep items shows "Keep as-is.", for non-keep items shows replacement/suggestedTest code and action button.
  - WHY section: reason text, line-clamped to 4 lines via CSS.
  - EVIDENCE section: first evidence excerpt + source label. "Show evidence (N events)" link when more than one evidence item.
  - Close button wired to `onClose` prop.
- app/frontend/src/styles.css: Popover restyled:
  - Clean outline border (1px solid, 10px radius, very light shadow) instead of heavy drop shadow.
  - No internal padding on the container; each section has its own padding and a top border divider.
  - Small-caps section headers (RECOMMENDATION, WHY, EVIDENCE) in muted color.
  - WHY text line-clamped to 4 lines.
  - Code blocks max-height capped to ~4 lines.
  - Status dot colored: green for supported, gray for unobserved.
- app/frontend/tests/App.test.tsx: 17 tests. New/updated: "opens a popover with structured sections" (checks for RECOMMENDATION, WHY, EVIDENCE labels), "keep item shows Keep as-is.", "close button dismisses". All existing tests updated for the new structure.

Decisions:
- Action near the top. The user's feedback: "buttons should be near the top, so that it's close to your mouse when you click a snippet of text." RECOMMENDATION is the first section after the title, so the action button is within ~80px of the top of the popover.
- Line-clamped WHY. The contract's `reason` field can be 3-4 sentences. Clamping to 4 lines keeps the popover compact. Full text available in a future detail view.
- "Show evidence (N events)" as a link, not expanded. Keeps the popover short. Expanding is a future feature.

Commands run:
- `npx vitest run` -> 17/17 passing.
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> CSS 5.68KB (gzip 1.71KB), JS 159KB (gzip 51KB).

Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.
Blockers: none.
Next step: next user feedback.

## 2026-05-10 Fix orphaned chip drop + re-sync fixture [atlas]

Goal: fix the "weird dropping" — the chip label sat alone below the title as an orphaned word ("conflict", "stale"), and the fixture was out of sync with CLAUDE.md (modified by a parallel agent again).

Changes:

- app/frontend/src/App.tsx: merged the chip (stateLabel) into the top status row of the popover. Layout is now: `● OBSERVED · seen 2/4 runs   ×` on one line, then the title below. Removed the separate verdict label from the top row (the RECOMMENDATION section communicates the action). Removed unused `verdictLabel` function.
- app/frontend/src/styles.css: `.po-chip` moved to flex with `margin-left: auto` in the top row. Removed `.pv-*` verdict color classes (no longer used in the popover).
- demo-repo/.profiler/review/review-items.json: regenerated against the current CLAUDE.md (sha256:4c0a2142...) which now has 8 instruction paragraphs (two new: "patch" about narrow changes, "errors" about domain exceptions). All offsets verified round-trip. Verdicts: keep:5, update:1, remove:1, add_test:1. Flags: conflicting:2, stale:1. tokenDelta:-50.

The parallel agent keeps modifying demo-repo/CLAUDE.md. Each time they do, the fixture drifts and integration tests break. This is the third regeneration. The worklog records it; moving on.

Commands run:
- `npx vitest run` -> 17/17 passing.
- `npx tsc --noEmit` -> clean.
- `npx vite build` -> CSS 5.43KB (gzip 1.68KB), JS 160KB (gzip 51KB).

Files changed: app/frontend/src/{App.tsx,styles.css}, demo-repo/.profiler/review/review-items.json, docs/worklog.md.
Blockers: none.
Next step: next user feedback.

## 2026-05-10 Popover higher, no clipping [atlas]

Goal: popover was positioned too low and content was cut off by maxHeight + line-clamp. User wants it higher and all content visible.

Changes:
- app/frontend/src/App.tsx: removed `maxHeight` from popoverStyle inline return. Nudged top position up 8px (`rect.top - 8` instead of `rect.top`).
- app/frontend/src/styles.css: removed `overflow-y: auto` from `.popover`, removed `-webkit-line-clamp` from `.po-why`, removed `max-height` + `overflow: hidden` from `.po-code`. All content now renders fully.

Commands: vitest 17/17, tsc clean.
Files changed: app/frontend/src/{App.tsx,styles.css}, docs/worklog.md.

## 2026-05-10 Expand CLAUDE.md + Phase C ablation [scout]

Goal: make the demo CLAUDE.md more realistic (larger, fewer headings, opening paragraph assessed) and add one targeted ablation to demonstrate causal attribution.

CLAUDE.md expansion:
- Renamed heading to `# CLAUDE.md` (was `# csv-stats`).
- Added 3 new instruction paragraphs: repo orientation (mentions legacy `src/admin/` scaffold), workflow guidance ("keep patches narrow"), error handling (`csvstats.errors` which doesn't exist -- stale signal).
- Removed `## Deployment` heading so content flows as paragraphs.
- Updated extractor: rule 3 (skip opening) removed so all paragraphs get assessed. PROMPT_VERSION bumped to 2.
- Pipeline re-run: 9 instructions extracted (0 fallbacks), 6 original stable IDs preserved. Assessor: keep 3, update 3, remove 2, add_test 1. Token delta -97.

Phase C ablation:
- Target: logging instruction (instr-cf4c5f0a), chosen because the full-context run showed the agent following it.
- Method: `profiler/run_task.py --ablate instr-cf4c5f0a` removes the instruction from CLAUDE.md before copying to workspace, records `context_variant: "ablate:instr-cf4c5f0a"` in result.json.
- Finding: agent produced identical code in both runs. `load_tsv` used `logger.error(exc_info=True)` even without the logging instruction, because the existing `load_rows` already demonstrates the pattern. The instruction is redundant with the codebase convention.
- Assessor updated to handle multiple sessions with context_variant labels. Ablation runs are annotated in the prompt. Evidence kind "ablation" added. The assessor correctly identified: "Even with the instruction removed, the agent followed surrounding code style and used logger, indicating the convention is reinforced by existing code."

Validation:
- profiler/test_extract.py: 15/15 passing
- demo-repo/ pytest: 8/8 passing
- app/frontend vitest: 17/17 passing
- UI confirmed rendering 9 instructions with ablation evidence in the detail popover.

Files changed: demo-repo/CLAUDE.md, profiler/extract.py, profiler/run_task.py, profiler/assess.py, demo-repo/.profiler/{instructions,review,attribution,traces,stages,runs}/*.json.
Blockers: none.
Next step: README/submission deliverables.

## 2026-05-10 Show all evidence inline, ablation visible by default [atlas]

Goal: ablation evidence should be visible without clicking. Previously only evidence[0] was shown; ablation was hidden behind "Show evidence (N events)" which wasn't wired.

Changes:

- app/frontend/src/App.tsx: evidence section now iterates all items, not just evidence[0]. Ablation items get a "ABLATION" kind label. Removed unused `best` variable and the "Show evidence" link.
- app/frontend/src/styles.css: added `.po-ev` wrapper with bottom margin for spacing between evidence items. Ablation items (`.po-ev-ablation`) get a left blue border to distinguish them. `.po-ev-kind` is a small uppercase label. Removed `.po-ev-more` styles.
- app/frontend/tests/App.test.tsx: added `evAblation` to the keep item's evidence array. New test: "shows all evidence items inline, ablation evidence labeled" verifies both trace and ablation excerpts render, and the "ABLATION" label is present.

Commands: vitest 18/18, tsc clean.
Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.

## 2026-05-10 Review decisions (local state) [atlas]

Goal: let users accept, leave unchanged, or clear review decisions per item. Local UI state only, no disk persistence.

Changes:

- app/frontend/src/App.tsx:
  - Added `decisions` state: `Record<string, string>` mapping item id to the accepted action kind.
  - `decide(id, action)` sets a decision; `clearDecision(id)` removes it.
  - Popover RECOMMENDATION section: when no proposedChange (keep without proposedChange), shows "Keep as-is." with no action row. When proposedChange exists and no decision, shows action button ("Mark for removal" / "Mark for update" / "Mark to add test"). When decided, shows a green confirmation row ("Marked for removal") with a "Clear" button to undo.
  - Highlight gets a `decided` prop; when true, adds `.decided` class for a visual indicator.
  - Renamed `actionButtonLabel` to `actionLabel`, added `decidedLabel`.
- app/frontend/src/styles.css:
  - `mark.hl.decided`: dashed green outline to indicate a decision was made on that highlight.
  - `.po-decided`: flex row with green-tinted background, "Marked for X" label, and a "Clear" button aligned right.
- app/frontend/tests/App.test.tsx: 21 tests. New: "clicking action button accepts the decision", "clearing a decision returns to undecided state", "decided items show indicator on highlight". Updated: action button text from "Remove instruction" to "Mark for removal" per new label scheme.

Decisions:
- No separate "leave unchanged" button. The default is no decision; the user only acts when they want to accept the recommendation. This matches the PR-review pattern (no action = no opinion).
- Decision state is `Record<string, string>` keyed by item id. The value is the proposedChange kind (remove/update/add_test). This is enough for now; disk persistence will need a richer shape (e.g., user-supplied replacement text for update decisions).
- Decided highlight indicator is a dashed green outline. Subtle enough not to compete with the verdict highlight color.

Commands: vitest 21/21, tsc clean.
Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.
Blockers: none.
Next step: next user feedback.

## 2026-05-10 Compact in-column header with run statistics [atlas]

Goal: move the header into the same column as the document body, remove the full-width separator, and quietly surface key run statistics to ground the reviewer.

Changes:

- app/frontend/src/App.tsx: replaced the full-width `<header>` with a `DocHeader` component rendered as the first child of the `<article>`. It flows with the document and shares its max-width/padding. Shows:
  - Title: "Context Profiler"
  - Path: repo / file in monospace
  - Summary line: instruction count, run count, verdict breakdown (3 keep, 3 update, 2 remove, 1 add test)
  - Details line (smaller, more muted): observed/unobserved counts, flag counts, token impact, generation date
  - Drift indicator (if applicable)
  - Drift banner also moved inside the article, styled as a compact inline alert.
- app/frontend/src/styles.css: removed `header.top` and associated full-width styles. Added `.doc-header` with block-level children, progressively smaller/more muted text for each line. Drift banner restyled as a small rounded box inside the column.
- app/frontend/tests/App.test.tsx: updated header test to check for verdict counts in the document content. Drift test updated for new banner text.

Commands: vitest 21/21, tsc clean.
Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.

## 2026-05-10 Review flow: progress bar, navigation, summary [atlas]

Goal: make the review journey obvious. Progress indicator, Next/Previous to step through reviewable items, completion state, and a summary screen as the payoff.

Changes:

- app/frontend/src/App.tsx:
  - `reviewable`: items with `proposedChange`, sorted by source offset. `decidedCount` and `allReviewed` derived from decisions state.
  - `navigateTo(id)`: finds the highlight by data-testid, scrolls it into view, opens its popover.
  - `navigateNext` / `navigatePrev`: find the next/previous undecided reviewable item (wraps around).
  - `ReviewBar` component: sticky bottom bar with a thin progress track (green fill), count text ("2 of 5 reviewed"), and Previous/Next buttons. When all items decided, shows "Review complete" with a "View summary" button.
  - `Summary` component: shown when "View summary" is clicked. Lists each reviewable item with a checkmark or dash, the action taken, and total token impact. "Back to review" returns to the document.
  - `showSummary` state toggles between document and summary views.
- app/frontend/src/styles.css: added `.review-bar` (sticky bottom, same column width as document), `.rb-*` inner styles (progress track, buttons), `.summary` and `.summary-*` (centered card with item list).
- app/frontend/tests/App.test.tsx: 26 tests. New review flow cases: "shows review bar with progress", "Next navigates to first undecided item", "shows completion when all decided", "View summary shows decisions", "Back to review returns to document".

Decisions:
- Only items with `proposedChange` are reviewable. Keep items without proposedChange need no decision.
- Navigation uses `document.querySelector` to find highlights by data-testid. Pragmatic for v0; avoids a ref map. `scrollIntoView` is guarded with optional chaining for jsdom compatibility.
- The review bar uses the same max-width as the document column (800px) so it doesn't feel like a separate UI layer.
- Summary is a full-page replacement, not an overlay. Clean transition. "Back to review" returns to the document with decisions preserved.

Commands: vitest 26/26, tsc clean.
Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.

## 2026-05-10 Start Review flow, auto-advance, top controls [atlas]

Goal: rework the review journey per user feedback. Bottom bar was weird and disconnected. Popovers were clipping off-screen for bottom items. No clear entry point or payoff.

Changes:

- app/frontend/src/App.tsx:
  - Removed `ReviewBar` (sticky bottom bar). Replaced with `ReviewControls` rendered inline in the doc header.
  - Three review states: not started (green "Start Review" button + "N items to review" hint), in progress (progress bar + count + Next button), complete ("Review complete" + "Accept changes" / "Reset" buttons).
  - "Start Review" navigates to the first reviewable item and opens its popover.
  - Auto-advance: a useEffect watches `decisions`. When the current popover's item gets decided, it auto-navigates to the next undecided item after 350ms (brief confirmation flash). If all decided, dismisses the popover.
  - "Accept changes" goes to the summary screen. "Reset" clears all decisions and returns to the Start state.
  - Popover positioning fix: `top` is now capped at `window.innerHeight - 480` so the popover never clips below the viewport for bottom-of-page items.
  - Removed `navigatePrev` (not needed with auto-advance flow).
- app/frontend/src/styles.css: replaced `.review-bar` / `.rb-*` with `.rc` / `.rc-*` (inline review controls). Green "Start Review" button. Progress bar is 80px wide (compact). "Accept changes" button is green. Removed all sticky/fixed bottom bar styles.
- app/frontend/tests/App.test.tsx: 26 tests. Updated review flow tests: "Start Review button before review begins", "Start Review opens popover on first item", "completion after deciding all items", "Accept changes shows summary", "Reset clears and returns to Start".

Decisions:
- Auto-advance on decision, not on explicit Next. The user said "when you click mark for update, it should automatically move you to the next item." The 350ms delay lets the user see the "Marked for..." confirmation before advancing.
- "Next" button is still available during review for skipping an item without deciding.
- No Previous button. The review is forward-moving. Users can click any highlight to revisit.
- Popover top capped at `innerHeight - 480`. Ensures at least the title and recommendation section are visible for items near the bottom of the viewport.
- "Accept changes" leads to the existing summary screen. Diff preview is the next iteration.

Commands: vitest 26/26, tsc clean, vite build ok.
Files changed: app/frontend/src/{App.tsx,styles.css}, app/frontend/tests/App.test.tsx, docs/worklog.md.

## 2026-05-10 Skip completes review, run counts on all labels [atlas]

Goal: skipping all items should complete the review. All chip labels should show run counts.

Changes:

- app/frontend/src/App.tsx:
  - Added `skipped` state (Set<string>). Skip button adds the item to the skipped set (was just calling navigateNext without tracking). Auto-advance fires on skip too.
  - `reviewedCount` = decided + skipped. `allReviewed` checks reviewedCount === totalCount. `findNextUndecided` skips both decided and skipped items. Reset clears skipped set.
  - `stateLabel` now appends run counts to all labels: "stale · 0/4 runs", "conflict · 1/4 runs", "add test · 4/4 runs", "not seen · 0/4 runs". Previously only "seen X/Y runs" had counts.
  - Summary receives `skipped` set; shows "Skipped" vs "Not reviewed" for undecided items.
  - Renamed `decidedCount` to `reviewedCount` throughout.
- app/frontend/tests/App.test.tsx: 27 tests. New: "skipping all items completes the review". Updated stale label assertion to include run count.

Commands: vitest 27/27, tsc clean.
Files changed: app/frontend/src/App.tsx, app/frontend/tests/App.test.tsx, docs/worklog.md.

## 2026-05-10 Popover readability, positioning fix, copy action [atlas]

Goal: improve popover readability (text too small), fix popover clipping at viewport bottom, add "Copy updated CLAUDE.md" action to summary.

Changes:

- app/frontend/src/styles.css: bumped all popover font sizes. Body text from 0.82rem to 0.88rem. Code blocks from 0.72rem to 0.78rem. Section headers from 0.6rem to 0.65rem. Title from 0.92rem to 1rem. Evidence text from 0.8rem to 0.86rem. Buttons from 0.76rem to 0.82rem. Increased internal padding throughout (0.85rem to 1rem horizontal, more vertical spacing between sections). Status line and chip from 0.65rem to 0.7rem.
- app/frontend/src/App.tsx:
  - Popover width from 320px to 360px to accommodate larger text.
  - Popover top position now capped at `innerHeight * 0.35` (was `innerHeight - 480`). This ensures the popover always starts in the upper third of the viewport regardless of where the highlight is.
  - Added `applyDecisions(source, items, decisions)`: walks decided items in reverse offset order, applies removals (including trailing newlines) and replacements. Returns the patched CLAUDE.md text.
  - Summary component receives `source` prop. "Copy updated CLAUDE.md" button computes the patched text and copies to clipboard. Shows "Copied!" confirmation for 2 seconds.

Commands: vitest 27/27, tsc clean.
Files changed: app/frontend/src/{App.tsx,styles.css}, docs/worklog.md.
