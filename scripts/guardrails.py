#!/usr/bin/env python3
"""
Guardrails: input validation, schema compliance, hallucination detection,
scope-creep detection, and confidentiality-safe structured logging.
Implements BRD Section 8. Cross-agent consistency is enforced by the Critic
(see critic.py::cross_agent_consistency_checks) and is intentionally not
duplicated here.

Every check returns (passed: bool, event: dict | None), where event matches
the guardrail_events[] item shape used in schemas/orchestrator_state.schema.json:
    {"type": ..., "agent_id": ..., "detail": ..., "action_taken": ...}
`event` is None when the check passed cleanly (nothing worth logging).

Usage (demo):
    python scripts/guardrails.py --demo
"""
import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

import jsonschema

from critic import rule_based_groundedness

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
LOGS_DIR = REPO_ROOT / "logs"

ALLOWED_BRD_FILE_TYPES = {".pdf", ".docx", ".md", ".txt"}

SCHEMA_FILES = {
    "parsed_brd": "parsed_brd.schema.json",
    "engineering_plan": "engineering_plan.schema.json",
    "schedule_estimate": "schedule_estimate.schema.json",
    "solution_architecture": "solution_architecture.schema.json",
    "poc_plan": "poc_plan.schema.json",
    "tech_stack_recommendation": "tech_stack_recommendation.schema.json",
    "critic_review": "critic_review.schema.json",
    "orchestrator_state": "orchestrator_state.schema.json",
}


def _event(type_, agent_id, detail, action_taken):
    return {"type": type_, "agent_id": agent_id, "detail": detail, "action_taken": action_taken}


