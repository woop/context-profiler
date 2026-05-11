"""Cross-artifact integrity tests over the committed ``demo-repo/.profiler/``.

These tests lock the contracts between pipeline stages so silent drift
(orphaned evidence, mismatched ids, summary fields out of sync with items,
stale context hashes, typo'd ablation variants) surfaces as a test failure
rather than as confusing UI output.

The tests read the committed artifacts only. They never write, never call an
LLM, and never edit any of the existing pipeline code. New pipeline output
that violates the documented contract will trip the relevant test.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import jsonschema
import pytest

from profiler.extract import stable_id

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "demo-repo"
PROFILER = DEMO / ".profiler"
SCHEMAS = REPO_ROOT / "profiler" / "schemas"


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def claude_md_text() -> str:
    return (DEMO / "CLAUDE.md").read_text()


@pytest.fixture(scope="module")
def claude_md_hash(claude_md_text: str) -> str:
    return "sha256:" + hashlib.sha256(claude_md_text.encode()).hexdigest()


@pytest.fixture(scope="module")
def instructions() -> dict:
    return _load(PROFILER / "instructions" / "instructions.json")


@pytest.fixture(scope="module")
def review() -> dict:
    return _load(PROFILER / "review" / "review-items.json")


@pytest.fixture(scope="module")
def evidence() -> dict:
    return _load(PROFILER / "attribution" / "instruction-evidence.json")


@pytest.fixture(scope="module")
def sessions() -> dict:
    return _load(PROFILER / "traces" / "sessions-index.json")


# -- schema validation -------------------------------------------------------

def test_instructions_validate_against_schema(instructions: dict) -> None:
    schema = _load(SCHEMAS / "instructions.schema.json")
    jsonschema.Draft202012Validator(schema).validate(instructions)


def test_review_items_validate_against_schema(review: dict) -> None:
    schema = _load(SCHEMAS / "review-items.schema.json")
    jsonschema.Draft202012Validator(schema).validate(review)


def test_schema_files_are_themselves_valid_draft_2020_12() -> None:
    for name in ("instructions.schema.json", "review-items.schema.json"):
        schema = _load(SCHEMAS / name)
        jsonschema.Draft202012Validator.check_schema(schema)


# -- offset round-trip -------------------------------------------------------

def test_instruction_offsets_round_trip(
    instructions: dict, claude_md_text: str
) -> None:
    for ins in instructions["instructions"]:
        actual = claude_md_text[ins["startOffset"] : ins["endOffset"]]
        assert actual == ins["snippet"], (
            f"instruction {ins['id']}: source.slice does not match snippet"
        )


def test_review_item_offsets_round_trip(
    review: dict, claude_md_text: str
) -> None:
    for item in review["items"]:
        actual = claude_md_text[item["startOffset"] : item["endOffset"]]
        assert actual == item["snippet"], (
            f"review item {item['id']}: source.slice does not match snippet"
        )


# -- contextHash freshness ---------------------------------------------------

def test_instructions_context_hash_matches_claude_md(
    instructions: dict, claude_md_hash: str
) -> None:
    assert instructions["source"]["contextHash"] == claude_md_hash, (
        "instructions.json contextHash is stale relative to CLAUDE.md; "
        "rerun extract"
    )


def test_review_context_hash_matches_claude_md(
    review: dict, claude_md_hash: str
) -> None:
    assert review["source"]["contextHash"] == claude_md_hash, (
        "review-items.json contextHash is stale relative to CLAUDE.md; "
        "rerun assess/build"
    )


# -- stable-id formula -------------------------------------------------------

def test_every_instruction_id_matches_d013_formula(instructions: dict) -> None:
    for ins in instructions["instructions"]:
        expected = stable_id(ins["sourceFile"], ins["snippet"])
        assert ins["id"] == expected, (
            f"id {ins['id']} does not match stable_id formula "
            f"(expected {expected}); snippet was edited without "
            f"regenerating the id"
        )


def test_every_review_item_id_matches_d013_formula(review: dict) -> None:
    for item in review["items"]:
        expected = stable_id(item["sourceFile"], item["snippet"])
        assert item["id"] == expected, (
            f"review item id {item['id']} does not match stable_id formula "
            f"(expected {expected})"
        )


# -- cross-artifact id closure -----------------------------------------------

def _ids(artifact: dict, key: str, id_field: str) -> set[str]:
    return {entry[id_field] for entry in artifact[key]}


def test_review_item_ids_are_a_subset_of_instruction_ids(
    instructions: dict, review: dict
) -> None:
    instr_ids = _ids(instructions, "instructions", "id")
    review_ids = _ids(review, "items", "id")
    orphans = review_ids - instr_ids
    assert not orphans, (
        f"review items reference ids absent from instructions.json: {orphans}"
    )


def test_evidence_instruction_ids_are_a_subset_of_instruction_ids(
    instructions: dict, evidence: dict
) -> None:
    instr_ids = _ids(instructions, "instructions", "id")
    ev_ids = {item["instruction_id"] for item in evidence["items"]}
    orphans = ev_ids - instr_ids
    assert not orphans, (
        f"instruction-evidence.json references ids absent from "
        f"instructions.json: {orphans}"
    )


# -- ablation context_variant references -------------------------------------

ABLATE_PATTERN = re.compile(r"^ablate:(instr-[0-9a-f]{8})$")


def test_session_context_variants_reference_real_instructions(
    sessions: dict, instructions: dict
) -> None:
    instr_ids = _ids(instructions, "instructions", "id")
    for session in sessions["sessions"]:
        variant = session["context_variant"]
        if variant == "full":
            continue
        m = ABLATE_PATTERN.match(variant)
        assert m, (
            f"sessions-index entry {session['task_id']}/{session['run_id']}: "
            f"context_variant {variant!r} is neither 'full' nor "
            f"a valid 'ablate:instr-xxx' form"
        )
        assert m.group(1) in instr_ids, (
            f"sessions-index entry {session['task_id']}/{session['run_id']}: "
            f"context_variant {variant!r} references instruction "
            f"id absent from instructions.json"
        )


def test_evidence_ablation_variants_reference_real_instructions(
    evidence: dict, instructions: dict
) -> None:
    instr_ids = _ids(instructions, "instructions", "id")
    for item in evidence["items"]:
        for ev in item["evidence"]:
            variant = ev["context_variant"]
            if variant == "full":
                continue
            m = ABLATE_PATTERN.match(variant)
            assert m, (
                f"evidence {ev['id']}: context_variant {variant!r} "
                f"is neither 'full' nor a valid 'ablate:instr-xxx' form"
            )
            assert m.group(1) in instr_ids, (
                f"evidence {ev['id']}: context_variant {variant!r} "
                f"references instruction id absent from instructions.json"
            )


# -- summary consistency -----------------------------------------------------

def test_review_summary_total_instructions_matches_items(review: dict) -> None:
    assert review["summary"]["totalInstructions"] == len(review["items"])


def test_review_summary_verdict_counts_match_items(review: dict) -> None:
    actual = Counter(item["verdict"] for item in review["items"])
    declared = review["summary"]["verdictCounts"]
    for verdict in ("keep", "update", "remove", "add_test"):
        assert declared[verdict] == actual.get(verdict, 0), (
            f"summary.verdictCounts.{verdict} = {declared[verdict]} "
            f"but items contain {actual.get(verdict, 0)}"
        )


def test_review_summary_status_counts_match_items(review: dict) -> None:
    actual = Counter(item["status"] for item in review["items"])
    declared = review["summary"]["statusCounts"]
    for status in ("supported", "unobserved"):
        assert declared[status] == actual.get(status, 0), (
            f"summary.statusCounts.{status} = {declared[status]} "
            f"but items contain {actual.get(status, 0)}"
        )


def test_review_summary_flag_counts_match_items(review: dict) -> None:
    actual: Counter[str] = Counter()
    for item in review["items"]:
        for flag in item["flags"]:
            actual[flag] += 1
    declared = review["summary"]["flagCounts"]
    for flag in ("conflicting", "stale"):
        assert declared[flag] == actual.get(flag, 0), (
            f"summary.flagCounts.{flag} = {declared[flag]} "
            f"but items contain {actual.get(flag, 0)}"
        )


def test_review_summary_token_change_equals_sum_of_item_deltas(
    review: dict,
) -> None:
    declared = review["summary"]["estimatedTokenChange"]
    actual = sum(item["tokenDelta"] for item in review["items"])
    assert declared == actual, (
        f"summary.estimatedTokenChange = {declared} but "
        f"sum(items.tokenDelta) = {actual}"
    )


# -- run-count consistency ---------------------------------------------------

# -- ablation function correctness -------------------------------------------

def test_ablate_removes_correct_span(
    claude_md_text: str, instructions: dict, tmp_path: Path
) -> None:
    from profiler.run_task import _ablate_claude_md

    target = instructions["instructions"][0]
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(claude_md_text)
    instr_path = tmp_path / "instructions.json"
    instr_path.write_text(json.dumps(instructions))

    variant = _ablate_claude_md(claude_md, target["id"], instr_path)

    ablated = claude_md.read_text()
    assert target["snippet"] not in ablated
    assert variant == f"ablate:{target['id']}"
    assert len(ablated) < len(claude_md_text)


def test_ablate_rejects_unknown_id(
    claude_md_text: str, instructions: dict, tmp_path: Path
) -> None:
    from profiler.run_task import _ablate_claude_md

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(claude_md_text)
    instr_path = tmp_path / "instructions.json"
    instr_path.write_text(json.dumps(instructions))

    with pytest.raises(ValueError, match="not found"):
        _ablate_claude_md(claude_md, "instr-00000000", instr_path)


# -- evidence kind/variant alignment -----------------------------------------

def test_trace_evidence_has_full_variant(review: dict) -> None:
    for item in review["items"]:
        for ev in item["evidence"]:
            if ev["kind"] in ("trace", "absence", "conflict"):
                assert ev["context_variant"] == "full", (
                    f"{item['id']}/{ev['id']}: {ev['kind']} evidence should "
                    f"have context_variant='full', got {ev['context_variant']!r}"
                )


def test_ablation_evidence_has_ablate_variant(review: dict) -> None:
    for item in review["items"]:
        for ev in item["evidence"]:
            if ev["kind"] == "ablation":
                assert ev["context_variant"].startswith("ablate:"), (
                    f"{item['id']}/{ev['id']}: ablation evidence should "
                    f"have context_variant='ablate:...', got {ev['context_variant']!r}"
                )


# -- run-count consistency ---------------------------------------------------

def test_review_summary_total_runs_matches_full_context_sessions(
    review: dict, sessions: dict
) -> None:
    full = [s for s in sessions["sessions"] if s["context_variant"] == "full"]
    assert review["summary"]["totalRuns"] == len(full), (
        f"summary.totalRuns ({review['summary']['totalRuns']}) disagrees with "
        f"the number of full-context sessions ({len(full)}); ablation runs "
        f"should not be counted in totalRuns"
    )
