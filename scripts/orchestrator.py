#!/usr/bin/env python3
"""
Orchestrator: routes a parsed BRD to the 5 specialist agents (Planning +
Design groups), retrieves RAG context per agent's documented scope
(scripts/query.py), enforces guardrails at every handoff (scripts/guardrails.py),
sends outputs to the Critic (scripts/critic.py) with a capped 2-cycle revision
loop, tracks state matching schemas/orchestrator_state.schema.json, and writes
structured logs per BRD Section 9.

Generation itself is pluggable, exactly like critic.py's judge_fn: each
registry entry takes an agent_fn(parsed_brd, retrieved_chunks, revision_number,
critic_feedback) -> output dict. This file supplies:
  - a fixture-backed plan_generator_fn (rev0 -> rev1) that demonstrates a real
    Critic-driven revision improving the output
  - minimal stub generators for the other 4 agents, built from real RAG
    retrieval against the ingested Chroma KB, so the routing/RAG/guardrail/
    logging wiring is exercised end-to-end even without a live LLM call
  - a deliberately-flaky schedule_estimator variant used only to demonstrate
    the schema-failure retry-then-escalate path

Usage:
    python scripts/orchestrator.py --demo
"""
import argparse
import copy
import json
import re
import sys
import time
import uuid
from pathlib import Path

from common import build_collection
from query import query as rag_query, AGENT_SCOPES
from critic import review as critic_review, mock_judge_fn
from guardrails import run_guardrails, validate_brd_file, validate_schema, log_agent_execution, hash_content
from brd_parser import parse_brd

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"
LOGS_DIR = REPO_ROOT / "logs"
CHROMA_DIR = REPO_ROOT / "chroma_db"

MAX_RETRIES = 1  # schema-failure retries before escalating, per docs/architecture.md failure modes

SCHEMA_BY_AGENT = {
    "plan_generator": "engineering_plan",
    "schedule_estimator": "schedule_estimate",
    "solution_architect": "solution_architecture",
    "poc_planner": "poc_plan",
    "tech_stack_recommender": "tech_stack_recommendation",
}

ROUTING_RULES = {
    "functional_requirement": ["plan_generator", "schedule_estimator"],
    "non_functional_requirement": ["solution_architect", "poc_planner", "tech_stack_recommender"],
}


# --------------------------------------------------------------------------
# Agent registry -- pluggable generation functions
# --------------------------------------------------------------------------

def _generic_plan_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    """Minimal stub plan for any BRD other than brd-002, built the same way
    the other 4 stub agents are (real parsed-BRD requirement ids, real RAG
    citations, no domain-specific content) -- since the brd-002 fixture below
    hard-codes loyalty-points-specific phases/risks that would be wrong (not
    just generic) for a different BRD. Still a stand-in for a real LLM call;
    see README "Notes on What's a Live Call vs. a Stand-In"."""
    output = _base_envelope("plan_generator", parsed_brd, revision_number,
                             _all_requirement_ids(parsed_brd), _citations_from_chunks(retrieved_chunks))
    output.update({
        "status": "draft" if revision_number == 0 else "revised",
        # phase-1..4 matches schedule_estimator_fn's hardcoded phase_ids below --
        # both stubs share this fixed phase skeleton so the cross-agent
        # consistency check has something real to pass, regardless of BRD.
        "phases": [
            {"phase_id": "phase-1", "name": "Discovery & Design", "sequence": 1, "dependencies": []},
            {"phase_id": "phase-2", "name": "Core Implementation", "sequence": 2, "dependencies": ["phase-1"]},
            {"phase_id": "phase-3", "name": "Testing & Rollout", "sequence": 3, "dependencies": ["phase-2"]},
            {"phase_id": "phase-4", "name": "Load & Peak Testing", "sequence": 4, "dependencies": ["phase-3"]},
        ],
        "risks": [
            {"risk_id": "risk-1", "description": "Requirements may be underspecified in areas the BRD leaves ambiguous.",
             "likelihood": "medium", "impact": "medium", "mitigation": "Flag ambiguities per the conservative-default policy instead of guessing."},
        ],
        "milestones": [
            {"milestone_id": "m-1", "name": "Design sign-off", "phase_id": "phase-1", "target_criteria": "Architecture and plan approved by EM."},
            {"milestone_id": "m-2", "name": "Feature-complete", "phase_id": "phase-2", "target_criteria": "All FR/NFR requirements addressed."},
        ],
        "team_composition": [{"role": "engineer", "count": 2, "phase_id": "phase-2"}],
        "reflection_notes": {
            "self_identified_gaps": ["This is a minimal stub plan, not an LLM-generated one -- phase/risk detail is generic."],
            "confidence": "low",
            "revision_from_previous": "n/a (first revision)" if revision_number == 0 else "no content change -- generic stub does not incorporate Critic feedback",
        },
    })
    return output


