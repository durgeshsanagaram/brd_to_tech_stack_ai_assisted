#!/usr/bin/env python3
"""
ASR (Whisper) for EM voice queries -- the ASR piece of BRD Section 14's
"Voice Interface Agent" stretch goal. Transcribes a spoken query to text
using OpenAI's Whisper API (`whisper-1`), so the result can be handed to
scripts/query.py / the Orchestrator exactly like a typed query would be.

Scope: this implements ASR only -- transcription in, text out. It does NOT
implement the other three pieces the stretch goal describes (RAG-connected
voice-query answering, TTS spoken responses, or a voice approval/rejection
flow into the Orchestrator's awaiting_hitl state). Those are separate,
unimplemented work; see README's "Voice Interface (stretch goal)" section.

No local/offline fallback: unlike scripts/common.py's embedding fallback,
running Whisper locally needs the `openai-whisper` package plus torch and
ffmpeg -- a multi-GB dependency footprint not justified for this stretch
scope. Requires OPENAI_API_KEY; there is no Amber-style degraded path here,
the way there is for embeddings.

Usage:
    python scripts/asr.py samples/voice_queries/query-01.mp3
    python scripts/asr.py --demo   # transcribes all 5 sample queries and
                                    # checks each transcript against the
                                    # known ground truth (see
                                    # scripts/generate_voice_samples.py)
"""
import argparse
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples" / "voice_queries"
GROUND_TRUTH_PATH = SAMPLES_DIR / "ground_truth.json"

# A transcript doesn't need to match word-for-word to be "correct" for this
# use case -- Whisper may drop/add punctuation or a filler word. Word-overlap
# against the known ground truth is a simple, inspectable correctness check,
# not a formal WER (word error rate) metric.
PASS_THRESHOLD = 0.7


def transcribe(audio_path, model="whisper-1"):
    """Sends an audio file to OpenAI's Whisper API and returns the
    transcribed text. Raises if OPENAI_API_KEY is unset (see module
    docstring -- there is no offline fallback for this)."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is required -- scripts/asr.py has no offline "
            "transcription fallback (see module docstring)."
        )
    from openai import OpenAI
    client = OpenAI()
    with open(audio_path, "rb") as fh:
        result = client.audio.transcriptions.create(model=model, file=fh)
    return result.text.strip()


def _normalize_words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def word_overlap_ratio(expected_text, transcribed_text):
    """Fraction of the expected text's words that also appear in the
    transcript -- 1.0 means every expected word showed up somewhere."""
    expected_words = _normalize_words(expected_text)
    if not expected_words:
        return 0.0
    transcribed_words = _normalize_words(transcribed_text)
    return len(expected_words & transcribed_words) / len(expected_words)


def run_demo(model="whisper-1"):
    """Transcribes every sample query in samples/voice_queries/ and checks
    it against the recorded ground truth. Returns a list of per-query result
    dicts so tests/test_asr.py can assert on them directly."""
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text())
    results = []
    for entry in ground_truth:
        audio_path = SAMPLES_DIR / entry["file"]
        transcript = transcribe(audio_path, model=model)
        overlap = word_overlap_ratio(entry["text"], transcript)
        results.append({
            "file": entry["file"],
            "expected_text": entry["text"],
            "transcribed_text": transcript,
            "word_overlap": overlap,
            "passed": overlap >= PASS_THRESHOLD,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_file", nargs="?", help="path to an audio file to transcribe")
    parser.add_argument("--demo", action="store_true", help="transcribe all 5 sample queries and verify against ground truth")
    parser.add_argument("--model", default="whisper-1")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required -- see module docstring (no offline fallback).")

    if args.demo:
        results = run_demo(model=args.model)
        print(f"Transcribing {len(results)} sample queries from {SAMPLES_DIR}...\n")
        for r in results:
            print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['file']} (word overlap {r['word_overlap']:.0%})")
            print(f"  expected:    {r['expected_text']}")
            print(f"  transcribed: {r['transcribed_text']}\n")
        passed = sum(r["passed"] for r in results)
        print(f"{passed}/{len(results)} sample queries transcribed correctly (>={PASS_THRESHOLD:.0%} word overlap)")
        return

    if not args.audio_file:
        parser.error("provide an audio file, or use --demo")
    print(transcribe(args.audio_file, model=args.model))


if __name__ == "__main__":
    main()
