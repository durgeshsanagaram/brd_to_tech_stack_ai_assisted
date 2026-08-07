#!/usr/bin/env python3
"""
Single entrypoint that chains every script in this repo into one pipeline run,
in the order the README documents them individually:

  1. guardrails.py  -- input validation on the BRD file, before anything else touches it
  2. ingest.py      -- (re)build the Chroma KB from kb/
  3. query.py       -- retrieval smoke test (one probe query per agent scope)
  4. orchestrator.py -- 5 agents + Critic (critic.py) + guardrails + revision loop, end-to-end
  5. evaluation summary -- badges/scores pulled straight from the orchestrator run

This is a wiring convenience, not new logic: every step below calls the same
functions the standalone scripts call, in-process, so results match running
them one at a time by hand.

Layer 1 parsing (scripts/brd_parser.py) is real -- --brd works for any BRD
following kb/past_brds/'s frontmatter + '## Section' + 'FR-N:'/'NFR-N:' bullet
structure, not just brd-002. Generation (the 5 specialist agents) is still
pluggable stubs, not a live LLM call (see README "Notes on What's a Live Call
vs. a Stand-In"): plan_generator has a real fixture-backed rev0->rev1 demo for
brd-002 specifically, and falls back to a minimal generic stub plan for any
other BRD; the other 4 agents are minimal stubs for every BRD. Guardrails,
retrieval, and the Critic all run for real regardless of which BRD you pass.

Usage:
    python scripts/run_all.py                                        # ingest + full pipeline against brd-002
    python scripts/run_all.py --brd kb/past_brds/brd-003-complex.md   # same, but for brd-003
    python scripts/run_all.py --skip-ingest                          # reuse the existing ./chroma_db
    python scripts/run_all.py --no-smoke-test                        # skip step 3
"""
import argparse
import sys
from pathlib import Path

import jsonschema

from common import build_collection
import guardrails
import ingest
import query as query_mod
import orchestrator
from brd_parser import parse_brd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRD = REPO_ROOT / "kb" / "past_brds" / "brd-002-medium.md"


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run_all(brd_path=DEFAULT_BRD, persist_dir="./chroma_db", skip_ingest=False, smoke_test=True):
    brd_path = Path(brd_path)

    section("1/5  Input validation (guardrails.validate_brd_file)")
    ok, event = guardrails.validate_brd_file(brd_path)
    if event:
        print(f"  [{event['type']}] {event['detail']} -> {event['action_taken']}")
    if not ok:
        print("  BRD failed input validation -- stopping before ingest/generation.")
        sys.exit(1)
    print(f"  OK: {brd_path.name}")

    if skip_ingest:
        section("2/5  Ingest KB into Chroma (skipped: --skip-ingest)")
        collection = build_collection(persist_dir)
    else:
        section("2/5  Ingest KB into Chroma")
        chunks = ingest.load_all_chunks()
        collection = build_collection(persist_dir, reset=True)
        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
        )
        print(f"  Upserted {len(chunks)} chunks into '{collection.name}' at {persist_dir}")

    if smoke_test:
        section("3/5  RAG retrieval smoke test (query.py)")
        parsed_probe = parse_brd(brd_path)
        domain = parsed_probe["metadata"]["domain"]
        req_text = " ".join(
            r["text"] for s in parsed_probe["sections"] for r in s.get("requirements", [])
        )
        probes = {
            "plan_generator": f"engineering plan phases risks milestones for: {domain}. {req_text}",
            "solution_architect": f"architecture pattern trade-offs for: {domain}. {req_text}",
        }
        for agent_id, text in probes.items():
            scope = query_mod.AGENT_SCOPES[agent_id]
            kept, dropped = query_mod.query(collection, text, scope["source_types"], scope["top_k"])
            print(f"  [{agent_id}] {len(kept)} hit(s) above threshold, {dropped} dropped")
            if not kept:
                print("    WARNING: no hits -- the orchestrator run below will likely see the same starvation.")
    else:
        section("3/5  RAG retrieval smoke test (skipped: --no-smoke-test)")

    section("4/5  Orchestrator: agents + Critic + guardrails + revision loop")
    state, result = orchestrator.run_pipeline(brd_path=str(brd_path), persist_dir=persist_dir)
    print(f"  pipeline_status: {state['pipeline_status']}")
    print(f"  run_id: {state['run_id']}")
    for entry in state["agent_states"]:
        print(f"    {entry['agent_id']}: status={entry['status']} attempts={entry['attempt_count']} revisions={entry['revision_count']}")
    if state["guardrail_events"]:
        print(f"  guardrail events ({len(state['guardrail_events'])}):")
        for ev in state["guardrail_events"]:
            print(f"    [{ev['type']}] {ev['agent_id']}: {ev['detail']} -> {ev['action_taken']}")

    schema = __import__("json").loads((REPO_ROOT / "schemas" / "orchestrator_state.schema.json").read_text())
    jsonschema.Draft7Validator(schema).validate(state)
    print("  [schema validation] PASSED against schemas/orchestrator_state.schema.json")

    section("5/5  Evaluation summary (Critic badges)")
    all_green = True
    for agent_id, c_review in result.get("critic_reviews", {}).items():
        badge = c_review["badge"]
        all_green = all_green and badge == "green"
        print(f"  {agent_id}: {badge.upper()} (overall {c_review['overall_score']}, revisions used {c_review['revision_count']})")
    for check in result.get("cross_agent_checks", []):
        print(f"  [{'PASS' if check['passed'] else 'FAIL'}] {check['check']}")

    section("RESULT")
    ok_overall = all_green and state["pipeline_status"] == "complete"
    print(f"  {'ALL GREEN' if ok_overall else 'NEEDS ATTENTION'} -- pipeline_status={state['pipeline_status']}")
    return state, result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brd", default=str(DEFAULT_BRD), help="BRD file to validate (generation still runs against brd-002's fixtures -- see module docstring)")
    parser.add_argument("--persist-dir", default="./chroma_db")
    parser.add_argument("--skip-ingest", action="store_true", help="reuse the existing Chroma collection instead of re-ingesting")
    parser.add_argument("--no-smoke-test", dest="smoke_test", action="store_false", help="skip the retrieval smoke test step")
    args = parser.parse_args()
    run_all(brd_path=args.brd, persist_dir=args.persist_dir, skip_ingest=args.skip_ingest, smoke_test=args.smoke_test)


if __name__ == "__main__":
    main()
