#!/usr/bin/env python3
"""
Synthesizes the sample EM approval/rejection voice commands used to verify
the voice-driven human-in-the-loop gate (BRD Section 14 "Voice Interface
Agent" stretch goal's fourth piece: voice approval/rejection into the
Orchestrator's awaiting_hitl state). Reproducible from source, same
reasoning as generate_voice_samples.py / generate_kb_voice_query_samples.py.
Requires OPENAI_API_KEY (TTS call).

Usage:
    python scripts/generate_approval_voice_samples.py
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples" / "voice_approvals"

# expected_decision is what scripts/orchestrator.py::classify_hitl_decision
# should return for this clip's transcript.
SAMPLE_APPROVALS = [
    {"file": "approve-01.mp3", "text": "This looks good, approve it and proceed.", "expected_decision": "approve"},
    {"file": "reject-01.mp3", "text": "This needs to be redone, please reject it.", "expected_decision": "reject"},
    {"file": "unclear-01.mp3", "text": "Hmm, let me think about it for a bit.", "expected_decision": "unclear"},
]


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required to synthesize voice samples (TTS call).")

    from openai import OpenAI
    client = OpenAI()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for entry in SAMPLE_APPROVALS:
        out_path = SAMPLES_DIR / entry["file"]
        response = client.audio.speech.create(model="tts-1", voice="alloy", input=entry["text"])
        response.write_to_file(out_path)
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes) <- {entry['text']!r}")

    ground_truth_path = SAMPLES_DIR / "ground_truth.json"
    ground_truth_path.write_text(json.dumps(SAMPLE_APPROVALS, indent=2) + "\n")
    print(f"wrote {ground_truth_path}")


if __name__ == "__main__":
    main()
