"""Report construction and persistence."""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _column_names(rows: list[dict[str, str]]) -> list[str]:
    """Return column names in insertion order, de-duplicated."""
    seen: dict[str, None] = {}
    for row in rows:
        seen.update(dict.fromkeys(row))
    return list(seen)


def build_report(
    rows: list[dict[str, str]], group_by: str | None = None
) -> dict[str, Any]:
    """Build a JSON-serializable summary of the rows.

    If `group_by` is provided, count rows grouped by that column's value.

    For each column whose values are all convertible to float, the summary
    includes per-column stats (currently: ``median``) under ``column_stats``.
    """
    summary: dict[str, Any] = {"row_count": len(rows)}

    if group_by:
        summary["groups"] = dict(
            Counter(row.get(group_by, "") for row in rows)
        )

    if rows:
        col_stats: dict[str, dict[str, float]] = {}
        for col in _column_names(rows):
            values: list[str] = [row[col] for row in rows if col in row]
            try:
                floats = [float(v) for v in values]
            except (ValueError, TypeError):
                continue
            if floats:
                col_stats[col] = {"median": statistics.median(floats)}
        if col_stats:
            summary["column_stats"] = col_stats

    return summary


def write_report(report: dict[str, Any], out_path: Path) -> None:
    """Write a report dict as pretty JSON, creating parent directories."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True))
