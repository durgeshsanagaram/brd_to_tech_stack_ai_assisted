# Operationalization & Monitoring Plan

Per BRD Section 9: success/failure criteria defined upfront, pre-release gates, and a monitoring
approach. Where a number below is already measured (via `docs/evaluation_report.md`), it's cited
as a baseline; where it's a target for scale, it's marked as such rather than presented as
observed fact.

## 1. Success Criteria

Three measurable, already-checkable criteria (not aspirational — each maps to a real assertion in
the codebase):

| # | Criterion | Measured via | Current baseline |
| :---- | :---- | :---- | :---- |
| 1 | 100% of agent outputs pass schema validation before reaching the Critic or the EM | `scripts/guardrails.py::validate_schema`, enforced at every handoff in `scripts/orchestrator.py::call_agent_with_retries` | 5/5 agents, one full run (`docs/evaluation_report.md` §5) |
| 2 | Actionability score ≥4/5 on the eval dataset (BRD Section 7B) | `scripts/critic.py::score_dimensions` | 4.0/5.0 on both rev0 and rev1 of the one BRD run to date |
| 3 | End-to-end pipeline (5 agents + Critic + guardrails) completes without escalation, for any BRD matching the parser's supported structure | `scripts/orchestrator.py::run_pipeline`, `pipeline_status == "complete"` | Achieved on all 3 eval BRDs (brd-001/002/003); latency not yet formally budgeted (see gap in §5) |

A fourth criterion worth tracking once more BRDs run through the system: **guardrail
false-positive/false-negative rate on the eval dataset stays at 0**, per the 10/10 correct
guardrail test results in `docs/evaluation_report.md` §6. This is a floor, not a target — any
regression here should block release (see §3).

## 2. Failure Modes & Mitigations

At least three, each with a mitigation already implemented rather than merely planned:

