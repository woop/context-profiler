"""Domain-specific exceptions for csv-stats."""


class CsvStatsError(Exception):
    """Base exception for all csv-stats errors."""


class LoadError(CsvStatsError):
    """Raised when a data file cannot be loaded."""


class ReportError(CsvStatsError):
    """Raised when report generation fails."""
