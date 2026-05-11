# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic>=0.40",
#   "claude-code-sdk>=0.0.20",
#   "jsonschema>=4.22",
#   "python-dotenv>=1.0",
# ]
# ///
"""Run the full context profiler pipeline.

    uv run profiler/cli.py                    # full pipeline
    uv run profiler/cli.py --replay           # replay from committed artifacts (no API key needed)
    uv run profiler/cli.py --skip-runs        # re-assess with existing traces
    uv run profiler/cli.py --force            # ignore all caches
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="context-profiler",
        description="Profile a CLAUDE.md against real agent traces.",
    )
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--demo-repo", default="demo-repo")
    parser.add_argument("--replay", action="store_true", help="Replay from committed artifacts (no API key needed)")
    parser.add_argument("--skip-runs", action="store_true", help="Skip task runs, re-assess only")
    parser.add_argument("--force", action="store_true", help="Bypass all caches")
    args = parser.parse_args()

    repo_root = args.repo_root
    if repo_root is None:
        repo_root = str(Path(__file__).resolve().parent.parent)

    skip_runs = args.skip_runs or args.replay
    here = Path(__file__).resolve().parent

    shared = ["--repo-root", repo_root, "--demo-repo", args.demo_repo]
    force = ["--force"] if args.force else []

    stages = [
        ("Stage 3: Extract instructions", [sys.executable, str(here / "extract.py")] + shared + force),
    ]
    if not skip_runs:
        stages.append(
            ("Stage 5: Run tasks", [sys.executable, str(here / "run_task.py")] + shared + force),
        )
    stages.append(
        ("Stage 6+7: Assess and build review items", [sys.executable, str(here / "assess.py")] + shared + force),
    )

    for label, cmd in stages:
        print("=" * 60, file=sys.stderr)
        print(label, file=sys.stderr)
        if args.replay:
            print("  (replay mode: using committed artifacts)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        rc = subprocess.call(cmd)
        if rc != 0:
            return rc

    print("=" * 60, file=sys.stderr)
    print("Done. Review items written to:", file=sys.stderr)
    review_path = Path(repo_root) / args.demo_repo / ".profiler" / "review" / "review-items.json"
    print(f"  {review_path}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
