#!/usr/bin/env python3
"""
Synthesizes the sample voice queries used to verify RAG-connected voice
queries (BRD Section 14 "Voice Interface Agent" stretch goal) -- distinct
from samples/voice_queries/ (which are EM questions about a run's live
artifacts, e.g. Critic scores, and are NOT meant to hit the static KB).
These 3 are genuine questions about KB content (plan templates, architecture
patterns, tech stack decisions), each paired with the agent scope
scripts/voice_query.py should retrieve them against.

Reproducible from source, same reasoning as generate_voice_samples.py.
Requires OPENAI_API_KEY (TTS call).

Usage:
    python scripts/generate_kb_voice_query_samples.py
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples" / "voice_queries_kb"

# Each phrasing was checked against the real KB before being adopted here --
# all three return strongly relevant top hits (0.49-0.70 similarity), not
# picked blind and hoped for.
SAMPLE_QUERIES = [
    {
        "file": "kb-query-01.mp3",
        "text": "What does the engineering plan template for a medium complexity feature include?",
        "agent": "plan_generator",
    },
    {
        "file": "kb-query-02.mp3",
        "text": "What architecture pattern works well for an event driven e-commerce checkout integration?",
        "agent": "solution_architect",
    },
    {
        "file": "kb-query-03.mp3",
        "text": "What tech stack decisions have worked well for past e-commerce projects?",
        "agent": "tech_stack_recommender",
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
