"""csvstats CLI entry point."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .loader import load_rows
from .report import build_report, write_report

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(prog="csvstats")
    parser.add_argument("csv", type=Path, help="Path to a CSV file.")
    parser.add_argument(
        "--group-by",
        default=None,
        help="Column name to group row counts by.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path; defaults to stdout.",
    )
    args = parser.parse_args(argv)

    try:
        rows = load_rows(args.csv)
    except FileNotFoundError:
        logger.error("input csv missing", exc_info=True)
        return 2

    report = build_report(rows, group_by=args.group_by)
    if args.out is not None:
        write_report(report, args.out)
    else:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
