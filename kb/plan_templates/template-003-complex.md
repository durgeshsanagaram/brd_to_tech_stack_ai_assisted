---
source_id: template-003
source_type: plan_template
title: Engineering Plan Template — Complex Real-Time ML Platform
domain: fintech
complexity: complex
tags: [ml, real-time, high-availability, regulated, multi-team]
created_at: 2025-06-10
---

# Engineering Plan Template — Complex Real-Time ML Platform

Used for: multi-team, regulated, real-time platforms with hard latency/availability NFRs and an
ML component. Reference case: Real-Time Fraud Detection Platform (brd-003).

## Phases
1. **Discovery & Architecture Decision Records** (3 weeks) — resolve open contradictions with
   sponsor/EM (e.g. latency vs. explainability trade-offs), decide build-vs-buy for supporting
   systems, define the ADR log.
2. **Core Scoring Path** (5 weeks) — rule engine + model-serving path built to the latency
   budget; fail-open/fail-closed behavior explicitly designed and tested.
3. **Case Management & Feedback Loop** (4 weeks) — analyst UI (or buy integration), model
   retraining feedback pipeline.
4. **Compliance & Explainability** (3 weeks) — audit trail, decision-rationale traceability,
   regulatory sign-off checkpoint.
5. **Resilience & DR Testing** (3 weeks) — chaos/failover testing against RPO/RTO targets, peak
   throughput testing.
6. **Phased Rollout with Shadow Mode** (3 weeks) — run new system in shadow (scoring but not
   deciding) before cutover, compare against legacy batch system, then cut over.

## Risks
- R-1: Latency budget and explainability requirement conflict (likelihood: high, impact: high) —
  mitigate by resolving as an explicit ADR in phase 1, not discovered mid-build; do not let
  discovery phase end without sign-off on this trade-off.
- R-2: Data science team lacks sub-150ms real-time inference experience (likelihood: high,
  impact: high) — mitigate with a dedicated ML-infra engineer or external consulting for phase 2;
  do not staff phase 2 with only application engineers.
- R-3: Build-vs-buy decision on case management left unresolved past discovery (likelihood:
  medium, impact: medium) — mitigate by defaulting to buy (lower engineering scope) if not
  decided by end of phase 1.
- R-4: Shadow-mode comparison reveals model/rule disagreement with legacy system at unacceptable
  rate (likelihood: medium, impact: high) — mitigate by budgeting 2 extra weeks of shadow mode
  before committing to a cutover date.

## Milestones
- M-1: All open contradictions resolved via ADR, build-vs-buy decided — end of phase 1.
- M-2: Core scoring path meeting p99 latency budget in staging — end of phase 2.
- M-3: Regulatory/compliance sign-off on audit trail — end of phase 4.
- M-4: DR test passing RPO/RTO targets — end of phase 5.
- M-5: Full cutover from legacy batch system — end of phase 6.

## Team Composition
- 3 backend engineers (full-time, phases 2–6).
- 2 ML engineers (full-time, phases 1–3; part-time phases 4–6 for retraining pipeline support).
- 1 ML-infra/latency specialist (full-time, phase 2; on-call phases 3–6).
- 1 compliance/audit liaison (part-time phases 1, 4).
- 1 QA/DR specialist (full-time, phase 5; part-time elsewhere).
- 1 EM/architect (full-time throughout — this template assumes active EM involvement given the
  volume of decisions requiring sign-off, not just periodic check-ins).

## Notes for Reuse
Fits BRDs with: hard real-time latency NFRs, regulatory/compliance requirements, an ML component,
and at least one unresolved contradiction or ambiguity in the source BRD. Total duration ~21
weeks, team of ~8 FTE at peak. The defining trait of this template vs. the medium template is
not team size alone — it's the presence of phase 1 as an explicit decision-resolution phase
rather than pure technical discovery, and a mandatory shadow-mode phase before cutover.
