"""
Regression test for scripts/asr.py (the ASR piece of the Voice Interface
stretch goal, BRD Section 14). Verifies Whisper transcription against the
5 sample voice queries' known ground truth -- the minimum-viable bar the BRD
specifies ("ASR verified on at least five sample queries").

Unlike the retrieval tests, there is no offline fallback for Whisper (see
scripts/asr.py's module docstring), so this suite is skipped -- not failed
-- when OPENAI_API_KEY isn't set, rather than pretending to test something
it can't actually exercise.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from asr import run_demo, word_overlap_ratio  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="scripts/asr.py has no offline fallback -- requires OPENAI_API_KEY",
)


def test_word_overlap_ratio_identical_text_is_full_overlap():
    assert word_overlap_ratio("hello world", "hello world") == 1.0


def test_word_overlap_ratio_case_and_punctuation_insensitive():
    assert word_overlap_ratio("What is the score?", "what is the score") == 1.0


def test_word_overlap_ratio_partial_match():
    assert word_overlap_ratio("approve the plan generator", "approve the plan") == pytest.approx(0.75)


def test_all_five_sample_queries_transcribe_correctly():
    """The minimum-viable bar from BRD Section 14: 'ASR verified on at least
    five sample queries.' Runs a real Whisper API call per sample -- not
    mocked -- against samples/voice_queries/ (see
    scripts/generate_voice_samples.py for how they were synthesized)."""
    results = run_demo()
    assert len(results) == 5
    failed = [r for r in results if not r["passed"]]
    assert not failed, f"ASR mismatch(es): {failed}"
    for r in results:
        assert r["word_overlap"] >= 0.7
