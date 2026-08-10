"""
Regression test for scripts/tts.py (the TTS piece of the Voice Interface
stretch goal, BRD Section 14). Verifies that spoken summaries built from real
Critic reviews are actually intelligible -- round-tripped back through
Whisper (scripts/asr.py) and checked against the original text -- not just
assumed to sound fine.

Same reasoning as tests/test_asr.py: no offline fallback exists for either
TTS or ASR, so the network-dependent cases are skipped -- not failed --
when OPENAI_API_KEY isn't set.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tts import build_spoken_summary, run_demo  # noqa: E402

requires_openai = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="scripts/tts.py has no offline fallback -- requires OPENAI_API_KEY",
)


# ---------------------------------------------------------------------------
# Pure logic -- no network required
# ---------------------------------------------------------------------------

def test_build_spoken_summary_green_badge_says_no_revision_required():
    result = {
        "target_agent_id": "plan_generator", "overall_score": 4.62, "badge": "green",
        "revision_required": False, "dimension_failures": [],
    }
    text = build_spoken_summary(result)
    assert "plan generator" in text
    assert "4.62" in text
    assert "green badge" in text
    assert "No revision is required" in text
    assert "_" not in text  # agent_id underscores replaced for spoken form


def test_build_spoken_summary_red_badge_lists_dimension_failures():
    result = {
        "target_agent_id": "plan_generator", "overall_score": 3.38, "badge": "red",
        "revision_required": True,
        "dimension_failures": [
            {"dimension": "groundedness", "reason": "Citations missing.", "specific_feedback": "Add citations."},
            {"dimension": "completeness", "reason": "5 requirements missing.", "specific_feedback": "Add coverage."},
        ],
    }
    text = build_spoken_summary(result)
    assert "Revision is required" in text
    assert "Groundedness: Citations missing." in text
    assert "Completeness: 5 requirements missing." in text


# ---------------------------------------------------------------------------
# Real synthesis + round-trip ASR verification
# ---------------------------------------------------------------------------

@requires_openai
def test_demo_summaries_are_verified_intelligible():
    """Both the rev0 (Red) and rev1 (Green) spoken summaries must round-trip
    through Whisper with high word overlap -- the closest automatable proxy
    for BRD Section 14's 'intelligible TTS' minimum-viable bar."""
    results = run_demo()
    assert len(results) == 2
    failed = [r for r in results if not r["intelligible"]]
    assert not failed, f"Unintelligible summary/summaries: {failed}"
    for r in results:
        assert r["word_overlap"] >= 0.7
        assert Path(r["audio_path"]).exists()
        assert Path(r["audio_path"]).stat().st_size > 0