def plan_generator_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    """Fixture-backed for brd-002 specifically: returns the deliberately-flawed
    rev0 on first call, the corrected rev1 on the revision call, to demonstrate
    a real Critic-driven revision improving the output. In production this
    would be an LLM call incorporating `critic_feedback` into its prompt; here
    the fixed fixture stands in for "the agent successfully incorporated the
    feedback," which is exactly what happened when these fixtures were
    authored against critic.py's rev0/rev1 demo. Any other BRD falls through
    to _generic_plan_fn rather than silently returning brd-002's content."""
    if parsed_brd["brd_id"] != "brd-002":
        return _generic_plan_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback)

    filename = "engineering_plan_brd-002_rev0.json" if revision_number == 0 else "engineering_plan_brd-002_rev1.json"
    output = json.loads((FIXTURES / filename).read_text())
    output["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Always reflect the orchestrator's true revision counter, not whatever
    # value happens to be baked into the fixture file -- otherwise the
    # Critic's revision-cap enforcement (critic.py::enforce_revision) can
    # never see the count advance, and the revision loop never terminates.
    output["revision_number"] = revision_number
    output["status"] = "draft" if revision_number == 0 else "revised"
    return output


def _citations_from_chunks(chunks, limit=3):
    """chunks is the flattened {chunk_id, source_id, source_type, text,
    similarity} shape built in run_agent_with_critic_loop, not the raw
    rag_query() hit (which nests these under "metadata")."""
    return [
        {
            "source_id": c["source_id"],
            "source_type": c["source_type"],
            "chunk_id": c["chunk_id"],
            "excerpt": c["text"][:300],
            "similarity_score": round(c["similarity"], 3),
        }
        for c in chunks[:limit]
    ]


def _base_envelope(agent_id, parsed_brd, revision_number, requirement_ids, citations):
    return {
        "agent_id": agent_id,
        "brd_id": parsed_brd["brd_id"],
        "run_id": "run-001",
        "revision_number": revision_number,
        "status": "draft",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "citations": citations,
        "assumptions": [],
        "ambiguities_flagged": [],
        "requirement_ids_addressed": requirement_ids,
    }


def _all_requirement_ids(parsed_brd):
    return [r["requirement_id"] for s in parsed_brd["sections"] for r in s.get("requirements", [])]


def schedule_estimator_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    output = _base_envelope("schedule_estimator", parsed_brd, revision_number,
                             _all_requirement_ids(parsed_brd), _citations_from_chunks(retrieved_chunks))
    output.update({
        "aligned_plan_id": "run-001#rev1",
        "effort_estimates": [
            {"phase_id": "phase-1", "effort_person_days": 7, "basis": "template-002 discovery phase"},
            {"phase_id": "phase-2", "effort_person_days": 15, "basis": "template-002 core ledger phase"},
            {"phase_id": "phase-3", "effort_person_days": 10, "basis": "template-002 admin/notifications phase"},
            {"phase_id": "phase-4", "effort_person_days": 7, "basis": "template-002 load-testing phase"},
        ],
        "timeline": [
            {"phase_id": "phase-1", "start_offset_days": 0, "duration_days": 8},
            {"phase_id": "phase-2", "start_offset_days": 8, "duration_days": 15},
            {"phase_id": "phase-3", "start_offset_days": 23, "duration_days": 10},
            {"phase_id": "phase-4", "start_offset_days": 33, "duration_days": 8},
        ],
        "resource_allocation": [
            {"role": "backend engineer", "phase_id": "phase-2", "allocation_pct": 100},
        ],
        "variance_notes": "Based on project_timeline rows for medium-complexity e-commerce projects (10-11 weeks observed, 10-20% variance).",
    })
    return output


def solution_architect_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    output = _base_envelope("solution_architect", parsed_brd, revision_number,
                             _all_requirement_ids(parsed_brd), _citations_from_chunks(retrieved_chunks))
    output.update({
        "pattern_selected": "event-driven",
        "components": [
            {"component_id": "comp-ledger", "name": "Points Ledger Service", "responsibility": "Award/redeem logic, audit trail", "depends_on": []},
            {"component_id": "comp-notify", "name": "Notification Service", "responsibility": "Expiry notifications (FR-6)", "depends_on": ["comp-ledger"]},
        ],
        "data_flow": [
            {"from_component_id": "comp-ledger", "to_component_id": "comp-notify", "data_description": "Points-expiring-soon events", "protocol": "Kafka"},
        ],
        "nfr_mapping": [
            {"nfr_requirement_id": "NFR-1", "addressed_by_component_id": "comp-ledger", "explanation": "Redis-cached balance lookups keep award/redeem under the 200ms budget."},
            {"nfr_requirement_id": "NFR-4", "addressed_by_component_id": "comp-ledger", "explanation": "Ledger never stores raw payment data, keeping PCI scope unchanged."},
        ],
        "diagram_mermaid": "flowchart LR\n  comp-ledger --> comp-notify",
    })
    return output


def poc_planner_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    output = _base_envelope("poc_planner", parsed_brd, revision_number,
                             _all_requirement_ids(parsed_brd), _citations_from_chunks(retrieved_chunks))
    output.update({
        "poc_scope": "Points award + redeem for a single product category, no admin UI.",
        "out_of_scope": ["Manual grant workflow (FR-5)", "Expiry notifications (FR-6)"],
        "success_criteria": [
            {"criterion_id": "sc-1", "description": "Award/redeem latency under budget", "measurement": "p99 latency in staging load test", "target_value": "<200ms"},
        ],
        "modular_boundaries": [
            {"module_id": "mod-ledger", "maps_to_component_id": "comp-ledger", "boundary_description": "Award/redeem API + ledger schema only."},
        ],
        "estimated_duration_days": 10,
    })
    return output


def tech_stack_recommender_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    output = _base_envelope("tech_stack_recommender", parsed_brd, revision_number,
                             _all_requirement_ids(parsed_brd), _citations_from_chunks(retrieved_chunks))
    output.update({
        "options": [
            {
                "option_id": "opt-a", "stack_name": "Node.js + Postgres + Redis",
                "components": [{"layer": "backend", "technology": "Node.js"}, {"layer": "data", "technology": "Postgres"}, {"layer": "cache", "technology": "Redis"}],
                "tradeoffs": {"scalability": "Good with Redis caching for latency budget", "team_familiarity": "High -- matches dec-003 precedent", "integration_risk": "Low", "cost": "Low"},
            },
            {
                "option_id": "opt-b", "stack_name": "Java/Spring + Postgres",
                "components": [{"layer": "backend", "technology": "Java/Spring"}, {"layer": "data", "technology": "Postgres"}],
                "tradeoffs": {"scalability": "Good", "team_familiarity": "Medium -- 2-week ramp-up per dec-004", "integration_risk": "Low, matches order-management stack", "cost": "Medium"},
            },
        ],
        "recommended_option_id": "opt-a",
        "rationale": "dec-003 shows this exact stack met the 200ms checkout-adjacent latency budget for a comparable feature.",
    })
    return output


AGENT_REGISTRY = {
    "plan_generator": plan_generator_fn,
    "schedule_estimator": schedule_estimator_fn,
    "solution_architect": solution_architect_fn,
    "poc_planner": poc_planner_fn,
    "tech_stack_recommender": tech_stack_recommender_fn,
}


# --------------------------------------------------------------------------
# Retry wrapper -- BRD/architecture failure mode: "malformed JSON (retry then escalate)"
# --------------------------------------------------------------------------

def call_agent_with_retries(agent_id, agent_fn, parsed_brd, retrieved_chunks, revision_number, critic_feedback):
    from guardrails import validate_schema
    schema_name = SCHEMA_BY_AGENT[agent_id]
    attempt = 0
    last_event = None
    while attempt <= MAX_RETRIES:
        output = agent_fn(parsed_brd, retrieved_chunks, revision_number, critic_feedback)
        ok, event = validate_schema(output, schema_name)
        if ok:
            return output, attempt, None
        last_event = event
        attempt += 1
    return None, attempt, last_event


# --------------------------------------------------------------------------
# Orchestrator run loop
# --------------------------------------------------------------------------

def build_routing_table(parsed_brd):
    table = []
    for section in parsed_brd["sections"]:
        assigned = ROUTING_RULES.get(section["section_type"], [])
        if assigned:
            table.append({"section_id": section["section_id"], "assigned_agents": assigned})
    return table


# --------------------------------------------------------------------------
# Human-in-the-loop: voice/text approval at the awaiting_hitl gate. Real
# control-flow decision (does the pipeline advance or stop), not a read-only
# convenience like ASR/TTS/RAG-voice-queries -- so it gets a keyword
# classifier that's easy to audit, not an LLM call whose judgment would be
# harder to hold accountable for a wrong branch.
# --------------------------------------------------------------------------

APPROVE_KEYWORDS = ("approve", "approved", "accept", "looks good", "proceed", "go ahead", "sounds good")
REJECT_KEYWORDS = ("reject", "rejected", "revise", "send back", "redo", "needs work", "not approved", "no good")

# "Not approved" legitimately contains the substring "approve", which would
# otherwise spuriously trigger APPROVE_KEYWORDS too, collapsing an
# unambiguous rejection into "unclear". Strip negated-approval phrases
# before matching approve keywords; REJECT_KEYWORDS already covers "not
# approved" explicitly, and this pattern catches variants like "not
# approve"/"don't approve" too.
_NEGATED_APPROVAL_RE = re.compile(r"\b(not|n't|never)\s+approv\w*\b")


def classify_hitl_decision(text):
    """Keyword-based intent classifier for a transcribed/typed EM decision.
    Returns 'approve', 'reject', or 'unclear' (both/neither keyword set
    matched -- ambiguous input is not guessed at, per BRD Section 8's
    ambiguity policy)."""
    normalized = text.lower()
    approve_search_text = _NEGATED_APPROVAL_RE.sub(" ", normalized)
    approve_hit = any(kw in approve_search_text for kw in APPROVE_KEYWORDS)
    reject_hit = any(kw in normalized for kw in REJECT_KEYWORDS) or bool(_NEGATED_APPROVAL_RE.search(normalized))
    if approve_hit and not reject_hit:
        return "approve"
    if reject_hit and not approve_hit:
        return "reject"
    return "unclear"


def resolve_hitl_decision(approval_audio=None, approval_text=None):
    """Determines the EM's approve/reject decision for the awaiting_hitl
    gate. Priority: explicit audio (voice, via scripts/asr.py) > explicit
    text > interactive stdin prompt (only if attached to a real terminal,
    so this never blocks an automated run) > auto-approve default for
    non-interactive runs with no input supplied (e.g. CI/--demo with neither
    flag set) -- logged explicitly by the caller, not silently skipped."""
    if approval_audio:
        from asr import transcribe
        transcript = transcribe(approval_audio)
        return {"decision": classify_hitl_decision(transcript), "source": "voice", "transcript": transcript}
    if approval_text:
        return {"decision": classify_hitl_decision(approval_text), "source": "text", "transcript": approval_text}
    if sys.stdin.isatty():
        typed = input("EM decision -- approve or reject this run's outputs? ")
        return {"decision": classify_hitl_decision(typed), "source": "text", "transcript": typed}
    return {"decision": "approve", "source": "default", "transcript": None}


def new_state(run_id, brd_id):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "run_id": run_id, "brd_id": brd_id, "pipeline_status": "ingesting",
        "agent_states": [], "routing_table": [], "guardrail_events": [],
        "started_at": now, "updated_at": now,
    }


