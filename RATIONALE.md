# Design Rationale

**Theme**: 4 (Evaluation & Data Quality)
**Time spent**: ~4 hours
**Live demo**: https://context-profiler.pages.dev

## Why this theme and this specific approach

I find it genuinely hard to clean up prompts and instructions, especially in a team environment where the original context behind each instruction gets lost over time. Someone adds a rule to a CLAUDE.md or a system prompt because it solved a problem last month. Six months later nobody remembers why it's there, whether the agent actually follows it, or whether it contradicts something added since. So it stays. Everything stays.

This is a real problem I run into regularly. What I need is a data-driven way to know when context can be cleaned up. Not a linter that checks syntax, but something that looks at what the agent actually did and tells me which instructions are doing work, which are dead, and which are fighting each other. And this applies to any context injected into an agent: CLAUDE.md files, system prompts, skills, tool descriptions, memory entries, even the set of tools an agent has access to.

The insight that made this buildable in a few hours is that the evidence already exists. Every agent session produces a detailed trace: files read, code written, commands run, decisions made. Every trace is implicitly an evaluation of every instruction the agent was given. Teams produce this data continuously and throw it away.

## Approaches considered and eliminated

I surveyed five method families and considered five concrete prototypes before selecting the approach:

**ContextCite-style sparse surrogates** (P3). Train a lightweight linear model that approximates per-token attribution by masking context spans. Produces fine-grained attribution scores. Eliminated because it requires white-box model access (logprobs at minimum, ideally activation access), which rules out API-only deployments. Most teams using Claude, GPT, or similar models cannot use this.

**Deterministic rule auditors** (P2). Build per-instruction compliance checkers (regex matchers, AST checks, test harnesses) that score each rule against agent output. Produces quantitative compliance rates. Eliminated because it requires custom checker logic per instruction type, which doesn't scale to the variety of instructions in real CLAUDE.md files (style rules, deployment procedures, security guidance, workflow conventions). The maintenance cost of the checkers would exceed the value.

**Static conflict/redundancy linting** (P4). Use an LLM to analyze the CLAUDE.md for internal contradictions and redundancy without running any tasks. Eliminated because it has no behavioral evidence. It can catch syntactic conflicts ("use Tailwind" vs "use CSS modules") but cannot tell you whether either instruction actually influences agent behavior. A static linter would flag dead instructions as conflicting when the real finding is that neither one matters.

## Approaches chosen

**LLM-as-judge over traces** is the baseline. An assessor model reads the agent's execution trace alongside each instruction and judges whether the instruction was followed, ignored, or contradicted. This is the most tractable entry point: most teams already have traces (or can start collecting them), and a single LLM call per instruction produces actionable verdicts. No special model access, no logprobs, no white-box techniques required.

**Targeted ablation** is the extension. Remove one instruction from the context, re-run the same task, compare the traces. This produces directional causal evidence rather than correlation. It costs one additional agent run per instruction tested, which is affordable for teams already running agents frequently. I chose ablation over logprob attribution and attention analysis because it works with any model behind any API.

**Task generation** is a natural complement. Rather than requiring teams to bring their own traces, the pipeline can generate realistic tasks for a repo, run them, and produce traces on demand. The prototype defines tasks manually, but the methodology supports automated task generation as an input stage.

## Key design decisions

- **Document-first review UI**. The strongest UX decision. The CLAUDE.md itself is the canvas: instructions are highlighted inline by verdict, and clicking a span opens evidence and actions in a popover. This keeps the user grounded in the original context instead of forcing them into an abstract table of findings. The evidence and recommended actions attach directly to the instruction text, so the user never loses sight of what they're evaluating.

- **Verbatim snippets with byte offsets**. The extractor returns exact source spans, anchored back to the file with offset validation (`source[start:end] === snippet`). The UI highlights the actual text, and every finding points at a real location in the source.

- **Control pairs for ablation**. Each task is run twice with full context to establish a noise floor. Without this, any behavioral difference in an ablation run could be model nondeterminism rather than a causal effect of removing the instruction.

- **Synthetic demo with known ground truth**. The demo CLAUDE.md is constructed to exercise each verdict path. This is a controlled test environment, not an evaluation against unknown inputs. I validated the methodology against known answers before pointing it at unknown ones.

## Tradeoffs

- **LLM-as-judge vs. deterministic checkers**: verdicts are qualitative judgments, not quantitative measurements. No inter-rater reliability or rubric calibration. I chose this because it handles the full range of instruction types without needing per-instruction checker logic.

- **n=1 ablations vs. statistical rigor**: each instruction is ablated once against one task. Meaningful causal claims would require multiple seeds averaged across tasks. I chose full coverage (9/9 instructions ablated) over depth (many seeds on a few instructions) because coverage demonstrates the methodology more clearly for a prototype.

- **Offline pipeline vs. online profiling**: the pipeline runs against pre-defined tasks, not live sessions. I chose offline because it's self-contained and reproducible for evaluation.

## How I would extend this

With more time, in order of impact:

1. **Run against a real CLAUDE.md** from an uncontrolled project. The synthetic demo validates the machinery. Real inputs validate the approach.
2. **Multi-seed ablations** (N=5 per instruction per task) with agreement rates. "Removing X changed behavior in 4/5 runs" is a real claim.
3. **Broader scope**: profile skills, tool descriptions, memory stores, entire repo-level context bundles. Anything injected into an agent as context can be attributed using the same methodology. The unit of analysis is always "a piece of text that was present when the agent ran."
4. **Online profiling** with shadow agents running ablated variants alongside production. Continuous causal attribution without blocking users.
