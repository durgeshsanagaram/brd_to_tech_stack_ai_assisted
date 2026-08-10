#!/usr/bin/env python3
"""
Critic Agent: rubric scoring, revision-loop enforcement, and cross-agent
consistency checks. Implements the four dimensions and thresholds from BRD
Section 7B, using the prompt in prompts/critic_rubric.md for the two
fundamentally subjective dimensions and rule-based code for everything a
script can check exactly.

Division of labor (see prompts/critic_rubric.md for the rationale):
  - groundedness:  rule-based citation-validity check (hallucination guard)
                   + LLM-judged claim-support score
  - completeness:  fully rule-based -- exact requirement_id coverage against
                   the parsed BRD (see requirement_ids_addressed in
                   schemas/common.schema.json)
  - consistency:   rule-based cross-agent reference checks (phase_id /
                   component_id linkage) + LLM-identified contradictions
  - actionability: fully LLM-judged

Usage (demo, no API key needed -- uses a mock judge):
    python scripts/critic.py --demo

Usage (real judge, requires OPENAI_API_KEY):
    python scripts/critic.py --review fixtures/engineering_plan_brd-002_rev0.json \\
        --brd fixtures/parsed_brd_brd-002.json \\
        --retrieved fixtures/retrieved_chunks_run-001_plan_generator.json \\
        --use-openai
"""
import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PROMPT_PATH = REPO_ROOT / "prompts" / "critic_rubric.md"
SCHEMA_PATH = REPO_ROOT / "schemas" / "critic_review.schema.json"

# Dimension pass thresholds, mirroring BRD Section 7B
GROUNDEDNESS_PASS_SCORE = 3.75   # 5 * 0.75 (>=75% claims cited)
COMPLETENESS_PASS_RATIO = 1.0    # 100% section/requirement coverage
CONSISTENCY_PASS_CONTRADICTIONS = 0
ACTIONABILITY_PASS_SCORE = 4.0

CONTRADICTION_PENALTY = 1.5      # per contradiction, off a base of 5.0
REVISION_CAP = 2                 # BRD: "Cap revisions at two cycles"


# --------------------------------------------------------------------------
# Prompt assembly -- prompts/critic_rubric.md is the single source of truth;
# this just extracts the fenced code blocks rather than duplicating them.
# --------------------------------------------------------------------------

