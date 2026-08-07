#!/usr/bin/env python3
"""
Query the Chroma knowledge base using the retrieval parameters and per-agent
source_type scoping documented in docs/rag_design.md (Section 6).

Usage:
    python scripts/query.py "real-time fraud scoring pipeline" --agent solution_architect
    python scripts/query.py "loyalty points redemption timeline" --agent schedule_estimator
    python scripts/query.py "free text query" --source-types architecture_pattern tech_stack_decision --top-k 8
"""
import argparse

from common import build_collection

# Empirically calibrated against this KB with text-embedding-3-small (see
# docs/rag_design.md Section 6 "Retrieval Parameters" for the measurements):
# genuinely relevant hits scored 0.34-0.575 cosine similarity, an irrelevant
# control query scored 0.12-0.22. 0.72 was an earlier unvalidated assumption
# that silently dropped every real hit -- always re-measure when the
# embedding model or corpus changes materially.
SIMILARITY_THRESHOLD = 0.30

# Mirrors the per-agent retrieval-scoping table in docs/rag_design.md Section 6
AGENT_SCOPES = {
    "plan_generator": {"source_types": ["plan_template", "past_brd"], "top_k": 5},
    "schedule_estimator": {"source_types": ["project_timeline", "plan_template"], "top_k": 5},
    "solution_architect": {"source_types": ["architecture_pattern", "org_standard"], "top_k": 8},
    "poc_planner": {"source_types": ["past_brd", "architecture_pattern"], "top_k": 5},
    "tech_stack_recommender": {"source_types": ["tech_stack_decision", "org_standard"], "top_k": 8},
    "critic": {"source_types": None, "top_k": 5},
}


def build_where(source_types=None, domain=None, complexity=None):
    conditions = []
    if source_types:
        conditions.append({"source_type": {"$in": source_types}})
    if domain:
        conditions.append({"domain": domain})
    if complexity:
        conditions.append({"complexity": complexity})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def query(collection, text, source_types=None, top_k=5, domain=None, complexity=None):
    where = build_where(source_types, domain, complexity)
    results = collection.query(query_texts=[text], n_results=top_k, where=where)

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"similarity": 1 - dist, "metadata": meta, "text": doc})

    kept = [h for h in hits if h["similarity"] >= SIMILARITY_THRESHOLD]
    dropped = len(hits) - len(kept)
    return kept, dropped


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query_text")
    parser.add_argument("--agent", choices=sorted(AGENT_SCOPES), help="apply this agent's documented retrieval scope")
    parser.add_argument("--source-types", nargs="*", help="override source_type filter")
    parser.add_argument("--top-k", type=int, help="override top_k")
    parser.add_argument("--domain")
    parser.add_argument("--complexity")
    parser.add_argument("--persist-dir", default="./chroma_db")
    args = parser.parse_args()

    source_types = args.source_types
    top_k = args.top_k
    if args.agent:
        scope = AGENT_SCOPES[args.agent]
        source_types = source_types or scope["source_types"]
        top_k = top_k or scope["top_k"]
    top_k = top_k or 5

    collection = build_collection(args.persist_dir)
    kept, dropped = query(collection, args.query_text, source_types, top_k, args.domain, args.complexity)

    if not kept:
        print(
            f"No chunks above similarity threshold ({SIMILARITY_THRESHOLD}) -- "
            "this is the 'no RAG hits' guardrail path: the calling agent should "
            "proceed with a disclaimer and an Amber badge (see docs/rag_design.md "
            "Section 6 / BRD Section 9)."
        )
        return

    for h in kept:
        m = h["metadata"]
        label = m.get("section") or m.get("title") or m["source_id"]
        print(f"[{h['similarity']:.3f}] {m['source_type']} :: {m['source_id']} :: {label}")
        print(f"  {h['text'][:200]}")
        print()

    if dropped:
        print(f"({dropped} additional result(s) below similarity threshold, dropped)")


if __name__ == "__main__":
    main()
