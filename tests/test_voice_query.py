"""
Regression test for scripts/voice_query.py: verifies the full ASR -> Chroma
retrieval pipeline actually returns relevant results for real KB-oriented
voice queries -- the "RAG-connected voice queries" piece of BRD Section 14's
Voice Interface stretch goal, wiring scripts/asr.py's Whisper transcription
directly into scripts/query.py's retrieval.

Skipped (not failed) without OPENAI_API_KEY, since transcription has no
offline fallback (see scripts/asr.py's module docstring).
"""
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from voice_query import voice_query  # noqa: E402

KB_SAMPLES_DIR = REPO_ROOT / "samples" / "voice_queries_kb"
GROUND_TRUTH = json.loads((KB_SAMPLES_DIR / "ground_truth.json").read_text())

requires_openai = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="scripts/voice_query.py has no offline ASR fallback -- requires OPENAI_API_KEY",
)


@requires_openai
@pytest.mark.parametrize("entry", GROUND_TRUTH, ids=[e["file"] for e in GROUND_TRUTH])
def test_kb_voice_query_retrieves_relevant_chunks(kb_collection, entry):
    """Each sample is a real spoken question about KB content (not a live
    run's artifacts), pre-checked to retrieve strongly relevant hits when
    typed -- this confirms the same holds true end-to-end through Whisper."""
    audio_path = KB_SAMPLES_DIR / entry["file"]
    result = voice_query(audio_path, kb_collection, agent=entry["agent"])
    assert result["transcript"]
    assert len(result["kept"]) > 0, f"{entry['file']}: expected at least one relevant KB hit"
    for hit in result["kept"]:
        assert hit["similarity"] >= 0.30
