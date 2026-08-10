"""
Regression tests for scripts/guardrails.py, covering all 5 guardrails
(input validation, schema compliance, hallucination detection, scope creep,
confidentiality-safe logging) plus the combined run_guardrails() entrypoint.
Codifies what guardrails.py --demo previously only demonstrated by hand --
see docs/guardrails_safety.md for the design rationale behind each check.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from guardrails import (  # noqa: E402
    detect_hallucinated_citations,
    detect_scope_creep,
    hash_content,
    log_agent_execution,
    redact_for_logging,
    run_guardrails,
    validate_brd_file,
    validate_schema,
)

FIXTURES_DIR = REPO_ROOT / "fixtures"
VALID_BRD = REPO_ROOT / "kb" / "past_brds" / "brd-002-medium.md"


# ---------------------------------------------------------------------------
# 1. Input validation
# ---------------------------------------------------------------------------

def test_validate_brd_file_accepts_a_real_brd():
    ok, event = validate_brd_file(VALID_BRD)
    assert ok is True
    assert event is None


def test_validate_brd_file_rejects_missing_file(tmp_path):
    ok, event = validate_brd_file(tmp_path / "does-not-exist.md")
    assert ok is False
    assert event["type"] == "input_validation"
    assert "not found" in event["detail"].lower()


def test_validate_brd_file_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("")
    ok, event = validate_brd_file(empty)
    assert ok is False
    assert "empty" in event["detail"].lower()


def test_validate_brd_file_rejects_disallowed_extension(tmp_path):
    exe = tmp_path / "not-a-brd.exe"
    exe.write_text("# Looks like markdown but isn't allowed")
    ok, event = validate_brd_file(exe)
    assert ok is False
    assert "unsupported file type" in event["detail"].lower()


def test_validate_brd_file_rejects_unstructured_text(tmp_path):
    """.md/.txt with no '#' heading at all doesn't look like a structured
    BRD -- rejected before Layer 1 parsing ever sees it."""
    unstructured = tmp_path / "no-headings.md"
    unstructured.write_text("just some prose with no headings whatsoever")
    ok, event = validate_brd_file(unstructured)
    assert ok is False
    assert "heading" in event["detail"].lower()


# ---------------------------------------------------------------------------
# 2. Schema compliance
# ---------------------------------------------------------------------------

def test_validate_schema_accepts_wellformed_engineering_plan(engineering_plan_rev1):
    ok, event = validate_schema(engineering_plan_rev1, "engineering_plan")
    assert ok is True
    assert event is None


def test_validate_schema_rejects_missing_required_field(engineering_plan_rev1):
    broken = copy.deepcopy(engineering_plan_rev1)
    del broken["phases"]
    ok, event = validate_schema(broken, "engineering_plan")
    assert ok is False
    assert "phases" in event["detail"]
    assert event["type"] == "schema_compliance"


# ---------------------------------------------------------------------------
# 3. Hallucination detection
# ---------------------------------------------------------------------------

def test_detect_hallucinated_citations_passes_with_no_citations(engineering_plan_rev0, retrieved_chunks):
    ok, event = detect_hallucinated_citations(engineering_plan_rev0, retrieved_chunks)
    assert ok is True
    assert event is None


def test_detect_hallucinated_citations_flags_never_retrieved_chunk(engineering_plan_rev1, retrieved_chunks):
    faked = copy.deepcopy(engineering_plan_rev1)
    faked["citations"].append({
        "source_id": "made-up", "source_type": "past_brd", "chunk_id": "made-up#0",
        "excerpt": "this chunk was never retrieved", "similarity_score": 0.9,
    })
    ok, event = detect_hallucinated_citations(faked, retrieved_chunks)
    assert ok is False
    assert "made-up#0" in event["detail"]
    assert event["type"] == "hallucination"


def test_detect_hallucinated_citations_passes_when_citations_all_valid(engineering_plan_rev1, retrieved_chunks):
    ok, event = detect_hallucinated_citations(engineering_plan_rev1, retrieved_chunks)
    assert ok is True
    assert event is None


# ---------------------------------------------------------------------------
# 4. Scope creep
# ---------------------------------------------------------------------------

def test_detect_scope_creep_passes_for_real_requirement_ids(engineering_plan_rev1, parsed_brd):
    ok, event = detect_scope_creep(engineering_plan_rev1, parsed_brd)
    assert ok is True
    assert event is None


def test_detect_scope_creep_flags_invented_requirement_id(engineering_plan_rev1, parsed_brd):
    creepy = copy.deepcopy(engineering_plan_rev1)
    creepy["requirement_ids_addressed"].append("FR-99")
    ok, event = detect_scope_creep(creepy, parsed_brd)
    assert ok is False
    assert "FR-99" in event["detail"]
    assert event["type"] == "scope_creep"


# ---------------------------------------------------------------------------
# 5. Confidentiality-safe logging
# ---------------------------------------------------------------------------

def test_hash_content_is_deterministic_sha256():
    h1 = hash_content("some raw BRD text")
    h2 = hash_content("some raw BRD text")
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert h1 != hash_content("different text")


def test_redact_for_logging_hashes_excerpts_only(engineering_plan_rev1):
    redacted = redact_for_logging(engineering_plan_rev1)
    for original, red in zip(engineering_plan_rev1["citations"], redacted["citations"]):
        assert red["excerpt"] == hash_content(original["excerpt"])
        assert red["excerpt"] != original["excerpt"]
        # structural fields untouched
        assert red["chunk_id"] == original["chunk_id"]
        assert red["source_type"] == original["source_type"]
    # non-citation structural content is unaffected
    assert redacted["phases"] == engineering_plan_rev1["phases"]
    # original is not mutated (redact_for_logging deep-copies)
    assert engineering_plan_rev1["citations"][0]["excerpt"] != redacted["citations"][0]["excerpt"]


def test_log_agent_execution_never_writes_raw_brd_text(tmp_path, engineering_plan_rev1, retrieved_chunks):
    log_path = tmp_path / "test.jsonl"
    brd_raw_text = VALID_BRD.read_text()

    entry = log_agent_execution(
        log_path,
        run_id="run-test",
        agent_id="plan_generator",
        brd_id="brd-002",
        input_text=brd_raw_text,
        rag_chunks_retrieved=retrieved_chunks,
        output=engineering_plan_rev1,
        critic_score=4.62,
        execution_time_ms=842,
        guardrail_events=[],
        revision_count=1,
    )

    assert brd_raw_text not in json.dumps(entry)
    assert entry["input_hash"] == hash_content(brd_raw_text)
    assert log_path.exists()
    written = json.loads(log_path.read_text().strip())
    assert brd_raw_text not in json.dumps(written)
    assert written["run_id"] == "run-test"


def test_log_agent_execution_appends_one_jsonl_line_per_call(tmp_path, engineering_plan_rev1, retrieved_chunks):
    log_path = tmp_path / "test.jsonl"
    for i in range(3):
        log_agent_execution(
            log_path, run_id=f"run-{i}", agent_id="plan_generator", brd_id="brd-002",
            output=engineering_plan_rev1, rag_chunks_retrieved=retrieved_chunks,
        )
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # each line is valid standalone JSON


# ---------------------------------------------------------------------------
# Combined run_guardrails()
# ---------------------------------------------------------------------------

def test_run_guardrails_all_pass_for_valid_output(engineering_plan_rev1, parsed_brd, retrieved_chunks):
    ok, events = run_guardrails(engineering_plan_rev1, "engineering_plan", parsed_brd=parsed_brd, retrieved_chunks=retrieved_chunks)
    assert ok is True
    assert events == []


def test_run_guardrails_flags_scope_creep(engineering_plan_rev1, parsed_brd, retrieved_chunks):
    creepy = copy.deepcopy(engineering_plan_rev1)
    creepy["requirement_ids_addressed"].append("FR-99")
    ok, events = run_guardrails(creepy, "engineering_plan", parsed_brd=parsed_brd, retrieved_chunks=retrieved_chunks)
    assert ok is False
    assert [e["type"] for e in events] == ["scope_creep"]


def test_run_guardrails_short_circuits_on_schema_failure(engineering_plan_rev1, parsed_brd, retrieved_chunks):
    """A structurally broken output can't be reliably checked for hallucinated
    citations or scope creep, so schema failure must stop the other checks
    from running at all -- not just report alongside them."""
    broken = copy.deepcopy(engineering_plan_rev1)
    del broken["phases"]
    ok, events = run_guardrails(broken, "engineering_plan", parsed_brd=parsed_brd, retrieved_chunks=retrieved_chunks)
    assert ok is False
    assert len(events) == 1
    assert events[0]["type"] == "schema_compliance"
