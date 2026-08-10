#!/usr/bin/env python3
"""
Synthesizes the 5 sample EM voice queries used to verify ASR (BRD Section 14
"Voice Interface Agent" stretch goal, minimum-viable bar: "ASR verified on at
least five sample queries"). Uses OpenAI TTS (`tts-1`) to generate realistic
spoken audio for a fixed set of BRD-review questions, and writes
samples/voice_queries/ground_truth.json recording the exact text each clip
was synthesized from -- that ground truth is what scripts/asr.py --demo
checks Whisper's transcription against.

This exists so the ASR samples are reproducible from source (the query text
lives in code, not just as opaque binary audio files) -- same reasoning as
kb/'s synthetic content being source-of-truth markdown rather than a
pre-built vector index. Regenerating costs a handful of small TTS calls;
requires OPENAI_API_KEY (no offline fallback, same as scripts/asr.py).

Usage:
    python scripts/generate_voice_samples.py
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples" / "voice_queries"

# Realistic EM voice queries spanning the interaction types the stretch goal
# describes: asking about a specific score, asking why a badge landed where
# it did, asking about generated content, and a voice approval/rejection
# command. Deliberately phrased as spoken questions, not typed CLI syntax.
SAMPLE_QUERIES = [
    {
        "file": "query-01.mp3",
        "text": "What is the overall Critic score for the engineering plan?",
    },
    {
        "file": "query-02.mp3",
        "text": "Why did the plan generator receive an amber badge?",
    },
    {
        "file": "query-03.mp3",
        "text": "Which architecture pattern was selected for the loyalty points engine?",
    },
    {
        "file": "query-04.mp3",
        "text": "List the requirements that are still missing from the current revision.",
    },
    {
        "file": "query-05.mp3",
        "text": "Approve the plan generator output and proceed to the next agent.",
    },
]


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required to synthesize voice samples (TTS call).")

    from openai import OpenAI
    client = OpenAI()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for entry in SAMPLE_QUERIES:
        out_path = SAMPLES_DIR / entry["file"]
        response = client.audio.speech.create(model="tts-1", voice="alloy", input=entry["text"])
        response.write_to_file(out_path)
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes) <- {entry['text']!r}")

    ground_truth_path = SAMPLES_DIR / "ground_truth.json"
    ground_truth_path.write_text(json.dumps(SAMPLE_QUERIES, indent=2) + "\n")
    print(f"wrote {ground_truth_path}")


if __name__ == "__main__":
    main()
