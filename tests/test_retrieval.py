"""
Regression tests for the RAG retrieval layer (scripts/query.py +
scripts/orchestrator.py's query-framing), covering the behaviors that were
previously only verified manually during development (see
docs/rag_design.md Section 6 and docs/evaluation_report.md Sections 5/8):

  - the empirically-calibrated similarity threshold is actually enforced
  - a genuinely irrelevant query hits the "no RAG hits" guardrail path
  - each agent's retrieval stays inside its documented source_type scope
  - the per-source-type query framing that fixed a real retrieval-starvation
    bug (plan_template chunks getting crowded out by near-duplicate past_brd
    chunks) keeps working, for every BRD in the KB -- not just brd-002

Runs against a real Chroma collection (see conftest.py), not a mock.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from query import query, build_where, AGENT_SCOPES, SIMILARITY_THRESHOLD  # noqa: E402
from orchestrator import build_retrieval_query  # noqa: E402
from brd_parser import parse_brd  # noqa: E402

KB_PAST_BRDS = REPO_ROOT / "kb" / "past_brds"
VALID_SOURCE_TYPES = {
    "past_brd", "plan_template", "architecture_pattern",
    "org_standard", "project_timeline", "tech_stack_decision",
}

RELEVANT_QUERY = "engineering plan phases risks milestones for a loyalty points engine"
IRRELEVANT_QUERY = "unrelated query about cooking recipes"


# ---------------------------------------------------------------------------
# Pure logic -- no DB / embeddings required, these run in milliseconds
# ---------------------------------------------------------------------------

def test_build_where_with_no_filters_returns_none():
    assert build_where() is None


def test_build_where_single_filter_is_unwrapped():
    assert build_where(source_types=["past_brd"]) == {"source_type": {"$in": ["past_brd"]}}


def test_build_where_combines_multiple_filters_with_and():
    where = build_where(source_types=["past_brd"], domain="fintech")
    assert where == {
        "$and": [
            {"source_type": {"$in": ["past_brd"]}},
            {"domain": "fintech"},
        ]
    }


def test_every_agent_scope_uses_valid_source_types_and_positive_top_k():
    for agent_id, scope in AGENT_SCOPES.items():
        if scope["source_types"] is None:
            continue  # critic is intentionally unscoped (searches everything)
        assert set(scope["source_types"]) <= VALID_SOURCE_TYPES, (
            f"{agent_id} scopes to an unknown source_type: {scope['source_types']}"
        )
        assert scope["top_k"] > 0, f"{agent_id} has a non-positive top_k"


# ---------------------------------------------------------------------------
# Real retrieval against a live Chroma collection built from kb/
# ---------------------------------------------------------------------------

def test_relevant_query_only_keeps_hits_at_or_above_threshold(kb_collection):
    scope = AGENT_SCOPES["plan_generator"]
    kept, _dropped = query(kb_collection, RELEVANT_QUERY, scope["source_types"], scope["top_k"])
    assert len(kept) > 0
    for hit in kept:
        assert hit["similarity"] >= SIMILARITY_THRESHOLD


def test_irrelevant_query_returns_no_hits_above_threshold(kb_collection):
    scope = AGENT_SCOPES["solution_architect"]
    kept, dropped = query(kb_collection, IRRELEVANT_QUERY, scope["source_types"], scope["top_k"])
    assert kept == []
    assert dropped >= 0


def test_results_never_leave_the_agents_source_type_scope(kb_collection):
    scope = AGENT_SCOPES["solution_architect"]  # architecture_pattern, org_standard
    kept, _dropped = query(
        kb_collection, "architecture pattern trade-offs for e-commerce checkout", scope["source_types"], scope["top_k"]
    )
    assert len(kept) > 0
    for hit in kept:
        assert hit["metadata"]["source_type"] in scope["source_types"]


def test_kept_plus_dropped_equals_raw_result_count(kb_collection):
    scope = AGENT_SCOPES["plan_generator"]
    kept, dropped = query(kb_collection, RELEVANT_QUERY, scope["source_types"], scope["top_k"])
    where = build_where(scope["source_types"])
    raw = kb_collection.query(query_texts=[RELEVANT_QUERY], n_results=scope["top_k"], where=where)
    assert len(kept) + dropped == len(raw["documents"][0])


def test_per_source_type_query_framing_surfaces_plan_template(kb_collection):
    """Regression test for a real bug: querying multiple source_types with
    raw requirement text let a BRD's own near-identical chunks (past_brd)
    dominate top-k and starve out plan_template precedent entirely. The fix
    (orchestrator.SOURCE_TYPE_QUERY_FRAMING) must keep surfacing
    plan_template hits when queried on its own, framed source_type."""
    parsed = parse_brd(KB_PAST_BRDS / "brd-002-medium.md")
    text = build_retrieval_query(parsed, "plan_template")
    kept, _dropped = query(kb_collection, text, ["plan_template"], 5)
    assert len(kept) > 0


@pytest.mark.parametrize(
    "brd_file", ["brd-001-simple.md", "brd-002-medium.md", "brd-003-complex.md"]
)
def test_every_kb_brd_retrieves_relevant_plan_template_chunks(kb_collection, brd_file):
    """Cross-BRD retrieval check: the plan_generator query framing must work
    for every BRD in the KB, not just the one used for the fixture-backed
    demo -- this is what was previously only checked by hand via
    run_all.py --brd <file>."""
    parsed = parse_brd(KB_PAST_BRDS / brd_file)
    text = build_retrieval_query(parsed, "plan_template")
    kept, _dropped = query(kb_collection, text, ["plan_template"], 5)
    assert len(kept) > 0, f"{brd_file}: no plan_template hits -- possible retrieval regression"
