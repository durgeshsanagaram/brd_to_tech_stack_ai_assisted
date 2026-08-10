"""
Regression tests for scripts/critic.py: the rule-based checks (groundedness/
completeness/consistency), badge computation, revision-cap enforcement, and
the end-to-end review() pipeline against the mock judge. Codifies the exact
before/after numbers documented in docs/evaluation_report.md Section 4
(rev0 Red 3.38 -> rev1 Green 4.62) as regression assertions rather than
one-off manual checks.
"""
import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from critic import (  # noqa: E402
    REVISION_CAP,
    compute_badge,
    cross_agent_consistency_checks,
    enforce_revision,
    load_rubric_templates,
    mock_judge_fn,
    review,
    rule_based_completeness,
    rule_based_groundedness,
    score_dimensions,
)
from guardrails import validate_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Rule-based groundedness (citation validity)
# ---------------------------------------------------------------------------

def test_rule_based_groundedness_no_citations_is_not_hallucinated(engineering_plan_rev0, retrieved_chunks):
    retrieved_ids = {c["chunk_id"] for c in retrieved_chunks}
    result = rule_based_groundedness(engineering_plan_rev0, retrieved_ids)
    assert result["citations_provided"] == 0
    assert result["has_hallucinated_citation"] is False


def test_rule_based_groundedness_flags_citation_to_unretrieved_chunk(engineering_plan_rev1, retrieved_chunks):
    retrieved_ids = {c["chunk_id"] for c in retrieved_chunks}
    faked = copy.deepcopy(engineering_plan_rev1)
    faked["citations"].append({"source_id": "made-up", "source_type": "past_brd", "chunk_id": "made-up#0"})
    result = rule_based_groundedness(faked, retrieved_ids)
    assert result["has_hallucinated_citation"] is True
    assert result["invalid_citations"][0]["chunk_id"] == "made-up#0"


def test_rule_based_groundedness_passes_when_all_citations_valid(engineering_plan_rev1, retrieved_chunks):
    retrieved_ids = {c["chunk_id"] for c in retrieved_chunks}
    result = rule_based_groundedness(engineering_plan_rev1, retrieved_ids)
    assert result["has_hallucinated_citation"] is False
    assert result["citations_provided"] > 0


# ---------------------------------------------------------------------------
# Rule-based completeness (exact requirement_id coverage)
# ---------------------------------------------------------------------------

def test_rule_based_completeness_full_coverage(engineering_plan_rev1, parsed_brd):
    result = rule_based_completeness(engineering_plan_rev1, parsed_brd)
    assert result["coverage_ratio"] == 1.0
    assert result["missing_requirement_ids"] == []


def test_rule_based_completeness_reports_missing_ids(engineering_plan_rev0, parsed_brd):
    result = rule_based_completeness(engineering_plan_rev0, parsed_brd)
    assert 0.0 < result["coverage_ratio"] < 1.0
    assert set(result["missing_requirement_ids"]) == {"FR-4", "FR-6", "NFR-2", "NFR-3", "NFR-4"}


def test_rule_based_completeness_ignores_stray_or_typoed_ids(engineering_plan_rev1, parsed_brd):
    typoed = copy.deepcopy(engineering_plan_rev1)
    typoed["requirement_ids_addressed"].append("FR-999-typo")
    result = rule_based_completeness(typoed, parsed_brd)
    assert result["coverage_ratio"] == 1.0  # stray id doesn't inflate coverage past 100%


# ---------------------------------------------------------------------------
# Cross-agent structural consistency checks
# ---------------------------------------------------------------------------

def test_cross_agent_consistency_passes_for_valid_phase_ids(engineering_plan_rev1):
    schedule = {"effort_estimates": [{"phase_id": p["phase_id"]} for p in engineering_plan_rev1["phases"]]}
    checks = cross_agent_consistency_checks(engineering_plan_rev1, {"schedule_estimator": schedule})
    assert len(checks) == 1
    assert checks[0]["passed"] is True


