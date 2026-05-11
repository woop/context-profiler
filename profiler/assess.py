# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic>=0.40",
#   "jsonschema>=4.22",
#   "python-dotenv>=1.0",
# ]
# ///
"""Stage 6+7: assess instructions against traces and build review items.

Reads instructions.json and SDK event traces, calls Opus once per
instruction with the full trace context and repo file listing, then
assembles the final review-items.json consumed by the UI.

Intermediate artifacts:
    .profiler/attribution/assessor-raw.json     (raw model output)
    .profiler/attribution/instruction-evidence.json (normalized)
    .profiler/traces/sessions-index.json        (run index)

Final artifact:
    .profiler/review/review-items.json          (UI contract)

Run:
    uv run profiler/assess.py             # respects cache
    uv run profiler/assess.py --force     # bypass cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL = "claude-opus-4-7"

ASSESS_TOOL = {
    "name": "emit_assessments",
    "description": "Emit the assessment for each instruction.",
    "input_schema": {
        "type": "object",
        "required": ["assessments"],
        "properties": {
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "instruction_id",
                        "verdict",
                        "status",
                        "flags",
                        "sessions_observed",
                        "reason",
                        "evidence",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "instruction_id": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "enum": ["keep", "update", "remove", "add_test"],
                        },
                        "status": {
                            "type": "string",
                            "enum": ["supported", "unobserved"],
                        },
                        "flags": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["conflicting", "stale"],
                            },
                        },
                        "sessions_observed": {
                            "type": "integer",
                            "description": "Number of full-context sessions (not ablation runs) where the agent's behavior was relevant to this instruction.",
                        },
                        "reason": {"type": "string"},
                        "evidence": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": [
                                    "kind",
                                    "label",
                                    "excerpt",
                                    "explanation",
                                ],
                                "additionalProperties": False,
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "trace",
                                            "absence",
                                            "conflict",
                                            "ablation",
                                        ],
                                    },
                                    "label": {"type": "string"},
                                    "excerpt": {"type": "string"},
                                    "explanation": {"type": "string"},
                                },
                            },
                        },
                        "proposed_change": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["update", "remove", "add_test"],
                                },
                                "rationale": {"type": "string"},
                                "replacement": {"type": "string"},
                                "suggested_test": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

SYSTEM_PROMPT = """\
You are a context profiler assessing instructions from a CLAUDE.md file.

For each instruction, you receive:
- The instruction text (a verbatim snippet from CLAUDE.md)
- Agent trace events from one or more task runs (tool calls, edits, bash commands)
- The repository file listing

Your job is to determine whether each instruction is load-bearing, stale, \
conflicting, or unobserved, and to recommend a verdict.

Verdict definitions:
- keep: the instruction is followed in traces and grounded in the repo. It works.
- update: the instruction has value but contains conflicting, ambiguous, or \
  outdated clauses that should be rewritten.
- remove: the instruction references systems or files that no longer exist, \
  or is entirely decorative with no grounding in the repo.
- add_test: the instruction is followed but adherence depends on discipline \
  rather than an enforceable check. Recommend adding a CI gate or test.

Status:
- supported: at least one trace event demonstrates the agent interacting with \
  code covered by this instruction.
- unobserved: no trace event touched code relevant to this instruction.

Flags (orthogonal to verdict):
- stale: the instruction references files, services, or tools that do not \
  exist in the repository.
- conflicting: the instruction contains clauses that are in tension with each \
  other or with other instructions.

Rules:
1. Ground every verdict in specific evidence (trace excerpts or repo state).
2. Do not infer stale from "no task touched this surface" -- that is unobserved.
3. Stale means the instruction's anchors (files, services) are missing from the repo.
4. For each piece of evidence, provide a short excerpt and explanation.
5. If verdict is update or remove or add_test, include a proposed_change.
6. Be concise. One sentence per explanation.
7. If an ablation run exists (a run where one instruction was removed), compare \
its behavior to the full-context run. Use evidence kind "ablation" for findings \
from the ablation comparison. If the agent behaved identically with and without \
the instruction, that suggests the instruction is redundant with the codebase \
convention and note this in the reason."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_listing(workspace: Path) -> str:
    lines = []
    for p in sorted(workspace.rglob("*")):
        if p.is_file() and ".profiler" not in p.parts:
            lines.append(str(p.relative_to(workspace)))
    return "\n".join(lines)


