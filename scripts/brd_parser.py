#!/usr/bin/env python3
"""
Layer 1: parses a raw BRD file into the schemas/parsed_brd.schema.json contract
(the contract every downstream agent's retrieval, completeness, and scope-creep
checking is keyed against -- see docs/agent_contract_reference.md Section 8).

Works on the structure used throughout kb/past_brds/ and expected of any new
BRD dropped in there: optional YAML frontmatter, '## Section' H2 headings, and
requirement bullets of the form '- FR-N: text' / '- NFR-N: text' (wrapped
continuation lines are re-joined). No LLM call -- this is a deterministic,
regex-based structural parser, matched to the plain-markdown format this
system actually receives, not a general-purpose document understander.

Known limitations (stated, not hidden):
  - Only .md/.txt are parsed. .pdf/.docx pass guardrails.validate_brd_file's
    file-type allowlist but raise NotImplementedError here -- they'd need a
    text-extraction step (pdfplumber / python-docx) that isn't wired up.
  - Only Functional/Non-Functional Requirements sections are parsed into
    requirement_id-bearing requirements[] entries, because those are the only
    sections that use an explicit, machine-checkable id prefix (FR-N:/NFR-N:)
    in the source documents. Constraints/Success Metrics/Notes are preserved
    as sections (so they still route and retrieve) but contribute no
    requirement_ids -- the same behavior the hand-authored brd-002 fixture had.
  - requirement priority (must/should/could) isn't inferred from free text --
    the source BRDs don't mark it explicitly, and guessing would be noise, not
    signal. Every requirement parses as priority="unspecified".
  - is_ambiguous / contradictions_detected are simple keyword heuristics
    (see AMBIGUITY_KEYWORDS / CONTRADICTION_MARKER below), not semantic
    ambiguity detection -- that's the Critic's job downstream, not Layer 1's.

Usage:
    python scripts/brd_parser.py kb/past_brds/brd-001-simple.md
    python scripts/brd_parser.py kb/past_brds/brd-003-complex.md -o /tmp/parsed.json
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from ingest import parse_frontmatter, split_sections

REQUIREMENT_LINE_RE = re.compile(r"^-\s*(FR|NFR)-(\d+):\s*(.+)$", re.IGNORECASE)

SECTION_TYPE_MAP = {
    "objectives": "objective",
    "functional requirements": "functional_requirement",
    "non-functional requirements": "non_functional_requirement",
    "constraints": "constraint",
    "stakeholders": "stakeholder",
    "success metrics": "success_metric",
}

# Kept short/stable so section_ids don't churn every time wording changes
# slightly, and so they match the hand-authored brd-002 fixture's ids
# ("brd-002-sec-fr", "brd-002-sec-nfr") that other fixtures reference.
SECTION_SLUG_MAP = {
    "objectives": "obj",
    "functional requirements": "fr",
    "non-functional requirements": "nfr",
    "constraints": "constraints",
    "stakeholders": "stakeholders",
    "success metrics": "success-metrics",
}

AMBIGUITY_KEYWORDS = ("tbd", "unclear", "ambiguous", "undecided", "unspecified", "not specify")
CONTRADICTION_MARKER = "flagged as a contradiction"

TEXT_FILE_TYPES = {"md", "txt"}


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"


def _join_wrapped_lines(text: str):
    """Bullet items can wrap onto an indented continuation line (see
    brd-002's FR-5). Re-join those before splitting into individual bullets."""
    joined = []
    for line in text.splitlines():
        if line.startswith("- ") or not joined:
            joined.append(line.rstrip())
        elif line.startswith((" ", "\t")):
            joined[-1] += " " + line.strip()
        else:
            joined.append(line.rstrip())
    return joined


def _parse_requirements(section_text: str):
    requirements = []
    for line in _join_wrapped_lines(section_text):
        m = REQUIREMENT_LINE_RE.match(line.strip())
        if not m:
            continue
        req_type, num, req_text = m.group(1).upper(), m.group(2), m.group(3).strip()
        classification = "functional" if req_type == "FR" else "non_functional"
        requirements.append({
            "requirement_id": f"{req_type}-{num}",
            "text": req_text,
            "classification": classification,
            "priority": "unspecified",
            "is_ambiguous": any(kw in req_text.lower() for kw in AMBIGUITY_KEYWORDS),
        })
    return requirements


def parse_brd(path) -> dict:
    path = Path(path)
    raw = path.read_text(errors="ignore")
    source_hash = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    file_type = path.suffix.lstrip(".").lower()

    if file_type not in TEXT_FILE_TYPES:
        raise NotImplementedError(
            f"brd_parser.parse_brd only supports {sorted(TEXT_FILE_TYPES)} today (got '.{file_type}'); "
            "pdf/docx need a text-extraction step (pdfplumber/python-docx) that isn't wired up yet."
        )

    try:
        frontmatter, body = parse_frontmatter(raw)
    except ValueError:
        frontmatter, body = {}, raw

    brd_id = frontmatter.get("source_id") or path.stem
    domain = frontmatter.get("domain") or "unspecified"
    complexity = frontmatter.get("complexity") or "unspecified"
    if complexity not in ("simple", "medium", "complex"):
        complexity = "medium"

    sections = []
    nfr_present = False
    for title, text in split_sections(body):
        key = title.strip().lower()
        section_type = SECTION_TYPE_MAP.get(key, "other")
        slug = SECTION_SLUG_MAP.get(key, slugify(title))
        requirements = (
            _parse_requirements(text)
            if section_type in ("functional_requirement", "non_functional_requirement")
            else []
        )
        if section_type == "non_functional_requirement" and requirements:
            nfr_present = True
        sections.append({
            "section_id": f"{brd_id}-sec-{slug}",
            "title": title.strip(),
            "section_type": section_type,
            "requirements": requirements,
        })

    return {
        "brd_id": brd_id,
        "source_hash": source_hash,
        "file_type": file_type,
        "validation_status": "valid",
        "sections": sections,
        "metadata": {
            "domain": domain,
            "estimated_complexity": complexity,
            "nfr_present": nfr_present,
            "contradictions_detected": CONTRADICTION_MARKER in raw.lower(),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("brd_path")
    parser.add_argument("-o", "--out", help="write parsed JSON here instead of stdout")
    parser.add_argument("--validate", action="store_true", help="validate the result against schemas/parsed_brd.schema.json")
    args = parser.parse_args()

    parsed = parse_brd(args.brd_path)

    req_counts = {}
    for s in parsed["sections"]:
        for r in s["requirements"]:
            req_counts[r["classification"]] = req_counts.get(r["classification"], 0) + 1
    print(f"brd_id={parsed['brd_id']} sections={len(parsed['sections'])} "
          f"requirements={sum(req_counts.values())} {req_counts} "
          f"domain={parsed['metadata']['domain']} complexity={parsed['metadata']['estimated_complexity']} "
          f"contradictions_detected={parsed['metadata']['contradictions_detected']}")

    if args.validate:
        from guardrails import validate_schema
        ok, event = validate_schema(parsed, "parsed_brd")
        print(f"[schema validation] {'PASSED' if ok else 'FAILED: ' + event['detail']}")

    out_text = json.dumps(parsed, indent=2)
    if args.out:
        Path(args.out).write_text(out_text + "\n")
        print(f"wrote {args.out}")
    else:
        print(out_text)


if __name__ == "__main__":
    main()