def hash_content(text: str) -> str:
    """Confidentiality guardrail: never log raw BRD content, only its hash."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 1. Input validation -- reject malformed BRDs before Layer 1 parsing
# --------------------------------------------------------------------------

def validate_brd_file(path):
    """Checks file type and minimal structural sanity. Deep section
    extraction is Layer 1's job, not this guardrail's -- this only rejects
    what should never reach the parser at all."""
    path = Path(path)
    if not path.exists():
        return False, _event("input_validation", "orchestrator", f"File not found: {path.name}", "rejected")
    if path.suffix.lower() not in ALLOWED_BRD_FILE_TYPES:
        return False, _event(
            "input_validation", "orchestrator",
            f"Unsupported file type '{path.suffix}'. Allowed: {sorted(ALLOWED_BRD_FILE_TYPES)}",
            "rejected",
        )
    text = path.read_text(errors="ignore")
    if not text.strip():
        return False, _event("input_validation", "orchestrator", "File is empty.", "rejected")
    if path.suffix.lower() in (".md", ".txt") and "#" not in text:
        return False, _event(
            "input_validation", "orchestrator",
            "No section headings found -- file does not look like a structured BRD.",
            "rejected",
        )
    return True, None


# --------------------------------------------------------------------------
# 2. Schema compliance -- validate every agent output at every handoff
# --------------------------------------------------------------------------

def validate_schema(output: dict, schema_name: str):
    schema_file = SCHEMA_FILES[schema_name]
    schema = json.loads((SCHEMAS_DIR / schema_file).read_text())
    common_schema = json.loads((SCHEMAS_DIR / "common.schema.json").read_text())
    resolver = jsonschema.RefResolver(
        base_uri=f"file://{SCHEMAS_DIR}/", referrer=schema, store={"common.schema.json": common_schema}
    )
    validator = jsonschema.Draft7Validator(schema, resolver=resolver)
    errors = sorted(validator.iter_errors(output), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:5])
        return False, _event("schema_compliance", output.get("agent_id", "unknown"), detail, "rejected")
    return True, None


# --------------------------------------------------------------------------
# 3. Hallucination detection -- reuses the same citation-validity check the
#    Critic uses to cap groundedness, but surfaces it as a guardrail event
#    the Orchestrator can act on independent of Critic scoring.
# --------------------------------------------------------------------------

def detect_hallucinated_citations(output: dict, retrieved_chunks: list):
    retrieved_chunk_ids = {c["chunk_id"] for c in retrieved_chunks}
    result = rule_based_groundedness(output, retrieved_chunk_ids)
    if result["has_hallucinated_citation"]:
        bad_ids = [c["chunk_id"] for c in result["invalid_citations"]]
        detail = f"Citation(s) reference chunk_id(s) never retrieved for this run: {bad_ids}"
        return False, _event("hallucination", output.get("agent_id", "unknown"), detail, "flagged")
    return True, None


# --------------------------------------------------------------------------
# 4. Scope creep -- no requirements introduced that aren't in the source BRD
# --------------------------------------------------------------------------

def detect_scope_creep(output: dict, parsed_brd: dict):
    all_ids = {r["requirement_id"] for s in parsed_brd["sections"] for r in s.get("requirements", [])}
    claimed = set(output.get("requirement_ids_addressed", []))
    invented = claimed - all_ids
    if invented:
        detail = f"Output references requirement_id(s) not present in the source BRD: {sorted(invented)}"
        return False, _event("scope_creep", output.get("agent_id", "unknown"), detail, "flagged")
    return True, None


# --------------------------------------------------------------------------
# 5. Confidentiality -- redact raw source content before it ever reaches a log
# --------------------------------------------------------------------------

def redact_for_logging(output: dict) -> dict:
    """Returns a deep copy safe to log: citation 'excerpt' fields (which may
    carry raw BRD/org-standard text) are replaced with their hash. Everything
    else is structural/derived (ids, scores, phase names) and is kept as-is."""
    redacted = copy.deepcopy(output)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "excerpt" and isinstance(v, str):
                    obj[k] = hash_content(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(redacted)
    return redacted


def log_agent_execution(log_path, *, run_id, agent_id, brd_id, input_text=None,
                         rag_chunks_retrieved=None, output=None, critic_score=None,
                         execution_time_ms=None, guardrail_events=None, revision_count=0):
    """Structured JSONL log per BRD Section 9. Raw BRD/source content is
    never written -- input_text is hashed, and citation excerpts inside
    `output` are redacted via redact_for_logging before being written."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id,
        "agent_id": agent_id,
        "brd_id": brd_id,
        "input_hash": hash_content(input_text) if input_text else None,
        "rag_chunks_retrieved": [c.get("chunk_id") for c in (rag_chunks_retrieved or [])],
        "output_produced": redact_for_logging(output) if output else None,
        "critic_score": critic_score,
        "execution_time_ms": execution_time_ms,
        "guardrail_triggers": guardrail_events or [],
        "revision_count": revision_count,
    }
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


# --------------------------------------------------------------------------
# Convenience: run every applicable check for one agent handoff in one call
# --------------------------------------------------------------------------

def run_guardrails(output: dict, schema_name: str, parsed_brd: dict = None, retrieved_chunks: list = None):
    """Runs schema compliance, hallucination detection, and (if parsed_brd
    is given) scope-creep detection. Returns (all_passed, events) where
    events includes one entry per triggered guardrail (empty list if clean).
    Schema-invalid output short-circuits the remaining checks -- there's no
    reliable way to check citations/requirement_ids on a structurally broken
    payload.
    """
    events = []

    ok, event = validate_schema(output, schema_name)
    if not ok:
        events.append(event)
        return False, events  # schema violation blocks downstream checks

    ok, event = detect_hallucinated_citations(output, retrieved_chunks or [])
    if not ok:
        events.append(event)

    if parsed_brd is not None:
        ok, event = detect_scope_creep(output, parsed_brd)
        if not ok:
            events.append(event)

    return len(events) == 0, events