| # | Failure mode | Mitigation | Where it's implemented |
| :---- | :---- | :---- | :---- |
| 1 | Agent output fails schema validation (malformed JSON, missing required field) | Retry once with the same inputs; if still invalid, escalate — do not silently pass broken output downstream | `scripts/orchestrator.py::call_agent_with_retries` (`MAX_RETRIES = 1`), sets `agent_states[].status = "failed"` and `pipeline_status = "failed"` on exhaustion |
| 2 | No RAG hits above the similarity threshold for an agent's query | Proceed with an explicit disclaimer instead of forcing a citation; downstream badge should reflect the gap (Amber) rather than hide it | `scripts/query.py::main` prints the "no RAG hits" guardrail message; the Critic's groundedness scoring would reflect the resulting uncited claims |
| 3 | Critic revision loop does not converge (agent keeps failing the same dimension) | Hard cap at 2 revision cycles; on the 3rd failure, stop looping and flag to the EM with the badge as computed (Amber/Red), rather than looping indefinitely | `scripts/critic.py::enforce_revision` (`REVISION_CAP = 2`), `escalated_to_em` flag in `schemas/critic_review.schema.json` |
| 4 | Retrieval similarity threshold or query framing is miscalibrated for the current embedding model/corpus | Threshold and per-source-type query framing are documented as re-measurable, not hardcoded assumptions; re-validate with the control-query method before trusting retrieval at a new scale | `docs/rag_design.md` § "Threshold calibration" — this is not hypothetical: the original 0.72 threshold was found to silently discard 100% of real hits during actual end-to-end testing (`docs/evaluation_report.md` §5) and was corrected to 0.30 |
| 5 | Vector DB (Chroma) or embedding API unavailable | Not yet implemented — currently an unhandled dependency failure. See gap in §5 | — |
| 6 | LLM API failure/rate limit during generation or Critic judging | Not yet implemented — `judge_fn`/`agent_fn` calls have no retry/backoff wrapper of their own (distinct from the schema-retry in #1, which retries generation but not transient API errors specifically). See gap in §5 | — |

Failure modes 5 and 6 are known, named gaps rather than omissions — see §5.

## 3. Pre-Release Gates

Before a change to any agent prompt, schema, or retrieval configuration ships, all of the
following must hold. This list is the actual checklist to run, not a description of a checklist:

1. **Schema validation**: 100% of the 5 agent contracts plus the Critic and Orchestrator-state
   contracts validate against their `schemas/*.json` files (`python scripts/guardrails.py --demo`
   §2, or run each schema against a fresh sample output).
2. **Guardrail suite**: all cases in `docs/evaluation_report.md` §6 still pass (10/10 currently) —
   no new false positive (valid input rejected) or false negative (bad input passed).
3. **Eval methods**: at least 2 of the implemented methods (rule-based, LLM-as-judge,
   execution-based — `docs/evaluation_report.md` §2) run against the eval dataset and results
   documented, not just spot-checked.
4. **Revision loop**: at least one before/after example on record showing the Critic driving a
   real quality improvement (currently: rev0 🔴 3.38 → rev1 🟢 4.62, `docs/evaluation_report.md` §4).
5. **Cross-agent consistency**: the structural checks in
   `scripts/critic.py::cross_agent_consistency_checks` pass for the reference BRD run.
6. **No unresolved guardrail escalations**: zero `escalated_to_em: true` outputs in the most
   recent full pipeline run, or an explicit, reviewed reason why one remains.

A change that fails any gate does not ship; it goes back through the revision loop or a manual
fix, the same discipline the system enforces on its own agents.

## 4. Logging & Monitoring

**What's logged today**, per agent execution, via `scripts/guardrails.py::log_agent_execution`
(structured JSONL, one file per `run_id` under `logs/`):

- `input_hash` — SHA-256 of the raw BRD/input text; the raw text itself is never written to disk
- `rag_chunks_retrieved` — `chunk_id`s only
- `output_produced` — the full structured output, with citation `excerpt` fields replaced by their
  hash (`redact_for_logging`) so retrieved BRD/org-standard text never leaks into logs even
  indirectly
- `critic_score`, `execution_time_ms`, `guardrail_triggers`, `revision_count`

This was verified, not just written: a real log entry was inspected and confirmed to contain zero
raw BRD text, only hashes (`docs/evaluation_report.md` §6, confidentiality row).

**Monitoring metrics to stand up on top of this log** (not yet built — this is the plan, distinct
from what's implemented above):

| Metric | Why it matters | Alerting posture |
| :---- | :---- | :---- |
| Badge distribution (Green/Amber/Red %) over a rolling window | Detects silent quality regression in a prompt/schema change before it's noticed downstream | Alert if Red % rises above a defined floor (e.g. >10% of runs) — threshold to be set once enough real-BRD volume exists to baseline against |
| Revision-count distribution (0 / 1 / 2 / escalated) | A rising share of `escalated_to_em: true` means the revision loop is failing to converge, not just that inputs got harder | Alert on any escalation immediately post-launch (low volume); move to a rate-based threshold at scale |
| Guardrail trigger rate by type (`input_validation`, `schema_compliance`, `hallucination`, `scope_creep`, `confidentiality`, `cross_agent_consistency`) | A spike in one guardrail type pinpoints which failure mode (§2) is actually occurring in production | Per-type alert, since each type maps to a different root cause and a different fix |
| "No RAG hits" rate per agent | Directly measures whether the KB/retrieval config still matches the BRDs being submitted | Alert if any agent's rate exceeds a small baseline — this is the earliest signal of a retrieval miscalibration like the one found in §2 row 4 |
| p50/p95/p99 execution_time_ms per agent | Latency budget tracking (ties to Success Criterion #3) | Alert on p95 latency budget breach, per the pattern in `kb/org_standards/org-standards-001.md` § Observability & Monitoring, which requires latency-budget alerting specifically wherever a hard budget exists — not just generic error-rate alerting |

Per the org standard already in the KB (`org-standards-001.md` § 6), alerting thresholds must be
defined before launch, not added reactively after an incident — the table above is that upfront
definition, even though the dashboards themselves aren't built yet.

## 5. Known Gaps (Explicit, Not Hidden)

- **No retry/backoff for transient LLM/embedding API failures.** The current retry logic
  (`call_agent_with_retries`) retries on schema validation failure, not on network/rate-limit
  errors from the generation or judge calls themselves. A production version needs a separate
  exponential-backoff wrapper around `agent_fn`/`judge_fn` calls.
- **No vector DB availability handling.** If Chroma is unreachable, `build_collection` raises
  rather than degrading gracefully (e.g. skip RAG, flag Amber, continue). Not yet implemented.
- **Latency budget not yet formally set.** Success Criterion #3 notes the pipeline completes on
  all 3 eval BRDs, but no p95 target has been set or measured across repeated runs — 3 data
  points isn't enough to characterize a distribution (`docs/evaluation_report.md` §8).
- **Monitoring dashboards are a plan, not a build.** §4's metrics table is the design; no
  dashboard/alerting infrastructure exists yet. Structured logs are in place and are the
  prerequisite for building it.

## 6. Scaling Beyond a Single BRD at a Time

Per `docs/architecture.md`'s orchestration justification: at 50+ BRDs/week, the single
Orchestrator-instance-per-run model would shard by BRD (one Orchestrator instance per in-flight
BRD, horizontally scaled), and the vector store would move from local Chroma to a managed cloud
vector DB (Qdrant/Pinecone) to handle concurrent read load without one BRD's retrieval contending
with another's. The logging/monitoring design in §4 doesn't change at that scale — it's
already per-`run_id`, which is what makes per-BRD sharding observable in the first place.
