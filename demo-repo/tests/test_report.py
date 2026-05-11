from pathlib import Path

from csvstats.report import build_report, write_report


def test_row_count_only() -> None:
    rows = [{"a": "1"}, {"a": "2"}]
    report = build_report(rows)
    assert report["row_count"] == 2
    # column "a" is numeric; median of [1.0, 2.0] = 1.5
    assert report["column_stats"]["a"]["median"] == 1.5


def test_group_by_counts() -> None:
    rows = [
        {"team": "a"},
        {"team": "b"},
        {"team": "a"},
    ]
    report = build_report(rows, group_by="team")
    assert report == {
        "row_count": 3,
        "groups": {"a": 2, "b": 1},
    }


def test_group_by_missing_column_treats_as_empty() -> None:
    rows = [{"team": "a"}, {"other": "b"}]
    report = build_report(rows, group_by="team")
    assert report["groups"] == {"a": 1, "": 1}


def test_write_report_creates_parents(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "report.json"
    write_report({"row_count": 0}, out)
    assert out.read_text().startswith("{")


def test_median_numeric_columns() -> None:
    # Odd count: median is the middle value.
    rows = [
        {"name": "ada",   "age": "36", "score": "98.5"},
        {"name": "linus", "age": "54", "score": "82.0"},
        {"name": "grace", "age": "42", "score": "91.25"},
    ]
    report = build_report(rows)
    col_stats = report["column_stats"]
    # "name" is non-numeric — must not appear in column_stats
    assert "name" not in col_stats
    # age: sorted [36, 42, 54] → median = 42.0
    assert col_stats["age"]["median"] == 42.0
    # score: sorted [82.0, 91.25, 98.5] → median = 91.25
    assert col_stats["score"]["median"] == 91.25


def test_median_even_count() -> None:
    # Even count: median is the mean of the two middle values.
    rows = [
        {"val": "10"},
        {"val": "20"},
        {"val": "30"},
        {"val": "40"},
    ]
    report = build_report(rows)
    # sorted [10, 20, 30, 40] → median = (20 + 30) / 2 = 25.0
    assert report["column_stats"]["val"]["median"] == 25.0


def test_median_mixed_column_skipped() -> None:
    # A column with at least one non-numeric value must be excluded.
    rows = [{"x": "1"}, {"x": "oops"}, {"x": "3"}]
    report = build_report(rows)
    assert "column_stats" not in report


def test_no_column_stats_for_empty_rows() -> None:
    assert build_report([]) == {"row_count": 0}