def _load_events(events_path: Path) -> list[dict[str, Any]]:
    lines = events_path.read_text().strip().split("\n")
    return [json.loads(line) for line in lines if line.strip()]


def _format_trace(events: list[dict[str, Any]]) -> str:
    lines = []
    for ev in events:
        if ev["type"] == "AssistantMessage":
            for block in ev.get("content", []):
                if block.get("type") == "ToolUseBlock":
                    tool = block.get("tool_name", "unknown")
                    inp = block.get("tool_input", {})
                    if "command" in inp:
                        lines.append(f"[tool] {tool}: {inp['command']}")
                    elif "file_path" in inp:
                        detail = ""
                        if "new_string" in inp:
                            detail = f" -> wrote: {inp['new_string'][:200]}"
                        elif "content" in inp:
                            detail = f" -> wrote: {inp['content'][:200]}"
                        lines.append(f"[tool] {tool}: {inp['file_path']}{detail}")
                    elif "pattern" in inp:
                        lines.append(f"[tool] {tool}: pattern={inp['pattern']}")
                    else:
                        lines.append(f"[tool] {tool}: {json.dumps(inp)[:150]}")
                elif block.get("type") == "TextBlock":
                    text = block.get("text", "")
                    if text.strip():
                        lines.append(f"[text] {text[:200]}")
        elif ev["type"] == "ResultMessage":
            result = ev.get("result", "")
            if result:
                lines.append(f"[result] {result[:300]}")
    return "\n".join(lines)