def test_cross_agent_consistency_flags_unknown_phase_id(engineering_plan_rev1):
    schedule = {"effort_estimates": [{"phase_id": "phase-does-not-exist"}]}
    checks = cross_agent_consistency_checks(engineering_plan_rev1, {"schedule_estimator": schedule})
    assert len(checks) == 1
    assert checks[0]["passed"] is False
    assert "phase-does-not-exist" in checks[0]["detail"]


def test_cross_agent_consistency_flags_unknown_component_id():
    poc_output = {"agent_id": "poc_planner", "modular_boundaries": [{"maps_to_component_id": "component-x"}]}
    architecture = {"components": [{"component_id": "component-y"}]}
    checks = cross_agent_consistency_checks(poc_output, {"solution_architect": architecture})
    assert len(checks) == 1
    assert checks[0]["passed"] is False
    assert "component-x" in checks[0]["detail"]


def test_cross_agent_consistency_returns_no_checks_when_no_related_outputs(engineering_plan_rev1):
    checks = cross_agent_consistency_checks(engineering_plan_rev1, {})
    assert checks == []


# ---------------------------------------------------------------------------
# Scoring math
# ---------------------------------------------------------------------------

def test_score_dimensions_hard_caps_groundedness_on_hallucinated_citation():
    groundedness_rule = {"has_hallucinated_citation": True}
    completeness_rule = {"coverage_ratio": 1.0}
    judge_output = {"groundedness_score": 4.5, "actionability_score": 4.0, "contradictions": []}
    scores, dimension_pass, _ = score_dimensions(groundedness_rule, completeness_rule, judge_output, [])
    assert scores["groundedness"] == 1.0  # capped despite judge scoring 4.5
    assert dimension_pass["groundedness"] is False


def test_score_dimensions_does_not_cap_when_no_hallucination():
    groundedness_rule = {"has_hallucinated_citation": False}
    completeness_rule = {"coverage_ratio": 1.0}
    judge_output = {"groundedness_score": 4.5, "actionability_score": 4.0, "contradictions": []}
    scores, dimension_pass, _ = score_dimensions(groundedness_rule, completeness_rule, judge_output, [])
    assert scores["groundedness"] == 4.5
    assert dimension_pass["groundedness"] is True


def test_score_dimensions_consistency_penalizes_contradictions():
    groundedness_rule = {"has_hallucinated_citation": False}
    completeness_rule = {"coverage_ratio": 0.5}
    judge_output = {
        "groundedness_score": 4.5, "actionability_score": 4.0,
        "contradictions": [{"this_output_statement": "a", "other_output_statement": "b",
                             "other_agent_id": "x", "explanation": "y"}],
    }
    structural_checks = [{"passed": False, "detail": "bad ref"}]
    scores, dimension_pass, contradiction_count = score_dimensions(
        groundedness_rule, completeness_rule, judge_output, structural_checks
    )
    assert contradiction_count == 2  # 1 judge-identified + 1 structural failure
    assert scores["consistency"] == 2.0  # 5.0 - 1.5*2
    assert dimension_pass["consistency"] is False
    assert scores["completeness"] == 2.5  # 5 * 0.5


# ---------------------------------------------------------------------------
# Badge computation boundaries
# ---------------------------------------------------------------------------

ALL_PASS = {"groundedness": True, "completeness": True, "consistency": True, "actionability": True}


def test_compute_badge_green_when_all_dimensions_pass_and_score_high():
    scores = {"groundedness": 5.0, "completeness": 5.0, "consistency": 5.0, "actionability": 5.0}
    overall, badge, dims_below = compute_badge(scores, ALL_PASS)
    assert overall == 5.0
    assert badge == "green"
    assert dims_below == 0


