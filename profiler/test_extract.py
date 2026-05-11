"""Deterministic helper tests for Stage 3 (extract-instructions).

These do not call the LLM. Live extraction is validated end-to-end by running
`profiler/extract.py` against the real CLAUDE.md.
"""

from __future__ import annotations

import re

import pytest

from profiler.extract import (
    anchor,
    cache_key,
    collapse_internal_whitespace,
    prompt_bundle,
    stable_id,
)

SOURCE = (
    "# Project Conventions\n"
    "\n"
    "Use type hints on all public function signatures. Prefer `pathlib.Path` over `os.path`.\n"
    "\n"
    "Tests live in `tests/` and use `pytest`. Run `pytest -q` from the repo root.\n"
)


# -- collapse_internal_whitespace -------------------------------------------

def test_collapse_replaces_runs_of_whitespace_with_one_space():
    assert collapse_internal_whitespace("a   b\n\tc") == "a b c"


def test_collapse_strips_ends():
    assert collapse_internal_whitespace("\n  hello world  \n") == "hello world"


def test_collapse_idempotent_on_normalized_text():
    s = "a b c"
    assert collapse_internal_whitespace(s) == s


# -- stable_id --------------------------------------------------------------

def test_stable_id_format():
    sid = stable_id("CLAUDE.md", "Use type hints.")
    assert re.fullmatch(r"instr-[0-9a-f]{8}", sid)


def test_stable_id_survives_whitespace_only_edits():
    a = stable_id("CLAUDE.md", "Use type hints. Prefer Path.")
    b = stable_id("CLAUDE.md", "Use type hints.   Prefer Path.")
    c = stable_id("CLAUDE.md", "Use type hints.\nPrefer Path.")
    assert a == b == c


def test_stable_id_changes_on_reword():
    a = stable_id("CLAUDE.md", "Use type hints.")
    b = stable_id("CLAUDE.md", "Always use type hints.")
    assert a != b


def test_stable_id_changes_with_source_file():
    a = stable_id("CLAUDE.md", "Use type hints.")
    b = stable_id("docs/CLAUDE.md", "Use type hints.")
    assert a != b


# -- cache_key --------------------------------------------------------------

def test_cache_key_changes_with_any_input():
    b = "bundle"
    base = cache_key("source", 1, "model", b)
    assert cache_key("source2", 1, "model", b) != base
    assert cache_key("source", 2, "model", b) != base
    assert cache_key("source", 1, "model2", b) != base
    assert cache_key("source", 1, "model", "other") != base


def test_cache_key_is_64_hex_chars():
    k = cache_key("source", 1, "model", "bundle")
    assert re.fullmatch(r"[0-9a-f]{64}", k)


def test_prompt_bundle_changes_on_any_component():
    base = prompt_bundle("sys", "user", {"name": "tool"})
    assert prompt_bundle("sys2", "user", {"name": "tool"}) != base
    assert prompt_bundle("sys", "user2", {"name": "tool"}) != base
    assert prompt_bundle("sys", "user", {"name": "tool2"}) != base


# -- anchor -----------------------------------------------------------------

def test_anchor_exact_match():
    snippet = "Use type hints on all public function signatures."
    result = anchor(SOURCE, snippet)
    assert result is not None
    start, end, recovered, used_fallback = result
    assert SOURCE[start:end] == snippet
    assert recovered == snippet
    assert used_fallback is False


def test_anchor_fallback_collapses_whitespace_runs():
    # Model returned a single-line version of a multi-line source span.
    llm_snippet = (
        "Tests live in `tests/` and use `pytest`. Run `pytest -q` from the repo root."
    )
    multiline_source = SOURCE.replace(
        "Tests live in `tests/` and use `pytest`. Run `pytest -q` from the repo root.",
        "Tests live in `tests/` and use `pytest`.\nRun `pytest -q` from the repo root.",
    )
    result = anchor(multiline_source, llm_snippet)
    assert result is not None
    start, end, recovered, used_fallback = result
    # The recovered span is the source-derived text, not the model's snippet.
    assert recovered == multiline_source[start:end]
    assert recovered != llm_snippet
    assert used_fallback is True


def test_anchor_returns_none_when_truly_absent():
    assert anchor(SOURCE, "this string is not in the source") is None


def test_anchor_cursor_resolves_duplicate_to_second_occurrence():
    text = "Rule A. Do X.\n\nRule B. Do X.\n"
    # Without cursor, both would anchor to the first "Do X."
    first = anchor(text, "Do X.", search_from=0)
    assert first is not None
    assert first[0] == text.find("Do X.")
    second = anchor(text, "Do X.", search_from=first[1])
    assert second is not None
    assert second[0] == text.find("Do X.", first[1])
    assert second[0] > first[0]


def test_anchor_cursor_fallback_respects_offset():
    text = "hello world\n\nhello  world\n"
    # First exact match at 0.
    first = anchor(text, "hello world", search_from=0)
    assert first is not None
    assert first[0] == 0
    assert first[3] is False
    # Search from past the first; the second has extra whitespace so fallback fires.
    second = anchor(text, "hello world", search_from=first[1])
    assert second is not None
    assert second[0] > first[0]
    assert second[3] is True
