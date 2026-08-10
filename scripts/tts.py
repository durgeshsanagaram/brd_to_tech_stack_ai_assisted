#!/usr/bin/env python3
"""
TTS for spoken summaries -- the TTS piece of BRD Section 14's "Voice
Interface Agent" stretch goal. Turns a Critic review (badge, overall score,
dimension feedback) into a short natural-language summary and synthesizes it
to speech via OpenAI's TTS API (`tts-1`), so an EM could hear "how did this
agent's output score" instead of reading JSON.

Scope: this implements TTS only -- summary text in, spoken audio out. It
does NOT implement voice approval/rejection wired into the Orchestrator, or
a live EM-facing playback UI; those are separate, unimplemented pieces of
the stretch goal (see README's "Voice Interface (stretch goal)" section).

No offline fallback, same reasoning as scripts/asr.py: local TTS needs a
model + inference stack not justified for this scope. Requires
OPENAI_API_KEY.

"Intelligible" is verified, not just assumed: --demo round-trips each
synthesized summary back through scripts/asr.py's Whisper transcription and
checks word overlap against the original text -- if Whisper (or, by proxy, a
human listener) can't recover the words, it isn't intelligible.

Usage:
    python scripts/tts.py --demo
    python scripts/tts.py --text "Custom summary text" --out /tmp/out.mp3
"""
import argparse
import json
import os
from pathlib import Path

from asr import transcribe, word_overlap_ratio
from critic import mock_judge_fn, review

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
SAMPLES_DIR = REPO_ROOT / "samples" / "tts_summaries"

# Same bar as ASR's word-overlap check -- reusing one threshold for both
# directions of the voice round-trip rather than inventing a second number.
INTELLIGIBILITY_THRESHOLD = 0.7


def synthesize(text, out_path, voice="alloy", model="tts-1"):
    """Sends text to OpenAI's TTS API and writes the resulting audio to
    out_path. Raises if OPENAI_API_KEY is unset (see module docstring --
    there is no offline fallback for this)."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is required -- scripts/tts.py has no offline "
            "synthesis fallback (see module docstring)."
        )
    from openai import OpenAI
    client = OpenAI()
    response = client.audio.speech.create(model=model, voice=voice, input=text)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    response.write_to_file(out_path)
    return out_path


def build_spoken_summary(critic_review_result):
    """Turns a critic_review dict (schemas/critic_review.schema.json) into a
    short natural-language summary suitable for reading aloud."""
    agent = critic_review_result["target_agent_id"].replace("_", " ")
    score = critic_review_result["overall_score"]
    badge = critic_review_result["badge"]
    parts = [f"{agent} scored {score} out of 5 overall, landing a {badge} badge."]
    if critic_review_result["revision_required"]:
        parts.append("Revision is required.")
        for failure in critic_review_result["dimension_failures"]:
            parts.append(f"{failure['dimension'].capitalize()}: {failure['reason']}")
    else:
        parts.append("No revision is required.")
    return " ".join(parts)


def run_demo():
    """Builds spoken summaries for the documented rev0 (Red) and rev1
    (Green) Critic reviews (docs/evaluation_report.md Section 4), synthesizes
    each to audio, and round-trips it back through Whisper to verify the
    result is actually intelligible rather than just assuming it. Returns a
    list of per-case result dicts so tests/test_tts.py can assert on them."""
    parsed_brd = json.loads((FIXTURES_DIR / "parsed_brd_brd-002.json").read_text())
    retrieved = json.loads((FIXTURES_DIR / "retrieved_chunks_run-001_plan_generator.json").read_text())
    rev0 = json.loads((FIXTURES_DIR / "engineering_plan_brd-002_rev0.json").read_text())
    rev1 = json.loads((FIXTURES_DIR / "engineering_plan_brd-002_rev1.json").read_text())

    cases = [
        ("rev0-red", review(rev0, parsed_brd, retrieved, judge_fn=mock_judge_fn)),
        ("rev1-green", review(rev1, parsed_brd, retrieved, judge_fn=mock_judge_fn)),
    ]

    results = []
    for label, critic_review_result in cases:
        summary_text = build_spoken_summary(critic_review_result)
        out_path = SAMPLES_DIR / f"{label}.mp3"
        synthesize(summary_text, out_path)
        transcript = transcribe(out_path)
        overlap = word_overlap_ratio(summary_text, transcript)
        results.append({
            "label": label,
            "text": summary_text,
            "audio_path": str(out_path),
            "transcript": transcript,
            "word_overlap": overlap,
            "intelligible": overlap >= INTELLIGIBILITY_THRESHOLD,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text", help="text to synthesize")
    parser.add_argument("--out", help="output audio file path")
    parser.add_argument("--voice", default="alloy")
    parser.add_argument(
        "--demo", action="store_true",
        help="synthesize spoken summaries for the rev0/rev1 Critic reviews and verify intelligibility via round-trip ASR",
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required (see module docstring, no offline fallback).")

    if args.demo:
        results = run_demo()
        for r in results:
            print(f"[{'PASS' if r['intelligible'] else 'FAIL'}] {r['label']} (round-trip word overlap {r['word_overlap']:.0%})")
            print(f"  text:       {r['text']}")
            print(f"  audio:      {r['audio_path']}")
            print(f"  round-trip: {r['transcript']}\n")
        passed = sum(r["intelligible"] for r in results)
        print(f"{passed}/{len(results)} summaries verified intelligible (>= {INTELLIGIBILITY_THRESHOLD:.0%} round-trip word overlap)")
        return

    if not (args.text and args.out):
        parser.error("provide --text and --out, or use --demo")
    path = synthesize(args.text, args.out, voice=args.voice)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