def test_compute_badge_amber_when_exactly_one_dimension_fails():
    scores = {"groundedness": 5.0, "completeness": 5.0, "consistency": 5.0, "actionability": 5.0}
    dimension_pass = {**ALL_PASS, "actionability": False}
    _overall, badge, dims_below = compute_badge(scores, dimension_pass)
    assert badge == "amber"
    assert dims_below == 1


def test_compute_badge_amber_when_overall_in_borderline_range():
    scores = {"groundedness": 3.5, "completeness": 3.5, "consistency": 3.5, "actionability": 3.5}
    overall, badge, dims_below = compute_badge(scores, ALL_PASS)
    assert overall == 3.5
    assert badge == "amber"


def test_compute_badge_red_when_two_or_more_dimensions_fail():
    scores = {"groundedness": 4.5, "completeness": 4.5, "consistency": 4.5, "actionability": 4.5}
    dimension_pass = {**ALL_PASS, "groundedness": False, "actionability": False}
    _overall, badge, dims_below = compute_badge(scores, dimension_pass)
    assert badge == "red"
    assert dims_below == 2


def test_compute_badge_red_when_overall_below_three():
    scores = {"groundedness": 2.0, "completeness": 3.0, "consistency": 3.0, "actionability": 3.0}
    overall, badge, _dims_below = compute_badge(scores, ALL_PASS)
    assert overall < 3.0
    assert badge == "red"


# ---------------------------------------------------------------------------
# Revision-cap enforcement
# ---------------------------------------------------------------------------

def test_enforce_revision_not_needed_when_no_dimensions_fail():
    revision_required, revision_count, escalated = enforce_revision(revision_count=0, dims_below=0)
    assert (revision_required, revision_count, escalated) == (False, 0, False)


def test_enforce_revision_required_when_under_cap():
    revision_required, revision_count, escalated = enforce_revision(revision_count=1, dims_below=1)
    assert revision_required is True
    assert escalated is False
    assert revision_count == 1  # unchanged -- caller increments


def test_enforce_revision_escalates_at_cap():
    revision_required, revision_count, escalated = enforce_revision(revision_count=REVISION_CAP, dims_below=1)
    assert revision_required is False
    assert escalated is True
    assert revision_count == REVISION_CAP


# ---------------------------------------------------------------------------
# Rubric prompt loading
# ---------------------------------------------------------------------------

def test_load_rubric_templates_extracts_both_fenced_blocks():
    system_prompt, user_template = load_rubric_templates()
    assert len(system_prompt) > 0
    assert len(user_template) > 0
    assert "{{brd_id}}" in user_template


# ---------------------------------------------------------------------------
# End-to-end review() against the mock judge -- pins the exact documented
# before/after numbers from docs/evaluation_report.md Section 4
# ---------------------------------------------------------------------------

def test_review_rev0_lands_red_matching_documented_baseline(engineering_plan_rev0, parsed_brd, retrieved_chunks):
    result = review(engineering_plan_rev0, parsed_brd, retrieved_chunks, judge_fn=mock_judge_fn)
    assert result["badge"] == "red"
    assert result["overall_score"] == 3.38
    assert result["revision_required"] is True
    assert result["scores"]["groundedness"] == 2.0
    assert result["scores"]["completeness"] == 2.5


def test_review_rev1_lands_green_matching_documented_result(engineering_plan_rev1, parsed_brd, retrieved_chunks):
    result = review(engineering_plan_rev1, parsed_brd, retrieved_chunks, judge_fn=mock_judge_fn)
    assert result["badge"] == "green"
    assert result["overall_score"] == 4.62
    assert result["revision_required"] is False
    assert result["scores"]["completeness"] == 5.0


def test_review_output_validates_against_critic_review_schema(engineering_plan_rev1, parsed_brd, retrieved_chunks):
    result = review(engineering_plan_rev1, parsed_brd, retrieved_chunks, judge_fn=mock_judge_fn)
    ok, event = validate_schema(result, "critic_review")
    assert ok is True, event["detail"] if event else None