def _extract_fenced_block(markdown_text: str, heading: str) -> str:
    pattern = re.escape(heading) + r"\s*\n\s*```\s*\n(.*?)\n```"
    match = re.search(pattern, markdown_text, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find fenced block under heading {heading!r}")
    return match.group(1).strip()


def load_rubric_templates():
    text = RUBRIC_PROMPT_PATH.read_text()
    system_prompt = _extract_fenced_block(text, "## System Prompt")
    user_template = _extract_fenced_block(text, "## User Prompt Template")
    return system_prompt, user_template


def _format_chunks(chunks):
    if not chunks:
        return "(none retrieved)"
    return "\n".join(
        f"[{c['source_type']} :: {c['source_id']} :: {c.get('section', '')}] "
        f"(similarity {c.get('similarity', 0):.2f})"
        for c in chunks
    )


def build_judge_prompt(target_output, parsed_brd, retrieved_chunks, other_outputs=None, previous_feedback=None):
    system_prompt, user_template = load_rubric_templates()

    brd_sections_text = "\n\n".join(
        f"### {s['title']}\n" + "\n".join(f"- {r['requirement_id']}: {r['text']}" for r in s.get("requirements", []))
        for s in parsed_brd["sections"]
    )

    other_outputs_text = "(none available yet)"
    if other_outputs:
        other_outputs_text = "\n\n".join(
            f"### {agent_id}\n```json\n{json.dumps(output, indent=2)}\n```"
            for agent_id, output in other_outputs.items()
        )

    previous_feedback_text = previous_feedback or "(first pass, no prior revision)"

    user_prompt = (
        user_template
        .replace("{{brd_id}}", parsed_brd["brd_id"])
        .replace("{{brd_sections_text}}", brd_sections_text)
        .replace("{{retrieved_chunks_formatted}}", _format_chunks(retrieved_chunks))
        .replace("{{target_agent_id}}", target_output["agent_id"])
        .replace("{{revision_number}}", str(target_output["revision_number"]))
        .replace("{{target_output_json}}", f"```json\n{json.dumps(target_output, indent=2)}\n```")
        .replace("{{other_agent_outputs_formatted}}", other_outputs_text)
        .replace("{{previous_feedback_text}}", previous_feedback_text)
    )
    return system_prompt, user_prompt


# --------------------------------------------------------------------------
# Rule-based checks
# --------------------------------------------------------------------------

def rule_based_groundedness(target_output, retrieved_chunk_ids):
    """Citation-validity / hallucination check: every chunk_id the agent
    cites must actually have been retrieved for this run. This does not
    measure whether prose claims are grounded (that's the LLM judge's job)
    -- it catches the harder guardrail failure of citing a chunk that was
    never retrieved at all.
    """
    citations = target_output.get("citations", [])
    invalid = [c for c in citations if c["chunk_id"] not in retrieved_chunk_ids]

    retrieved_but_uncited = bool(retrieved_chunk_ids) and not citations
    return {
        "citations_provided": len(citations),
        "invalid_citations": invalid,
        "has_hallucinated_citation": len(invalid) > 0,
        "retrieved_but_uncited": retrieved_but_uncited,
    }


def rule_based_completeness(target_output, parsed_brd):
    all_requirement_ids = {
        r["requirement_id"] for s in parsed_brd["sections"] for r in s.get("requirements", [])
    }
    addressed = set(target_output.get("requirement_ids_addressed", []))
    addressed = addressed & all_requirement_ids  # ignore stray/typo'd ids
    missing = sorted(all_requirement_ids - addressed)
    coverage_ratio = len(addressed) / len(all_requirement_ids) if all_requirement_ids else 1.0
    return {"coverage_ratio": coverage_ratio, "missing_requirement_ids": missing}


def cross_agent_consistency_checks(target_output, other_outputs):
    """Structural cross-reference checks -- exact, not semantic. Semantic
    contradictions (timeline vs. architecture complexity, etc.) are the LLM
    judge's job; see prompts/critic_rubric.md.
    """
    checks = []
    schedule = other_outputs.get("schedule_estimator")
    if target_output["agent_id"] == "plan_generator" and schedule:
        plan_phase_ids = {p["phase_id"] for p in target_output.get("phases", [])}
        schedule_phase_ids = {e["phase_id"] for e in schedule.get("effort_estimates", [])}
        unknown = schedule_phase_ids - plan_phase_ids
        checks.append({
            "check": "schedule effort_estimates reference valid plan phase_ids",
            "passed": len(unknown) == 0,
            "detail": f"Unknown phase_id(s) in schedule: {sorted(unknown)}" if unknown else "All phase_id references valid.",
        })

    architecture = other_outputs.get("solution_architect")
    if target_output["agent_id"] == "poc_planner" and architecture:
        component_ids = {c["component_id"] for c in architecture.get("components", [])}
        poc_refs = {
            m["maps_to_component_id"]
            for m in target_output.get("modular_boundaries", [])
            if m.get("maps_to_component_id")
        }
        unknown = poc_refs - component_ids
        checks.append({
            "check": "PoC modular_boundaries reference valid architecture component_ids",
            "passed": len(unknown) == 0,
            "detail": f"Unknown component_id(s) in PoC plan: {sorted(unknown)}" if unknown else "All component_id references valid.",
        })

    return checks


# --------------------------------------------------------------------------
# Judge functions (pluggable) -- swap in a real LLM call via --use-openai,
# or pass any callable matching judge_fn(system_prompt, user_prompt) -> dict
# --------------------------------------------------------------------------

def mock_judge_fn(system_prompt, user_prompt):
    """Deterministic stand-in judge for offline testing of the scoring
    pipeline's plumbing, calibrated to reproduce the worked example in
    prompts/critic_rubric.md when run against the rev0 fixture."""
    fabricated_present = "typically takes 3 weeks" in user_prompt
    return {
        "groundedness_score": 2.0 if fabricated_present else 4.5,
        "actionability_score": 4.0,
        "ungrounded_claims": [],
        "hallucinated_claims": (
            [{"claim": "Based on similar past e-commerce loyalty projects, this typically takes 3 weeks",
              "reason": "No matching project_timeline row exists for a loyalty-specific project; figure is unsupported."}]
            if fabricated_present else []
        ),
        "contradictions": [],
        "actionability_feedback": [
            "Add expiry-notification (FR-6) and peak-load testing as explicit phases before this plan is considered complete."
        ],
    }


def make_openai_judge_fn(model="gpt-4o"):
    from openai import OpenAI
    client = OpenAI()

    def judge_fn(system_prompt, user_prompt):
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return json.loads(response.choices[0].message.content)

    return judge_fn


# --------------------------------------------------------------------------
# Scoring, badge, and revision-loop logic
# --------------------------------------------------------------------------

def score_dimensions(groundedness_rule, completeness_rule, judge_output, structural_checks):
    groundedness_score = judge_output["groundedness_score"]
    if groundedness_rule["has_hallucinated_citation"]:
        groundedness_score = min(groundedness_score, 1.0)  # hard cap: cited a chunk that was never retrieved

    completeness_score = round(5 * completeness_rule["coverage_ratio"], 2)

    contradiction_count = len(judge_output.get("contradictions", [])) + sum(
        1 for c in structural_checks if not c["passed"]
    )
    consistency_score = max(0.0, 5.0 - CONTRADICTION_PENALTY * contradiction_count)

    actionability_score = judge_output["actionability_score"]

    scores = {
        "groundedness": round(groundedness_score, 2),
        "completeness": completeness_score,
        "consistency": round(consistency_score, 2),
        "actionability": round(actionability_score, 2),
    }

    dimension_pass = {
        "groundedness": scores["groundedness"] >= GROUNDEDNESS_PASS_SCORE,
        "completeness": completeness_rule["coverage_ratio"] >= COMPLETENESS_PASS_RATIO,
        "consistency": contradiction_count <= CONSISTENCY_PASS_CONTRADICTIONS,
        "actionability": scores["actionability"] >= ACTIONABILITY_PASS_SCORE,
    }
    return scores, dimension_pass, contradiction_count


def compute_badge(scores, dimension_pass):
    overall = round(sum(scores.values()) / len(scores), 2)
    dims_below = sum(1 for passed in dimension_pass.values() if not passed)

    if dims_below >= 2 or overall < 3.0:
        badge = "red"
    elif dims_below == 1 or 3.0 <= overall <= 3.9:
        badge = "amber"
    else:
        badge = "green"
    return overall, badge, dims_below


def enforce_revision(revision_count, dims_below):
    """BRD Section 4: 'Cap revisions at two cycles; beyond that, flag to the
    EM with an Amber/Red badge.'"""
    needs_revision = dims_below > 0
    if not needs_revision:
        return False, revision_count, False
    if revision_count >= REVISION_CAP:
        return False, revision_count, True  # escalate, stop looping
    return True, revision_count, False


def build_dimension_failures(dimension_pass, groundedness_rule, completeness_rule, judge_output, structural_checks):
    failures = []
    if not dimension_pass["groundedness"]:
        reason = "Citation references a chunk that was never retrieved (fabricated citation)." \
            if groundedness_rule["has_hallucinated_citation"] else \
            "One or more non-trivial claims lack supporting citations."
        feedback = "Cite a specific retrieved chunk for every non-trivial claim, or explicitly label it as an assumption." \
            if not groundedness_rule["has_hallucinated_citation"] else \
            "Remove or correct the citation pointing to an unretrieved chunk; do not cite chunks the retrieval step did not return."
        for hc in judge_output.get("hallucinated_claims", []):
            reason += f" Fabricated claim: \"{hc['claim']}\" -- {hc['reason']}"
        failures.append({"dimension": "groundedness", "reason": reason, "specific_feedback": feedback})

    if not dimension_pass["completeness"]:
        missing = completeness_rule["missing_requirement_ids"]
        failures.append({
            "dimension": "completeness",
            "reason": f"{len(missing)} BRD requirement(s) not addressed: {', '.join(missing)}.",
            "specific_feedback": f"Add explicit coverage for: {', '.join(missing)}, and list them in requirement_ids_addressed.",
        })

    if not dimension_pass["consistency"]:
        details = [c["detail"] for c in structural_checks if not c["passed"]]
        details += [f"{c['this_output_statement']} vs {c['other_output_statement']} ({c['other_agent_id']}): {c['explanation']}"
                    for c in judge_output.get("contradictions", [])]
        failures.append({
            "dimension": "consistency",
            "reason": "; ".join(details) or "Cross-agent contradiction detected.",
            "specific_feedback": "Resolve the flagged contradiction(s) with the referenced agent's output before resubmitting.",
        })

    if not dimension_pass["actionability"]:
        feedback = "; ".join(judge_output.get("actionability_feedback", [])) or "Make recommendations concrete enough to act on without follow-up questions."
        failures.append({"dimension": "actionability", "reason": "Actionability score below 4/5 threshold.", "specific_feedback": feedback})

    return failures


def review(target_output, parsed_brd, retrieved_chunks, other_outputs=None, previous_feedback=None,
           judge_fn=mock_judge_fn, run_id="run-001"):
    retrieved_chunk_ids = {c["chunk_id"] for c in retrieved_chunks}
    groundedness_rule = rule_based_groundedness(target_output, retrieved_chunk_ids)
    completeness_rule = rule_based_completeness(target_output, parsed_brd)
    structural_checks = cross_agent_consistency_checks(target_output, other_outputs or {})

    system_prompt, user_prompt = build_judge_prompt(
        target_output, parsed_brd, retrieved_chunks, other_outputs, previous_feedback
    )
    judge_output = judge_fn(system_prompt, user_prompt)

    scores, dimension_pass, contradiction_count = score_dimensions(
        groundedness_rule, completeness_rule, judge_output, structural_checks
    )
    overall_score, badge, dims_below = compute_badge(scores, dimension_pass)
    dimension_failures = build_dimension_failures(
        dimension_pass, groundedness_rule, completeness_rule, judge_output, structural_checks
    )

    incoming_revision_count = target_output["revision_number"]
    revision_required, revision_count, escalated = enforce_revision(incoming_revision_count, dims_below)

    critic_review = {
        "agent_id": "critic",
        "brd_id": target_output["brd_id"],
        "run_id": run_id,
        "revision_number": incoming_revision_count,
        "status": "final" if not revision_required else "draft",
        "created_at": "2026-08-03T10:05:00Z",
        "citations": [],
        "target_agent_id": target_output["agent_id"],
        "target_output_ref": f"{run_id}#rev{incoming_revision_count}",
        "scores": scores,
        "overall_score": overall_score,
        "badge": badge,
        "dimension_failures": dimension_failures,
        "cross_agent_consistency_checks": structural_checks,
        "revision_required": revision_required,
        "revision_count": revision_count,
        "escalated_to_em": escalated,
    }
    return critic_review


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--review", help="path to the agent output JSON to review")
    parser.add_argument("--brd", help="path to the parsed BRD JSON")
    parser.add_argument("--retrieved", help="path to the retrieved-chunks JSON for this run")
    parser.add_argument("--other-outputs", nargs="*", default=[], help="paths to other agents' output JSON for this run")
    parser.add_argument("--use-openai", action="store_true", help="use a real OpenAI judge instead of the mock")
    parser.add_argument("--demo", action="store_true", help="run against the bundled fixtures/ example")
    args = parser.parse_args()

    if args.demo:
        args.review = str(REPO_ROOT / "fixtures" / "engineering_plan_brd-002_rev0.json")
        args.brd = str(REPO_ROOT / "fixtures" / "parsed_brd_brd-002.json")
        args.retrieved = str(REPO_ROOT / "fixtures" / "retrieved_chunks_run-001_plan_generator.json")

    if not (args.review and args.brd and args.retrieved):
        parser.error("provide --review/--brd/--retrieved, or use --demo")

    target_output = json.loads(Path(args.review).read_text())
    parsed_brd = json.loads(Path(args.brd).read_text())
    retrieved_chunks = json.loads(Path(args.retrieved).read_text())
    other_outputs = {}
    for path in args.other_outputs:
        data = json.loads(Path(path).read_text())
        other_outputs[data["agent_id"]] = data

    judge_fn = make_openai_judge_fn() if args.use_openai else mock_judge_fn

    result = review(target_output, parsed_brd, retrieved_chunks, other_outputs, judge_fn=judge_fn)
    print(json.dumps(result, indent=2))

    try:
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text())
        common_schema = json.loads((REPO_ROOT / "schemas" / "common.schema.json").read_text())
        resolver = jsonschema.RefResolver(
            base_uri=f"file://{REPO_ROOT}/schemas/",
            referrer=schema,
            store={"common.schema.json": common_schema},
        )
        jsonschema.Draft7Validator(schema, resolver=resolver).validate(result)
        print("\n[schema validation] PASSED against schemas/critic_review.schema.json")
    except ImportError:
        print("\n[schema validation] skipped -- jsonschema not installed")


if __name__ == "__main__":
    main()
