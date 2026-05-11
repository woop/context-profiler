# Roadmap

Directions this prototype could go. None of these are implemented.

## Multiple context sources

The prototype profiles one file (CLAUDE.md). The same methodology applies to any text span injected into an agent: system prompts, skills, tool descriptions, retrieved documents, memory entries. The unit of analysis is always "a piece of text that was present when the agent ran." Extending the extractor to handle other sources is mostly a matter of knowing where each source is injected and how to address its spans.

## Online profiling

The prototype runs offline against pre-defined tasks. A production version could run shadow agents alongside real sessions: for each user session, re-run the task with one instruction removed (or with a proposed change) and compare the trace. This produces continuous causal attribution without blocking the user. The cost is one additional agent run per instruction being tested per user session, which can be sampled.

## Prompt optimization

Once you can measure whether an instruction matters and how, you can close the loop: automatically rewrite underperforming instructions, re-run the task suite against the proposed change, and accept the rewrite only if the task suite passes. The assessor already proposes replacements for "update" verdicts. Automating the validation step is the missing piece.

## Context budgeting

Each instruction has a token cost (measured) and a behavioral impact (assessed). With both numbers, you can answer "if I need to cut 200 tokens from this CLAUDE.md, which instructions should I remove?" This is the context equivalent of tree-shaking: keep only the context that demonstrably influences behavior, prune the rest.

## Statistical robustness

The prototype runs each ablation once (n=1). A production version would run multiple seeds, average across tasks, and report confidence intervals. The data model already supports multiple runs per task via the run-id scheme.
