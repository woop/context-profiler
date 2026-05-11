"""CSV loading helpers."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from csvstats.errors import LoadError

logger = logging.getLogger(__name__)


def load_rows(path: Path) -> list[dict[str, str]]:
    """Read all rows from a CSV file as a list of dicts keyed by header."""
    if not path.exists():
        logger.error("csv not found at %s", path, exc_info=True)
        raise LoadError(path)
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def load_tsv(path: Path) -> list[dict[str, str]]:
    """Read all rows from a TSV file as a list of dicts keyed by header."""
    if not path.exists():
        logger.error("tsv not found at %s", path, exc_info=True)
        raise LoadError(path)
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader)
