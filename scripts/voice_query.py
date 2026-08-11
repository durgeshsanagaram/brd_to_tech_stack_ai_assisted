#!/usr/bin/env python3
"""
RAG-connected voice queries -- the third piece of BRD Section 14's "Voice
Interface Agent" stretch goal (ASR and TTS are implemented in scripts/asr.py
and scripts/tts.py; this wires ASR directly into retrieval). A spoken
question is transcribed via Whisper, then the transcript is run through
scripts/query.py's Chroma retrieval exactly like a typed query would be --
same per-agent source_type scoping, same similarity threshold, same
"no RAG hits" guardrail path on an irrelevant question.

Scope: this covers "voice queries retrieve from ... the source BRD" and the
rest of the synthetic KB -- source BRDs are already indexed as past_brd
chunks, so a spoken question about BRD content is answerable this way. It
does NOT cover "retrieve from artifacts": a specific run's generated agent
outputs (engineering_plan, critic_review, ...) aren't indexed anywhere, so a
question like "why did THIS run's plan land Amber" can't be answered by this
path -- only questions answerable from the static KB can. Still not
implemented: voice approval/rejection into the Orchestrator's awaiting_hitl
state (see README's "Voice Interface (stretch goal)" section).

Usage:
    python scripts/voice_query.py samples/voice_queries_kb/kb-query-01.mp3 --agent plan_generator
    python scripts/voice_query.py --demo
"""
import argparse
import json
from pathlib import Path

from asr import transcribe
from common import build_collection
from query import AGENT_SCOPES
from query import query as run_query

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_SAMPLES_DIR = REPO_ROOT / "samples" / "voice_queries_kb"
KB_GROUND_TRUTH_PATH = KB_SAMPLES_DIR / "ground_truth.json"


def voice_query(audio_path, collection, agent=None, source_types=None, top_k=None):
    """Transcribes audio_path via Whisper, then retrieves from collection
    using the same scoping scripts/query.py's --agent flag applies. Returns
    {transcript, kept, dropped}."""
    transcript = transcribe(audio_path)
    if agent:
        scope = AGENT_SCOPES[agent]
        source_types = source_types or scope["source_types"]
        top_k = top_k or scope["top_k"]
    kept, dropped = run_query(collection, transcript, source_types, top_k or 5)
    return {"transcript": transcript, "kept": kept, "dropped": dropped}


def run_demo(persist_dir="./chroma_db"):
    """Runs each sample KB-oriented voice query (samples/voice_queries_kb/)
    through the full audio -> transcript -> retrieval pipeline against the
    real Chroma collection. Returns a list of per-query result dicts so
    tests/test_voice_query.py can assert on them directly."""
    collection = build_collection(persist_dir)
    ground_truth = json.loads(KB_GROUND_TRUTH_PATH.read_text())
    results = []
    for entry in ground_truth:
        audio_path = KB_SAMPLES_DIR / entry["file"]
        result = voice_query(audio_path, collection, agent=entry["agent"])
        result.update({"file": entry["file"], "agent": entry["agent"], "expected_text": entry["text"]})
        results.append(result)
    return results


def _print_result(result):
    print(f"transcript: {result['transcript']}")
    if result["kept"]:
        for h in result["kept"]:
            m = h["metadata"]
            label = m.get("section") or m.get("title") or m["source_id"]
            print(f"  [{h['similarity']:.3f}] {m['source_type']} :: {m['source_id']} :: {label}")
    else:
        print("  No chunks above similarity threshold -- 'no RAG hits' guardrail path "
              "(question may be about live artifacts, not the static KB).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_file", nargs="?", help="path to an audio file with a spoken question")
    parser.add_argument("--agent", choices=sorted(AGENT_SCOPES), help="apply this agent's documented retrieval scope")
    parser.add_argument("--source-types", nargs="*", help="override source_type filter")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--persist-dir", default="./chroma_db")
    parser.add_argument("--demo", action="store_true", help="run all 3 sample KB voice queries end to end")
    args = parser.parse_args()

    if args.demo:
        results = run_demo(persist_dir=args.persist_dir)
        for r in results:
            print(f"[{r['agent']}] {r['file']}")
            _print_result(r)
            print()
        with_hits = sum(1 for r in results if r["kept"])
        print(f"{with_hits}/{len(results)} voice queries retrieved at least one relevant chunk from the KB")
        return

    if not args.audio_file:
        parser.error("provide an audio file, or use --demo")
    collection = build_collection(args.persist_dir)
    result = voice_query(args.audio_file, collection, agent=args.agent, source_types=args.source_types, top_k=args.top_k)
    _print_result(result)


if __name__ == "__main__":
    main()
