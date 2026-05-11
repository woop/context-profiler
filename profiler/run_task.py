# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "claude-code-sdk>=0.0.20",
#   "python-dotenv>=1.0",
# ]
# ///
"""Stage 5: run a task against the demo repo using the Claude Agent SDK.

Copies the demo repo into an isolated workspace, runs the agent with the
task prompt, and collects SDK events into a predictable output directory.

Layout per run:
    .profiler/runs/tasks/<task-id>/<run-id>/
        workspace/          # cp -r of demo-repo (agent's cwd)
        agent-home/         # CLAUDE_CONFIG_DIR sandbox
        output/
            sdk-events.jsonl   # all SDK messages
            result.json        # summary (model, elapsed, token counts)

Run:
    uv run profiler/run_task.py                         # run all tasks
    uv run profiler/run_task.py --task add-tsv-loader   # run one task
    uv run profiler/run_task.py --force                 # ignore prior runs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL = "claude-sonnet-4-6"
MAX_TURNS = 15
RUN_PREFIX = "run"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_run_id(task_dir: Path) -> str:
    existing = sorted(task_dir.glob(f"{RUN_PREFIX}-*"))
    n = len(existing) + 1
    return f"{RUN_PREFIX}-{n:03d}"


def _load_tasks(demo: Path) -> list[dict[str, Any]]:
    tasks_path = demo / ".profiler" / "inputs" / "tasks.json"
    data = json.loads(tasks_path.read_text())
    return data["tasks"]


def _ablate_claude_md(claude_md_path: Path, instruction_id: str, instructions_path: Path) -> str:
    """Remove one instruction from the CLAUDE.md by its id. Returns context_variant label."""
    instructions = json.loads(instructions_path.read_text())["instructions"]
    target = next((i for i in instructions if i["id"] == instruction_id), None)
    if target is None:
        raise ValueError(f"Instruction {instruction_id} not found in {instructions_path}")

    source = claude_md_path.read_text()
    snippet = source[target["startOffset"] : target["endOffset"]]
    if snippet != target["snippet"]:
        raise ValueError(
            f"Offset mismatch for {instruction_id}: "
            f"expected {target['snippet']!r}, got {snippet!r}"
        )

    ablated = source[: target["startOffset"]] + source[target["endOffset"] :]
    ablated = ablated.replace("\n\n\n", "\n\n")
    claude_md_path.write_text(ablated)
    return f"ablate:{instruction_id}"


async def run_one_task(
    task: dict[str, Any],
    demo: Path,
    repo_root: Path,
    *,
    force: bool = False,
    ablate: str | None = None,
) -> dict[str, Any]:
    from claude_code_sdk import ClaudeCodeOptions, query
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")

    task_id = task["id"]
    runs_dir = demo / ".profiler" / "runs" / "tasks" / task_id

    if not force and runs_dir.exists() and any(runs_dir.iterdir()):
        print(f"[run] skipping {task_id}: prior run exists (use --force)", file=sys.stderr)
        return {"task_id": task_id, "skipped": True}

    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = _next_run_id(runs_dir)
    run_dir = runs_dir / run_id
    workspace = run_dir / "workspace"
    agent_home = run_dir / "agent-home"
    output_dir = run_dir / "output"

    shutil.copytree(
        demo,
        workspace,
        ignore=shutil.ignore_patterns(".profiler"),
    )
    agent_home.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    claude_md_path = workspace / "CLAUDE.md"
    context_variant = "full"
    if ablate:
        instructions_path = demo / ".profiler" / "instructions" / "instructions.json"
        context_variant = _ablate_claude_md(claude_md_path, ablate, instructions_path)

    saved_env: dict[str, str | None] = {}
    env_overrides = {
        "CLAUDE_CONFIG_DIR": str(agent_home),
        "CLAUDE_CODE_OAUTH_TOKEN": "",
    }
    for k, v in env_overrides.items():
        saved_env[k] = os.environ.get(k)
        os.environ[k] = v

    options = ClaudeCodeOptions(
        cwd=workspace,
        model=MODEL,
        max_turns=MAX_TURNS,
        permission_mode="bypassPermissions",
        append_system_prompt=claude_md_path.read_text(),
        extra_args={"bare": None},
    )

    events: list[dict[str, Any]] = []
    started = time.time()
    result_text = ""

    try:
        variant_label = f", variant={context_variant}" if context_variant != "full" else ""
        print(f"[run] {task_id}/{run_id}: starting ({MODEL}, max_turns={MAX_TURNS}{variant_label})", file=sys.stderr)
        async for msg in query(prompt=task["prompt"], options=options):
            event = {
                "type": type(msg).__name__,
                "timestamp": _now_iso(),
            }
            if hasattr(msg, "content"):
                event["content"] = [
                    _serialize_block(b) for b in msg.content
                ]
            if hasattr(msg, "message"):
                event["message"] = str(msg.message)
            if hasattr(msg, "result"):
                event["result"] = msg.result
                result_text = msg.result or ""
            if hasattr(msg, "session_id"):
                event["session_id"] = msg.session_id
            events.append(event)
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    elapsed = time.time() - started

    events_path = output_dir / "sdk-events.jsonl"
    with events_path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    result = {
        "task_id": task_id,
        "run_id": run_id,
        "context_variant": context_variant,
        "model": MODEL,
        "max_turns": MAX_TURNS,
        "started_at": events[0]["timestamp"] if events else _now_iso(),
        "elapsed_seconds": round(elapsed, 2),
        "total_events": len(events),
        "result_text": result_text[:500],
        "workspace": str(workspace.relative_to(demo)),
        "events_path": str(events_path.relative_to(demo)),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    print(
        f"[run] {task_id}/{run_id}: done in {elapsed:.1f}s, {len(events)} events",
        file=sys.stderr,
    )
    return result


def _serialize_block(block: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"type": type(block).__name__}
    if hasattr(block, "text"):
        d["text"] = block.text
    if hasattr(block, "name"):
        d["tool_name"] = block.name
    if hasattr(block, "input"):
        d["tool_input"] = _truncate_input(block.input)
    if hasattr(block, "id") and not hasattr(block, "text"):
        d["tool_use_id"] = block.id
    if hasattr(block, "content") and not hasattr(block, "text"):
        d["content"] = str(block.content)[:500]
    return d


def _truncate_input(inp: Any) -> Any:
    if isinstance(inp, dict):
        out = {}
        for k, v in inp.items():
            if isinstance(v, str) and len(v) > 300:
                out[k] = v[:300] + "..."
            else:
                out[k] = v
        return out
    return inp


async def async_main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve()
    repo_root_default = here.parent.parent

    parser = argparse.ArgumentParser(prog="run-task")
    parser.add_argument("--repo-root", default=str(repo_root_default))
    parser.add_argument("--demo-repo", default="demo-repo")
    parser.add_argument("--task", default=None, help="Run only this task id")
    parser.add_argument("--ablate", default=None, help="Instruction id to remove from CLAUDE.md")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    demo = repo_root / args.demo_repo

    tasks = _load_tasks(demo)
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            print(f"[run] task {args.task!r} not found", file=sys.stderr)
            return 1

    results = []
    for task in tasks:
        result = await run_one_task(
            task, demo, repo_root, force=args.force, ablate=args.ablate
        )
        results.append(result)

    ran = [r for r in results if not r.get("skipped")]
    print(f"[run] completed: {len(ran)} runs, {len(results) - len(ran)} skipped", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