def _build_user_prompt(
    instructions: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    file_listing: str,
) -> str:
    parts = ["# Instructions to assess\n"]
    for ins in instructions:
        parts.append(
            f"## {ins['id']} -- {ins['title']}\n"
            f"```\n{ins['snippet']}\n```\n"
        )

    parts.append("# Agent trace events\n")
    for session in sessions:
        variant = session.get("context_variant", "full")
        variant_note = ""
        if variant != "full":
            variant_note = f" (ABLATION: {variant} -- this instruction was REMOVED from CLAUDE.md for this run)"
        parts.append(
            f"## Task: {session['task_id']} / {session['run_id']}{variant_note}\n"
            f"```\n{session['trace']}\n```\n"
        )

    parts.append(
        f"# Repository file listing\n```\n{file_listing}\n```\n\n"
        "Assess each instruction and call the emit_assessments tool."
    )
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _ev_id(idx: int) -> str:
    return f"ev-{idx:06x}"


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve()
    repo_root_default = here.parent.parent

    parser = argparse.ArgumentParser(prog="assess")
    parser.add_argument("--repo-root", default=str(repo_root_default))
    parser.add_argument("--demo-repo", default="demo-repo")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    demo = repo_root / args.demo_repo

    # Load instructions (Stage 3 output).
    instructions_path = demo / ".profiler" / "instructions" / "instructions.json"
    instructions_artifact = json.loads(instructions_path.read_text())
    instructions = instructions_artifact["instructions"]
    source_text = (demo / instructions_artifact["source"]["contextPath"]).read_text()
    source_hash = "sha256:" + hashlib.sha256(source_text.encode()).hexdigest()

    # Discover runs and build sessions index.
    runs_root = demo / ".profiler" / "runs" / "tasks"
    sessions: list[dict[str, Any]] = []
    if runs_root.exists():
        for task_dir in sorted(runs_root.iterdir()):
            if not task_dir.is_dir():
                continue
            for run_dir in sorted(task_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                events_path = run_dir / "output" / "sdk-events.jsonl"
                result_path = run_dir / "output" / "result.json"
                if events_path.exists():
                    events = _load_events(events_path)
                    context_variant = "full"
                    if result_path.exists():
                        result_data = json.loads(result_path.read_text())
                        context_variant = result_data.get(
                            "context_variant", "full"
                        )
                    sessions.append(
                        {
                            "task_id": task_dir.name,
                            "run_id": run_dir.name,
                            "context_variant": context_variant,
                            "events_path": str(
                                events_path.relative_to(demo)
                            ),
                            "result_path": str(
                                result_path.relative_to(demo)
                            )
                            if result_path.exists()
                            else None,
                            "trace": _format_trace(events),
                        }
                    )

    # Write sessions index (A.5).
    traces_dir = demo / ".profiler" / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    sessions_index = {
        "version": 1,
        "sessions": [
            {k: v for k, v in s.items() if k != "trace"} for s in sessions
        ],
    }
    (traces_dir / "sessions-index.json").write_text(
        json.dumps(sessions_index, indent=2) + "\n"
    )
    print(
        f"[assess] indexed {len(sessions)} sessions",
        file=sys.stderr,
    )

    # Check cache.
    cache_dir = demo / ".profiler" / "stages"
    cache_path = cache_dir / "assess.cache.json"
    attrib_dir = demo / ".profiler" / "attribution"

    cache_inputs = json.dumps(
        {
            "source_hash": source_hash,
            "instructions": [i["id"] for i in instructions],
            "sessions": [
                {"task_id": s["task_id"], "run_id": s["run_id"]}
                for s in sessions
            ],
            "model": MODEL,
        },
        sort_keys=True,
    )
    cache_key = hashlib.sha256(cache_inputs.encode()).hexdigest()

    if not args.force and cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("cache_key") == cache_key:
            print("[assess] cache hit; skipping", file=sys.stderr)
            return 0

    # File listing for stale detection.
    file_listing = _file_listing(demo)

    # Call Opus (A.6).
    import anthropic
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
    client = anthropic.Anthropic()

    user_prompt = _build_user_prompt(instructions, sessions, file_listing)

    print(
        f"[assess] calling {MODEL} with {len(instructions)} instructions, "
        f"{len(sessions)} sessions",
        file=sys.stderr,
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        tools=[ASSESS_TOOL],
        tool_choice={"type": "tool", "name": "emit_assessments"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_output: dict[str, Any] | None = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            raw_output = block.input
            break
    if raw_output is None:
        raise RuntimeError(f"No tool_use block in response: {resp}")

    # Write raw assessor output.
    attrib_dir.mkdir(parents=True, exist_ok=True)
    raw_path = attrib_dir / "assessor-raw.json"
    raw_path.write_text(json.dumps(raw_output, indent=2) + "\n")

    # Normalize into instruction-evidence and review-items (A.7).
    config = json.loads((demo / ".profiler" / "config.json").read_text())
    ev_counter = 0
    items: list[dict[str, Any]] = []

    assessment_by_id = {
        a["instruction_id"]: a for a in raw_output["assessments"]
    }

    for ins in instructions:
        assessment = assessment_by_id.get(ins["id"])
        if assessment is None:
            print(
                f"[assess] warning: no assessment for {ins['id']}",
                file=sys.stderr,
            )
            continue

        token_count = _estimate_tokens(ins["snippet"])
        evidence_items = []
        for ev in assessment.get("evidence", []):
            ev_counter += 1
            ev_variant = "full"
            ev_source = ""
            if sessions:
                ablation_sessions = [
                    s for s in sessions if s["context_variant"] != "full"
                ]
                full_sessions = [
                    s for s in sessions if s["context_variant"] == "full"
                ]
                if ev["kind"] == "ablation" and ablation_sessions:
                    ev_variant = ablation_sessions[0]["context_variant"]
                    ev_source = ablation_sessions[0]["events_path"]
                elif full_sessions:
                    ev_source = full_sessions[0]["events_path"]
                else:
                    ev_source = sessions[0]["events_path"]
            evidence_items.append(
                {
                    "id": _ev_id(ev_counter),
                    "kind": ev["kind"],
                    "context_variant": ev_variant,
                    "label": ev["label"],
                    "source": ev_source,
                    "excerpt": ev.get("excerpt", ""),
                    "explanation": ev["explanation"],
                }
            )

        trace_events = sum(
            1
            for ev in evidence_items
            if ev["kind"] in ("trace", "ablation")
        )
        full_sessions = [s for s in sessions if s["context_variant"] == "full"]
        sessions_observed = min(
            assessment.get("sessions_observed", 0), len(full_sessions)
        )

        proposed = assessment.get("proposed_change")
        proposed_item = None
        token_delta = 0
        if proposed and assessment["verdict"] != "keep":
            proposed_item = {"kind": proposed["kind"], "rationale": proposed["rationale"]}
            if proposed.get("replacement"):
                proposed_item["replacement"] = proposed["replacement"]
                token_delta = (
                    _estimate_tokens(proposed["replacement"]) - token_count
                )
            elif proposed.get("suggested_test"):
                proposed_item["suggestedTest"] = proposed["suggested_test"]
            elif assessment["verdict"] == "remove":
                token_delta = -token_count

        item: dict[str, Any] = {
            "id": ins["id"],
            "verdict": assessment["verdict"],
            "status": assessment["status"],
            "flags": assessment.get("flags", []),
            "title": ins["title"],
            "snippet": ins["snippet"],
            "sourceFile": ins["sourceFile"],
            "startOffset": ins["startOffset"],
            "endOffset": ins["endOffset"],
            "tokenCount": token_count,
            "tokenDelta": token_delta,
            "metrics": {
                "sessionsObserved": sessions_observed,
                "totalSessions": len([s for s in sessions if s["context_variant"] == "full"]),
                "traceEvents": trace_events,
            },
            "reason": assessment["reason"],
            "evidence": evidence_items,
        }
        if proposed_item:
            item["proposedChange"] = proposed_item
        items.append(item)

    # Write instruction-evidence.json.
    evidence_artifact = {
        "version": 1,
        "model": MODEL,
        "generatedAt": _now_iso(),
        "items": [
            {
                "instruction_id": item["id"],
                "verdict": item["verdict"],
                "status": item["status"],
                "flags": item["flags"],
                "reason": item["reason"],
                "evidence": item["evidence"],
            }
            for item in items
        ],
    }
    evidence_path = attrib_dir / "instruction-evidence.json"
    evidence_path.write_text(json.dumps(evidence_artifact, indent=2) + "\n")

    # Build review-items.json (A.7).
    verdict_counts = {"keep": 0, "update": 0, "remove": 0, "add_test": 0}
    status_counts = {"supported": 0, "unobserved": 0}
    flag_counts = {"conflicting": 0, "stale": 0}
    total_token_delta = 0

    for item in items:
        verdict_counts[item["verdict"]] += 1
        status_counts[item["status"]] += 1
        for flag in item["flags"]:
            flag_counts[flag] += 1
        total_token_delta += item["tokenDelta"]

    review_artifact = {
        "version": 1,
        "source": {
            "repoName": config["repoName"],
            "contextPath": instructions_artifact["source"]["contextPath"],
            "contextHash": source_hash,
            "generatedAt": _now_iso(),
        },
        "summary": {
            "totalInstructions": len(items),
            "totalRuns": len([s for s in sessions if s["context_variant"] == "full"]),
            "verdictCounts": verdict_counts,
            "statusCounts": status_counts,
            "flagCounts": flag_counts,
            "estimatedTokenChange": total_token_delta,
        },
        "items": items,
    }

    import jsonschema

    schema = json.loads(
        (repo_root / "profiler" / "schemas" / "review-items.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(review_artifact)

    review_path = demo / ".profiler" / "review" / "review-items.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(review_artifact, indent=2) + "\n")

    # Write cache.
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_record = {
        "stage": "assess",
        "cache_key": cache_key,
        "source_hash": source_hash,
        "model": MODEL,
        "generated_at": review_artifact["source"]["generatedAt"],
    }
    cache_path.write_text(json.dumps(cache_record, indent=2) + "\n")

    print(
        f"[assess] wrote {len(items)} review items "
        f"(verdicts: {verdict_counts}) to {review_path.relative_to(repo_root)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
