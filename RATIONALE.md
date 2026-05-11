# Design Rationale

**Theme**: 4 (Evaluation & Data Quality)
**Time spent**: ~4 hours
**Live demo**: https://context-profiler.pages.dev

## Why this theme and this specific approach

AI agents accumulate context from many sources: system prompts, CLAUDE.md files, skills, tool descriptions, memory entries, retrieved documents. Each piece was added because it solved a problem at some point. Over time, nobody remembers why a given instruction is there, whether the agent actually follows it, or whether it contradicts something added since. So it stays. Everything stays.

This is a real problem I run into regularly. What I need is a data-driven way to know which context is doing work and which can be cleaned up. Not a linter that checks syntax, but something that looks at what the agent actually did and tells me which instructions influenced behavior, which are dead, and which are fighting each other.

## What makes this non-obvious

The key insight is that the evidence already exists. Every agent session produces a detailed trace: files read, code written, commands run, decisions made. Each trace is implicitly an evaluation of every piece of context the agent was given. Teams produce this data continuously and throw it away.

Context Profiler treats agent traces as evaluation data. Instead of building custom eval harnesses or requiring white-box model access, it uses the behavioral record that agents already produce to attribute outcomes back to specific context.

The second non-obvious piece is using ablation as a black-box causal test. Remove one instruction, re-run the same task, compare traces. This gives you directional causal evidence ("removing this instruction changed behavior") without needing logprobs, attention weights, or any model internals. It works with any model behind any API.

## Why CLAUDE.md as the prototype scope

The methodology applies to any injected context, but CLAUDE.md is the right starting point for a prototype: it's a plain text file checked into the repo, it's read by Claude Code on every session, and its instructions are paragraph-sized units that map cleanly to an extract/assess/ablate loop. Building the full pipeline end-to-end for one context source validates the approach before extending to system prompts, tool descriptions, memory, or skills.

## Approaches eliminated

**[ContextCite](https://arxiv.org/abs/2409.00729)-style sparse surrogates**. Train a lightweight linear model that approximates per-token attribution by masking context spans. Produces fine-grained attribution scores, but requires white-box model access (logprobs at minimum). Most teams using Claude, GPT, or similar models via API cannot use this.

**Deterministic rule auditors**. Build per-instruction compliance checkers (regex, AST checks, test harnesses) that score each rule against agent output. Requires custom checker logic per instruction type. The variety of instructions in real context files (style rules, deployment procedures, security guidance, workflow conventions) makes maintenance cost exceed value.

**Static conflict/redundancy linting**. Use an LLM to analyze context for internal contradictions without running any tasks. No behavioral evidence: it can catch syntactic conflicts ("use Tailwind" vs "use CSS modules") but cannot tell you whether either instruction actually influences agent behavior. A static linter would flag dead instructions as conflicting when the real finding is that neither one matters.

## Methodology

**LLM-as-judge over traces** is the baseline. An assessor model reads the agent's execution traces alongside each extracted instruction and judges whether it was followed, ignored, or contradicted. Most teams already have traces (or can start collecting them), and a single assessment pass produces actionable verdicts for the full context file. No special model access required.

**Targeted ablation** is the causal extension. Remove one instruction from the context, re-run the same task, compare traces. This produces directional evidence rather than correlation. It costs one additional agent run per instruction tested.

**Control pairs** establish a noise floor for ablation. Each task is run twice with full context before any ablation runs. Without this, behavioral differences in an ablation run could be model nondeterminism rather than a causal effect of removing the instruction.

The prototype runs 4 tasks (each twice as a control pair) and ablates all 9 instructions, producing 8 full-context traces and 9 ablation traces.

## Key design decisions

- **Document-first review UI**. The context file itself is the canvas: instructions are highlighted inline by verdict, and clicking a span opens evidence and recommended actions in a popover. This keeps the user grounded in the original document instead of forcing them into an abstract table of findings.

- **Trace-based profiling over static analysis**. Static analysis can find syntactic issues but cannot tell you whether an instruction influences behavior. Trace-based profiling grounds every verdict in what the agent actually did.

- **Black-box ablation over logprob attribution**. Ablation works with any model behind any API. Logprob-based attribution requires white-box access and doesn't generalize across model providers.

## Tradeoffs

- **LLM-as-judge vs. deterministic checkers**: verdicts are qualitative judgments, not quantitative measurements. No inter-rater reliability or rubric calibration. I chose this because it handles the full range of instruction types without per-instruction checker logic.

- **n=1 ablations vs. statistical rigor**: each instruction is ablated once against one selected task. Meaningful causal claims would require multiple seeds averaged across tasks. I chose full instruction coverage (9/9) over depth because coverage demonstrates the methodology more clearly for a prototype.

- **Offline pipeline vs. online profiling**: the pipeline runs against pre-defined tasks, not live sessions. I chose offline because it's self-contained and reproducible for evaluation.

- **Synthetic demo vs. real-world validation**: the demo CLAUDE.md is constructed with known ground truth. The profiler is confirming known answers, not discovering unknowns. This validates the machinery; running against a real CLAUDE.md would validate the approach.

## How I would extend this

With more time, in order of impact:

1. **Run against a real CLAUDE.md** from an uncontrolled project. The synthetic demo validates the machinery. Real inputs validate the approach.
2. **Multi-seed ablations** (N=5 per instruction per task) with agreement rates. "Removing X changed behavior in 4/5 runs" is a meaningful claim.
3. **Broader context sources**: profile system prompts, tool descriptions, memory stores, skills. The unit of analysis is always "a piece of text that was present when the agent ran."
4. **Prompt optimization**: close the loop by automatically rewriting underperforming instructions, re-running the task suite against the proposed change, and accepting the rewrite only if the suite passes. The assessor already proposes replacements for "update" verdicts; automating the validation step is what's missing.
5. **Context budgeting**: each instruction has a token cost (measured) and a behavioral impact (assessed). With both numbers, you can answer "if I need to cut 200 tokens from this context, which instructions should I remove?" The context equivalent of tree-shaking.
6. **Online profiling** with shadow agents running ablated variants alongside production. Continuous attribution without blocking users.