def set_agent_state(state, agent_id, **fields):
    for entry in state["agent_states"]:
        if entry["agent_id"] == agent_id:
            entry.update(fields)
            return entry
    entry = {"agent_id": agent_id, "status": "pending", "attempt_count": 0, "last_error": None, "revision_count": 0}
    entry.update(fields)
    state["agent_states"].append(entry)
    return entry


# Querying every source_type with the same literal requirement text starves
# out precedent-style sources (plan_template, architecture_pattern) -- BRD
# requirement text near-exactly self-matches the BRD's own retrieved chunks
# (past_brd), which always wins top_k. Each source_type gets its own
# framing instead, matching the per-agent scoping intent already documented
# in docs/rag_design.md Section 6.
SOURCE_TYPE_QUERY_FRAMING = {
    "past_brd": "{domain}: {requirements}",
    "plan_template": "engineering plan phases risks milestones team composition for: {domain}. {requirements}",
    "architecture_pattern": "architecture pattern trade-offs for: {domain}. {requirements}",
    "org_standard": "engineering standards, approved stacks, review criteria relevant to: {domain}. {requirements}",
    "project_timeline": "past project duration and team size for a comparable: {domain} project. {requirements}",
    "tech_stack_decision": "past tech stack decisions and outcomes for: {domain}. {requirements}",
}


