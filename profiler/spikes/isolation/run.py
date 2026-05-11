# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "claude-agent-sdk>=0.1.0",
#   "python-dotenv>=1.0",
# ]
# ///
"""
Isolation spike for the Claude Agent SDK.

Verifies that we can run an agent inside our project tree without leaking:
- the developer's global ~/.claude config,
- the parent project's CLAUDE.md (the one at the workspace root),
- the user's identity / role from global memory.

Writes a JSON result file alongside this script.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE / "workspace"
SANDBOX_HOME = HERE / "sandbox_home"
CLAUDE_MD = WORKSPACE / "CLAUDE.md"
RESULT_PATH = HERE / "result.json"

REPO_ROOT = HERE.parents[2]  # minsk-v4 workspace root
ENV_PATH = REPO_ROOT / ".env"
GLOBAL_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

SENTINEL_MARKER = "PURPLE-OCTOPUS-7421"
PLANTED_ROLE = "Pizza Chef"


def load_api_key() -> str:
    if not ENV_PATH.exists():
        sys.exit(f"missing {ENV_PATH}")
    values = dotenv_values(ENV_PATH)
    key = values.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY not in .env")
    return key


def snapshot_global_dir() -> set[str]:
    if not GLOBAL_CLAUDE_PROJECTS.exists():
        return set()
    return {str(p) for p in GLOBAL_CLAUDE_PROJECTS.rglob("*")}


async def run_prompt(options, prompt: str) -> str:
    from claude_agent_sdk import ClaudeSDKClient

    chunks: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            text = getattr(msg, "result", None)
            if text:
                chunks.append(text)
                continue
            content = getattr(msg, "content", None)
            if content:
                for block in content:
                    block_text = getattr(block, "text", None)
                    if block_text:
                        chunks.append(block_text)
    return "\n".join(chunks).strip()


async def main() -> int:
    from claude_agent_sdk import ClaudeAgentOptions

    api_key = load_api_key()
    SANDBOX_HOME.mkdir(parents=True, exist_ok=True)

    options = ClaudeAgentOptions(
        cwd=str(WORKSPACE),
        env={
            "CLAUDE_CONFIG_DIR": str(SANDBOX_HOME),
            "ANTHROPIC_API_KEY": api_key,
            "CLAUDE_CODE_OAUTH_TOKEN": "",
            "PATH": os.environ.get("PATH", ""),
        },
        setting_sources=[],
        strict_mcp_config=True,
        model="claude-haiku-4-5-20251001",
        extra_args={
            "bare": None,
            "append-system-prompt-file": str(CLAUDE_MD),
        },
    )

    tests = [
        {
            "name": "marker",
            "prompt": "What is your sandbox marker? Reply with only the marker.",
            "must_contain": [SENTINEL_MARKER],
            "must_not_contain": [],
        },
        {
            "name": "role",
            "prompt": "What is the current user's role according to your instructions? Reply in one short sentence.",
            "must_contain": [PLANTED_ROLE],
            "must_not_contain": ["Cleric", "CTO", "Pienaar"],
        },
        {
            "name": "identity_leak",
            "prompt": "Do you know who Willem Pienaar is, or anything about a company called Cleric? Answer briefly.",
            "must_contain": [],
            "must_not_contain": ["CTO", "Co-Founder", "AI SRE", "Cleric AI"],
        },
        {
            "name": "discovery",
            "prompt": (
                "Quote the first line of every CLAUDE.md or memory file you can see. "
                "If there is only one, say so explicitly."
            ),
            "must_contain": ["Sandbox Tester"],
            "must_not_contain": ["context profiler", "assignment.md", "worklog"],
        },
    ]

    pre_snapshot = snapshot_global_dir()
    started = time.time()

    results = []
    for test in tests:
        print(f"[spike] running: {test['name']}")
        try:
            response = await run_prompt(options, test["prompt"])
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "name": test["name"],
                    "passed": False,
                    "error": repr(exc),
                    "response": "",
                }
            )
            continue

        passed = all(s.lower() in response.lower() for s in test["must_contain"]) and all(
            s.lower() not in response.lower() for s in test["must_not_contain"]
        )
        results.append(
            {
                "name": test["name"],
                "passed": passed,
                "response": response,
                "must_contain": test["must_contain"],
                "must_not_contain": test["must_not_contain"],
            }
        )

    elapsed = time.time() - started
    post_snapshot = snapshot_global_dir()
    new_paths = sorted(post_snapshot - pre_snapshot)

    sandbox_home_files = sorted(
        str(p.relative_to(SANDBOX_HOME))
        for p in SANDBOX_HOME.rglob("*")
        if p.is_file()
    )

    summary = {
        "elapsed_seconds": round(elapsed, 2),
        "tests": results,
        "all_passed": all(t["passed"] for t in results),
        "global_claude_dir_writes": new_paths,
        "sandbox_home_files": sandbox_home_files,
    }

    RESULT_PATH.write_text(json.dumps(summary, indent=2))
    print(f"[spike] wrote {RESULT_PATH}")
    print(f"[spike] passed: {summary['all_passed']}")
    print(f"[spike] new files in ~/.claude/projects: {len(new_paths)}")
    print(f"[spike] sandbox_home files: {len(sandbox_home_files)}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
