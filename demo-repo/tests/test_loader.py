from pathlib import Path

import pytest

from csvstats.errors import LoadError
from csvstats.loader import load_rows, load_tsv


def test_load_rows_returns_dicts(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("name,age\nada,36\nlinus,54\n")
    rows = load_rows(csv_path)
    assert rows == [
        {"name": "ada", "age": "36"},
        {"name": "linus", "age": "54"},
    ]


def test_load_rows_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("name,age\n")
    assert load_rows(csv_path) == []


def test_load_rows_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LoadError):
        load_rows(tmp_path / "nope.csv")


def test_load_rows_reads_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample.csv"
    rows = load_rows(fixture)
    assert [r["name"] for r in rows] == ["ada", "linus", "grace"]
    assert rows[2]["score"] == "91.25"


def test_load_tsv_returns_dicts(tmp_path: Path) -> None:
    tsv_path = tmp_path / "data.tsv"
    tsv_path.write_text("name\tage\nada\t36\nlinus\t54\n")
    rows = load_tsv(tsv_path)
    assert rows == [
        {"name": "ada", "age": "36"},
        {"name": "linus", "age": "54"},
    ]


def test_load_tsv_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LoadError):
        load_tsv(tmp_path / "nope.tsv")


def test_load_tsv_reads_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample.tsv"
    rows = load_tsv(fixture)
    assert [r["name"] for r in rows] == ["ada", "linus", "grace"]
    assert rows[2]["score"] == "91.25"