def build_retrieval_query(parsed_brd, source_type):
    domain = parsed_brd.get("metadata", {}).get("domain", "")
    requirement_text = " ".join(
        r["text"] for s in parsed_brd["sections"] for r in s.get("requirements", [])
    )
    template = SOURCE_TYPE_QUERY_FRAMING.get(source_type, "{domain}: {requirements}")
    return template.format(domain=domain, requirements=requirement_text)


def run_agent_with_critic_loop(agent_id, parsed_brd, collection, state, run_id):
    scope = AGENT_SCOPES[agent_id]
    source_types = scope["source_types"] or list(SOURCE_TYPE_QUERY_FRAMING)  # critic: search everything
    per_type_top_k = max(3, scope["top_k"] // len(source_types))

    retrieved_chunks = []
    for source_type in source_types:
        hits, _dropped = rag_query(
            collection, build_retrieval_query(parsed_brd, source_type), [source_type], per_type_top_k
        )
        retrieved_chunks.extend(hits)

    # Convert retrieval hits into the {chunk_id, source_id, ...} shape guardrails/critic expect
    retrieved = [
        {"chunk_id": c["metadata"]["chunk_id"], "source_id": c["metadata"]["source_id"],
         "source_type": c["metadata"]["source_type"], "text": c["text"], "similarity": c["similarity"]}
        for c in retrieved_chunks
    ]

    revision_number = 0
    critic_feedback = None
    final_output, final_critic = None, None

    while True:
        set_agent_state(state, agent_id, status="running")
        t0 = time.time()
        output, attempts, schema_error = call_agent_with_retries(
            agent_id, AGENT_REGISTRY[agent_id], parsed_brd, retrieved, revision_number, critic_feedback
        )
        if output is None:
            set_agent_state(state, agent_id, status="failed", attempt_count=attempts, last_error=schema_error["detail"])
            state["guardrail_events"].append(schema_error)
            return None, None  # escalate: pipeline_status will be set to 'failed' by caller

        passed, guardrail_events = run_guardrails(output, SCHEMA_BY_AGENT[agent_id], parsed_brd=parsed_brd, retrieved_chunks=retrieved)
        state["guardrail_events"].extend(guardrail_events)

        c_review = critic_review(output, parsed_brd, retrieved, other_outputs=None, previous_feedback=critic_feedback,
                                  judge_fn=mock_judge_fn, run_id=run_id)
        elapsed_ms = int((time.time() - t0) * 1000)

        log_agent_execution(
            LOGS_DIR / f"{run_id}.jsonl", run_id=run_id, agent_id=agent_id, brd_id=parsed_brd["brd_id"],
            input_text=json.dumps(parsed_brd), rag_chunks_retrieved=retrieved, output=output,
            critic_score=c_review["overall_score"], execution_time_ms=elapsed_ms,
            guardrail_events=guardrail_events, revision_count=revision_number,
        )

        set_agent_state(state, agent_id, status="succeeded", attempt_count=attempts, revision_count=revision_number)
        final_output, final_critic = output, c_review

        if not c_review["revision_required"]:
            break
        if c_review["escalated_to_em"]:
            break
        critic_feedback = "; ".join(f"[{d['dimension']}] {d['specific_feedback']}" for d in c_review["dimension_failures"])
        revision_number += 1

    return final_output, final_critic


DEFAULT_BRD_FILE = REPO_ROOT / "kb" / "past_brds" / "brd-002-medium.md"


def run_pipeline(brd_path=None, persist_dir=None, approval_audio=None, approval_text=None):
    brd_file = Path(brd_path) if brd_path else DEFAULT_BRD_FILE
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    # brd_id is a placeholder until Layer 1 parsing below resolves the real
    # one from the file's own frontmatter -- new_state needs something to
    # write immediately so guardrail events raised before parsing (e.g. a
    # rejected file) still land in a valid orchestrator_state.
    state = new_state(run_id, brd_file.stem)

    # 1. Input validation gate (guardrail #1) before anything else runs
    ok, event = validate_brd_file(brd_file)
    if event:
        state["guardrail_events"].append(event)
    if not ok:
        state["pipeline_status"] = "failed"
        return state, {}

    # 2. Layer 1: real parsing (scripts/brd_parser.py), not a static fixture --
    # works for any BRD following kb/past_brds/'s frontmatter + '## Section' +
    # 'FR-N:'/'NFR-N:' bullet structure. See brd_parser.py's module docstring
    # for the documented parsing limitations (md/txt only, no priority inference).
    parsed_brd = parse_brd(brd_file)
    state["brd_id"] = parsed_brd["brd_id"]
    schema_ok, schema_event = validate_schema(parsed_brd, "parsed_brd")
    if schema_event:
        state["guardrail_events"].append(schema_event)
    if not schema_ok:
        state["pipeline_status"] = "failed"
        return state, {}

    state["routing_table"] = build_routing_table(parsed_brd)
    state["pipeline_status"] = "routing"

    collection = build_collection(str(persist_dir or CHROMA_DIR))

    outputs, critic_reviews = {}, {}

    state["pipeline_status"] = "planning"
    for agent_id in ["plan_generator", "schedule_estimator"]:
        output, c_review = run_agent_with_critic_loop(agent_id, parsed_brd, collection, state, run_id)
        if output is None:
            state["pipeline_status"] = "failed"
            return state, outputs
        outputs[agent_id], critic_reviews[agent_id] = output, c_review

    state["pipeline_status"] = "designing"
    for agent_id in ["solution_architect", "poc_planner", "tech_stack_recommender"]:
        output, c_review = run_agent_with_critic_loop(agent_id, parsed_brd, collection, state, run_id)
        if output is None:
            state["pipeline_status"] = "failed"
            return state, outputs
        outputs[agent_id], critic_reviews[agent_id] = output, c_review

    # Final cross-agent consistency pass now that every agent has a final output
    state["pipeline_status"] = "critic_review"
    from critic import cross_agent_consistency_checks
    plan_vs_schedule = cross_agent_consistency_checks(outputs["plan_generator"], {"schedule_estimator": outputs["schedule_estimator"]})
    poc_vs_arch = cross_agent_consistency_checks(outputs["poc_planner"], {"solution_architect": outputs["solution_architect"]})
    for check in plan_vs_schedule + poc_vs_arch:
        if not check["passed"]:
            state["guardrail_events"].append({
                "type": "cross_agent_consistency", "agent_id": "critic", "detail": check["detail"], "action_taken": "flagged"
            })

    state["pipeline_status"] = "evaluating"
    state["pipeline_status"] = "awaiting_hitl"

    # Human-in-the-loop gate: a real decision, not a pass-through. Voice
    # (--approval-audio) and typed text (--approval-text) both flow through
    # the same classify_hitl_decision() logic; see resolve_hitl_decision's
    # docstring for the interactive-terminal and non-interactive-default
    # fallback behavior.
    hitl = resolve_hitl_decision(approval_audio=approval_audio, approval_text=approval_text)
    detail = f"EM decision: {hitl['decision']} (source={hitl['source']}"
    if hitl["transcript"]:
        detail += f", heard: {hitl['transcript']!r}"
    detail += ")"
    # action_taken records what happened as a result, not the raw decision
    # label -- 'unclear' maps to 'escalated' since that's the actual outcome.
    action_taken = {"approve": "approved", "reject": "rejected", "unclear": "escalated"}[hitl["decision"]]
    state["guardrail_events"].append({
        "type": "hitl_decision", "agent_id": "orchestrator", "detail": detail, "action_taken": action_taken,
    })

    if hitl["decision"] == "approve":
        state["pipeline_status"] = "complete"
    else:
        # 'reject' or 'unclear': no further automated revision path exists
        # here -- plan_generator's fixture-backed demo only has a rev0 and a
        # rev1 (see plan_generator_fn), there's no rev2 to fall back to, and
        # guessing at an ambiguous decision would violate the same
        # conservative-default policy the rest of this system follows.
        # Honest terminal state, not a fake extra loop.
        state["pipeline_status"] = "failed"
        state["guardrail_events"].append({
            "type": "hitl_decision", "agent_id": "orchestrator",
            "detail": "EM did not approve (or decision was unclear) and no further automated "
                      "revision is available for this demo pipeline; escalating.",
            "action_taken": "escalated",
        })

    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return state, {"outputs": outputs, "critic_reviews": critic_reviews,
                    "cross_agent_checks": plan_vs_schedule + poc_vs_arch}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--brd", help="BRD file to parse and run (default: kb/past_brds/brd-002-medium.md)")
    parser.add_argument("--persist-dir", default=None)
    parser.add_argument("--approval-audio", help="audio file with the EM's spoken approve/reject decision (requires OPENAI_API_KEY)")
    parser.add_argument("--approval-text", help="typed approve/reject decision, fallback for --approval-audio")
    args = parser.parse_args()
    if not args.demo:
        parser.error("only --demo is supported currently")

    state, result = run_pipeline(
        brd_path=args.brd, persist_dir=args.persist_dir,
        approval_audio=args.approval_audio, approval_text=args.approval_text,
    )

    print(f"pipeline_status: {state['pipeline_status']}")
    print(f"run_id: {state['run_id']}\n")

    print("Agent states:")
    for entry in state["agent_states"]:
        print(f"  {entry['agent_id']}: status={entry['status']} attempts={entry['attempt_count']} revisions={entry['revision_count']}")

    print(f"\nGuardrail events ({len(state['guardrail_events'])}):")
    for event in state["guardrail_events"]:
        print(f"  [{event['type']}] {event['agent_id']}: {event['detail']} -> {event['action_taken']}")

    if result.get("critic_reviews"):
        print("\nCritic badges:")
        for agent_id, c_review in result["critic_reviews"].items():
            print(f"  {agent_id}: {c_review['badge']} (overall {c_review['overall_score']}, revisions used {c_review['revision_count']})")

    if result.get("cross_agent_checks"):
        print("\nFinal cross-agent consistency checks:")
        for check in result["cross_agent_checks"]:
            print(f"  [{'PASS' if check['passed'] else 'FAIL'}] {check['check']}")

    # Validate final state against schemas/orchestrator_state.schema.json
    import jsonschema
    schema = json.loads((REPO_ROOT / "schemas" / "orchestrator_state.schema.json").read_text())
    jsonschema.Draft7Validator(schema).validate(state)
    print("\n[schema validation] PASSED against schemas/orchestrator_state.schema.json")


if __name__ == "__main__":
    main()