# --------------------------------------------------------------------------
# CLI demo
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if not args.demo:
        parser.error("only --demo is supported currently; import the functions directly for other uses")

    fixtures = REPO_ROOT / "fixtures"

    print("=== 1. Input validation ===")
    for label, path in [
        ("valid BRD (brd-002)", REPO_ROOT / "kb" / "past_brds" / "brd-002-medium.md"),
        ("empty file", fixtures / "malformed_empty.txt"),
        ("wrong extension", fixtures / "malformed_wrong_type.exe"),
    ]:
        ok, event = validate_brd_file(path)
        print(f"  [{label}] passed={ok}" + (f" -- {event['detail']}" if event else ""))

    print("\n=== 2. Schema compliance ===")
    rev1 = json.loads((fixtures / "engineering_plan_brd-002_rev1.json").read_text())
    ok, event = validate_schema(rev1, "engineering_plan")
    print(f"  rev1 (well-formed) passed={ok}" + (f" -- {event['detail']}" if event else ""))
    broken = copy.deepcopy(rev1)
    del broken["phases"]  # required field
    ok, event = validate_schema(broken, "engineering_plan")
    print(f"  rev1 minus required 'phases' field passed={ok}" + (f" -- {event['detail']}" if event else ""))

    print("\n=== 3. Hallucination detection ===")
    retrieved = json.loads((fixtures / "retrieved_chunks_run-001_plan_generator.json").read_text())
    rev0 = json.loads((fixtures / "engineering_plan_brd-002_rev0.json").read_text())
    ok, event = detect_hallucinated_citations(rev0, retrieved)
    print(f"  rev0 (no citations, nothing invalid) passed={ok}")
    faked = copy.deepcopy(rev1)
    faked["citations"].append({"source_id": "made-up", "source_type": "past_brd", "chunk_id": "made-up#0"})
    ok, event = detect_hallucinated_citations(faked, retrieved)
    print(f"  rev1 + a citation to a never-retrieved chunk passed={ok}" + (f" -- {event['detail']}" if event else ""))

    print("\n=== 4. Scope creep ===")
    parsed_brd = json.loads((fixtures / "parsed_brd_brd-002.json").read_text())
    ok, event = detect_scope_creep(rev1, parsed_brd)
    print(f"  rev1 (all real requirement_ids) passed={ok}")
    creepy = copy.deepcopy(rev1)
    creepy["requirement_ids_addressed"].append("FR-99")
    ok, event = detect_scope_creep(creepy, parsed_brd)
    print(f"  rev1 + invented 'FR-99' passed={ok}" + (f" -- {event['detail']}" if event else ""))

    print("\n=== 5. Confidentiality-safe logging ===")
    log_path = REPO_ROOT / "logs" / "demo.jsonl"
    brd_raw_text = (REPO_ROOT / "kb" / "past_brds" / "brd-002-medium.md").read_text()
    entry = log_agent_execution(
        log_path,
        run_id="run-001",
        agent_id="plan_generator",
        brd_id="brd-002",
        input_text=brd_raw_text,
        rag_chunks_retrieved=retrieved,
        output=rev1,
        critic_score=4.62,
        execution_time_ms=842,
        guardrail_events=[],
        revision_count=1,
    )
    assert brd_raw_text not in json.dumps(entry), "raw BRD content leaked into log entry!"
    print(f"  wrote entry to {log_path}")
    print(f"  input_hash: {entry['input_hash']}")
    print(f"  confirmed: raw BRD text not present anywhere in the logged entry")

    print("\n=== 6. Combined run_guardrails() ===")
    ok, events = run_guardrails(rev1, "engineering_plan", parsed_brd=parsed_brd, retrieved_chunks=retrieved)
    print(f"  rev1: all_passed={ok}, events={events}")
    ok, events = run_guardrails(creepy, "engineering_plan", parsed_brd=parsed_brd, retrieved_chunks=retrieved)
    print(f"  rev1+scope-creep: all_passed={ok}, events={[e['type'] for e in events]}")


if __name__ == "__main__":
    main()
