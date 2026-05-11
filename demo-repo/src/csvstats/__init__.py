"""csvstats: summarize CSV files into JSON reports."""

from .loader import load_rows
from .report import build_report, write_report

__all__ = ["load_rows", "build_report", "write_report"]
