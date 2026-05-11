# AI session traces

Raw Claude Code session logs from the four substantive sessions that built this prototype. All ran on 2026-05-10 in a Conductor worktree of this repo. Files are unedited JSONL: one event per line (user message, assistant response, tool call, tool result).

## Folders

- **`main-thread-and-backend/`** — Orchestration thread and backend (`profiler/`) build: problem framing, direction decisions, pipeline architecture, and iterative implementation of extract, run, ablate, assess. Three sub-agent traces under `subagents/`.
- **`frontend/`** — SPA build at `app/frontend/` behind the locked `review-items` contract. Largest session (about 7.7MB).
- **`deployment/`** — Cloudflare Pages + GitHub Actions on push to main.
- **`readme-diagrams/`** — Pipeline diagram iteration via the `paperbanana` skill.

## Notes

- Only the main thread spawned sub-agents.
- Other sessions exist (cleanup-and-tests, two reviewer passes, UI-contract discussion, file recovery) but are smaller and complementary; the four above cover the substantive design and build work.
- Short on time? Start with `main-thread-and-backend/` for the design decisions, then `frontend/` for the largest build trace.
