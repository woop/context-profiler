# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic>=0.40",
#   "jsonschema>=4.22",
#   "python-dotenv>=1.0",
# ]
# ///
"""Stage 3: extract instructions from a CLAUDE.md using Opus.

Reads `<demo-repo>/.profiler/config.json`, calls the model with a
structured-output tool, anchors each returned snippet back to exact source
spans, validates round-trip offsets and uniqueness, then writes
`<demo-repo>/.profiler/instructions/instructions.json` plus a cache record at
`<demo-repo>/.profiler/stages/extract-instructions.cache.json`.

Run:
    uv run profiler/extract.py            # respects cache
    uv run profiler/extract.py --force    # bypass cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROMPT_VERSION = 2
MODEL = "claude-opus-4-7"  # Per D012: Opus 4.7 for Stage 3 (chunking).

EXTRACT_TOOL = {
    "name": "emit_instructions",
    "description": "Emit the extracted instructions in source order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "instructions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["title", "snippet"],
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string", "maxLength": 80},
                        "snippet": {"type": "string", "minLength": 1},
                    },
                },
            }
        },
        "required": ["instructions"],
    },
}

SYSTEM_PROMPT = (
    "You extract instructions from a CLAUDE.md file. You must not rewrite, "
    "summarize, or paraphrase. You return verbatim source spans only. "
    "The downstream pipeline will reject any snippet that does not match the "
    "source byte-for-byte (a whitespace-tolerant fallback exists for safety, "
    "but do not rely on it)."
)

USER_PROMPT_RULES = (
    "Extract every instruction in the source. An instruction is a "
    "paragraph-sized unit that tells the agent how to behave (style, "
    "testing, deployment, logging, security, etc.). Include the opening "
    "paragraph if it contains instructional content such as where code "
    "lives or what to focus on.\n\n"
    "Rules:\n"
    "1. One instruction per paragraph. Only split a paragraph if it "
    "clearly contains multiple independent instructions.\n"
    "2. Skip headings (lines starting with `#`).\n"
    "3. The `snippet` field must be copied verbatim from the source, "
    "byte-for-byte. Do not normalize whitespace, smart quotes, or "
    "punctuation.\n"
    "4. Order: source order.\n"
    "5. Title: 6 words or fewer, imperative when possible, no trailing "
    "period.\n\n"
    "Call the emit_instructions tool with the result."
)


def user_prompt(source_file: str, source_text: str) -> str:
    return (
        f"Source file path: {source_file}\n\n"
        "Source content (between BEGIN and END markers):\n"
        "BEGIN\n"
        f"{source_text}\n"
        "END\n\n"
        + USER_PROMPT_RULES
    )


# -- deterministic helpers (unit-tested) ------------------------------------

def collapse_internal_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def stable_id(source_file: str, snippet: str) -> str:
    norm = collapse_internal_whitespace(snippet)
    h = hashlib.sha256(f"{source_file}:{norm}".encode()).hexdigest()[:8]
    return f"instr-{h}"


def prompt_bundle(system_prompt: str, user_template: str, tool_schema: dict) -> str:
    """Stable serialization of every prompt-side input that affects extraction.

    Anything in here, when changed, must invalidate the cache without relying
    on a manual PROMPT_VERSION bump.
    """
    return "||".join(
        [
            system_prompt,
            user_template,
            json.dumps(tool_schema, sort_keys=True),
        ]
    )


def cache_key(
    source_text: str, prompt_version: int, model: str, prompt_bundle_str: str
) -> str:
    h = hashlib.sha256()
    for part in (source_text, str(prompt_version), model, prompt_bundle_str):
        h.update(part.encode())
        h.update(b"||")
    return h.hexdigest()


def anchor(
    source_text: str, llm_snippet: str, *, search_from: int = 0
) -> tuple[int, int, str, bool] | None:
    """Anchor an LLM-returned snippet to exact source offsets in source order.

    `search_from` is the cursor: the caller advances it past each anchored
    span so identical phrases later in the file cannot resolve to the wrong
    location. Returns (start, end, source_derived_snippet, used_fallback) or
    None if even the whitespace-tolerant search fails.
    """
    idx = source_text.find(llm_snippet, search_from)
    if idx >= 0:
        return idx, idx + len(llm_snippet), llm_snippet, False
    pattern = re.escape(llm_snippet)
    pattern = re.sub(r"(\\\s)+", r"\\s+", pattern)
    m = re.search(pattern, source_text[search_from:])
    if m:
        start = search_from + m.start()
        end = search_from + m.end()
        return start, end, source_text[start:end], True
    return None


# -- main -------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve()
    repo_root_default = here.parent.parent

    parser = argparse.ArgumentParser(prog="extract-instructions")
    parser.add_argument("--repo-root", default=str(repo_root_default))
    parser.add_argument("--demo-repo", default="demo-repo")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    demo = repo_root / args.demo_repo
    cfg_path = demo / ".profiler" / "config.json"
    config = json.loads(cfg_path.read_text())
    rel_source = config["claudeMdPath"]
    source_path = demo / rel_source
    source_text = source_path.read_text()
    source_hash = "sha256:" + hashlib.sha256(source_text.encode()).hexdigest()

    out_dir = demo / ".profiler" / "instructions"
    out_path = out_dir / "instructions.json"
    cache_dir = demo / ".profiler" / "stages"
    cache_path = cache_dir / "extract-instructions.cache.json"

    bundle = prompt_bundle(SYSTEM_PROMPT, USER_PROMPT_RULES, EXTRACT_TOOL)
    key = cache_key(source_text, PROMPT_VERSION, MODEL, bundle)
    if not args.force and cache_path.exists() and out_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("cache_key") == key:
            print(
                f"[extract] cache hit; skipping. "
                f"({out_path.relative_to(repo_root)})",
                file=sys.stderr,
            )
            return 0

    # LLM call (lazy imports so tests can import helpers without anthropic).
    import anthropic
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "emit_instructions"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt(rel_source, source_text)}],
    )

    extracted: dict[str, Any] | None = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            extracted = block.input  # type: ignore[attr-defined]
            break
    if extracted is None:
        raise RuntimeError(f"No tool_use block in response: {resp}")

    instructions: list[dict[str, Any]] = []
    fallbacks = 0
    cursor = 0
    for ins in extracted["instructions"]:
        result = anchor(source_text, ins["snippet"], search_from=cursor)
        if result is None:
            raise RuntimeError(
                f"Could not anchor snippet to source: {ins['snippet']!r}"
            )
        start, end, snippet, used_fallback = result
        cursor = end
        if used_fallback:
            fallbacks += 1
            print(
                f"[extract] anchor fallback used for: {ins['title']!r}",
                file=sys.stderr,
            )
        instructions.append(
            {
                "id": stable_id(rel_source, snippet),
                "title": ins["title"],
                "snippet": snippet,
                "sourceFile": rel_source,
                "startOffset": start,
                "endOffset": end,
            }
        )

    # Offset round-trip and id uniqueness.
    for ins in instructions:
        actual = source_text[ins["startOffset"] : ins["endOffset"]]
        if actual != ins["snippet"]:
            raise RuntimeError(
                f"Offset round-trip failed for {ins['id']}: "
                f"expected {ins['snippet']!r}, got {actual!r}"
            )
    seen: set[str] = set()
    for ins in instructions:
        if ins["id"] in seen:
            raise RuntimeError(f"Duplicate id {ins['id']}")
        seen.add(ins["id"])

    artifact = {
        "version": 1,
        "source": {
            "repoName": config["repoName"],
            "contextPath": rel_source,
            "contextHash": source_hash,
        },
        "extraction": {
            "model": MODEL,
            "promptVersion": PROMPT_VERSION,
            "anchorFallbacks": fallbacks,
            "generatedAt": _now_iso(),
        },
        "instructions": instructions,
    }

    import jsonschema

    schema = json.loads(
        (repo_root / "profiler" / "schemas" / "instructions.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(artifact)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2) + "\n")

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_record = {
        "stage": "extract-instructions",
        "cache_key": key,
        "source_hash": source_hash,
        "prompt_version": PROMPT_VERSION,
        "model": MODEL,
        "anchor_fallbacks": fallbacks,
        "generated_at": artifact["extraction"]["generatedAt"],
        "output_path": str(out_path.relative_to(demo)),
    }
    cache_path.write_text(json.dumps(cache_record, indent=2) + "\n")

    print(
        f"[extract] wrote {len(instructions)} instructions "
        f"({fallbacks} anchor fallbacks) to {out_path.relative_to(repo_root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
