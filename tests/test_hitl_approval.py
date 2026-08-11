"""
Regression tests for scripts/orchestrator.py's human-in-the-loop approval
gate -- the fourth and final piece of BRD Section 14's "Voice Interface
Agent" stretch goal (voice/text approval or rejection at the awaiting_hitl
state, replacing what used to be an unconditional auto-complete).

Network-dependent voice tests are skipped (not failed) without
OPENAI_API_KEY, same pattern as tests/test_asr.py / test_tts.py /
test_voice_query.py.
"""
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from orchestrator import classify_hitl_decision, resolve_hitl_decision, run_pipeline  # noqa: E402

APPROVALS_DIR = REPO_ROOT / "samples" / "voice_approvals"
GROUND_TRUTH = json.loads((APPROVALS_DIR / "ground_truth.json").read_text())

requires_openai = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="voice approval has no offline ASR fallback -- requires OPENAI_API_KEY",
)


# ---------------------------------------------------------------------------
# classify_hitl_decision -- pure logic, no network
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "approve",
    "Approved, looks good.",
    "Yes, go ahead and proceed.",
    "Sounds good to me.",
])
def test_classify_hitl_decision_recognizes_approval(text):
    assert classify_hitl_decision(text) == "approve"


@pytest.mark.parametrize("text", [
    "reject",
    "This is rejected, send it back.",
    "Needs work, please redo it.",
    "Not approved.",
])
def test_classify_hitl_decision_recognizes_rejection(text):
    assert classify_hitl_decision(text) == "reject"


@pytest.mark.parametrize("text", [
    "hmm, not sure",
    "let me think about it",
    "",
])
def test_classify_hitl_decision_returns_unclear_for_ambiguous_input(text):
    assert classify_hitl_decision(text) == "unclear"


def test_classify_hitl_decision_returns_unclear_when_both_keywords_present():
    """A transcript matching both keyword sets is exactly as ambiguous as
    one matching neither -- not guessed at, per BRD Section 8's
    conservative-default/ambiguity policy."""
    assert classify_hitl_decision("I approve some of it but reject the rest") == "unclear"


# ---------------------------------------------------------------------------
# resolve_hitl_decision -- text and default paths (no network)
# ---------------------------------------------------------------------------

def test_resolve_hitl_decision_uses_explicit_text():
    result = resolve_hitl_decision(approval_text="approve this")
    assert result == {"decision": "approve", "source": "text", "transcript": "approve this"}


def test_resolve_hitl_decision_defaults_to_approve_when_noninteractive_and_no_input():
    """pytest's stdin isn't a tty, so this exercises the same non-interactive
    default path CI/--demo hits with no flags supplied."""
    result = resolve_hitl_decision()
    assert result["decision"] == "approve"
    assert result["source"] == "default"
    assert result["transcript"] is None


# ---------------------------------------------------------------------------
# resolve_hitl_decision -- voice path (real Whisper calls)
# ---------------------------------------------------------------------------

@requires_openai
@pytest.mark.parametrize("entry", GROUND_TRUTH, ids=[e["file"] for e in GROUND_TRUTH])
def test_resolve_hitl_decision_from_real_voice_matches_expected(entry):
    audio_path = APPROVALS_DIR / entry["file"]
    result = resolve_hitl_decision(approval_audio=audio_path)
    assert result["source"] == "voice"
    assert result["decision"] == entry["expected_decision"]
    assert result["transcript"]


# ---------------------------------------------------------------------------
# run_pipeline() integration -- the actual control-flow branch
# ---------------------------------------------------------------------------

def test_run_pipeline_approve_text_completes(kb_persist_dir):
    state, _result = run_pipeline(persist_dir=str(kb_persist_dir), approval_text="approve, looks good")
    assert state["pipeline_status"] == "complete"
    hitl_events = [e for e in state["guardrail_events"] if e["type"] == "hitl_decision"]
    assert len(hitl_events) == 1
    assert hitl_events[0]["action_taken"] == "approved"


def test_run_pipeline_reject_text_fails_and_escalates(kb_persist_dir):
    state, _result = run_pipeline(persist_dir=str(kb_persist_dir), approval_text="reject this, needs work")
    assert state["pipeline_status"] == "failed"
    hitl_events = [e for e in state["guardrail_events"] if e["type"] == "hitl_decision"]
    assert len(hitl_events) == 2
    assert hitl_events[0]["action_taken"] == "rejected"
    assert hitl_events[1]["action_taken"] == "escalated"


def test_run_pipeline_unclear_text_fails_and_escalates(kb_persist_dir):
    state, _result = run_pipeline(persist_dir=str(kb_persist_dir), approval_text="not sure")
    assert state["pipeline_status"] == "failed"
    hitl_events = [e for e in state["guardrail_events"] if e["type"] == "hitl_decision"]
    assert hitl_events[0]["action_taken"] == "escalated"


def test_run_pipeline_no_approval_input_defaults_to_complete(kb_persist_dir):
    """Matches the pre-existing --demo behavior with no flags: non-interactive,
    no input supplied -> auto-approve, but now logged explicitly instead of
    silently skipped."""
    state, _result = run_pipeline(persist_dir=str(kb_persist_dir))
    assert state["pipeline_status"] == "complete"
    hitl_events = [e for e in state["guardrail_events"] if e["type"] == "hitl_decision"]
    assert hitl_events[0]["detail"].startswith("EM decision: approve (source=default")
