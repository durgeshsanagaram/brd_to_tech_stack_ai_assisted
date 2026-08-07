---
source_id: brd-003
source_type: past_brd
title: Real-Time Fraud Detection Platform
domain: fintech
complexity: complex
tags: [fraud, real-time, ml, high-availability, fintech]
created_at: 2025-05-30
---

# BRD: Real-Time Fraud Detection Platform

## Objectives
Build a platform that scores every transaction for fraud risk in real time (before authorization
completes), replacing the current nightly batch fraud review. Must reduce fraud losses while
keeping false-positive declines low enough to avoid harming legitimate customer experience.

## Functional Requirements
- FR-1: Score every transaction in real time and return a risk decision (approve / decline /
  review) before authorization completes.
- FR-2: Support rule-based checks (velocity limits, geo-mismatch, denylists) alongside an ML risk
  score.
- FR-3: Case management UI for fraud analysts to review "review"-flagged transactions.
- FR-4: Feedback loop — analyst decisions feed back into model retraining pipeline.
- FR-5: Configurable rule engine — fraud ops team can add/adjust rules without a code deploy.
- FR-6: Full audit trail of every decision, including which rule or model version fired.
- FR-7: Support both card-present and card-not-present transaction types (different risk
  signals).

## Non-Functional Requirements
- NFR-1: Decision latency budget: p99 under 150ms (hard authorization-flow constraint).
- NFR-2: Availability: 99.99% — a fraud-scoring outage must not block legitimate transactions
  (fail-open with conservative default rules, documented risk trade-off).
- NFR-3: Throughput: must handle 5,000 transactions/second at peak (holiday shopping).
- NFR-4: Model decisions must be explainable enough for regulatory audit (no fully opaque
  black-box scoring without a rationale trace).
- NFR-5: All transaction data is PCI-DSS and PII-sensitive — full encryption at rest and in
  transit, strict data retention limits.
- NFR-6: Disaster recovery: RPO 5 minutes, RTO 15 minutes for the scoring service.

## Constraints
- Must not increase checkout/authorization latency beyond the 150ms budget under NFR-1 — this
  conflicts on paper with NFR-4 (explainability often implies heavier models); BRD does not
  resolve this trade-off explicitly. **Flagged as a contradiction requiring EM decision.**
- Existing data science team has production ML experience but not with sub-150ms real-time
  inference; this is a stated team capability gap, not just a technical constraint.
- Must integrate with three existing systems: authorization gateway (proprietary), case
  management (build vs. buy undecided in BRD — **ambiguous**), and the data warehouse (for
  historical feature computation).

## Stakeholders
- Sponsor: Chief Risk Officer.
- Secondary: VP Engineering (latency/availability trade-offs), Head of Data Science (model
  ownership), Compliance/Legal (audit trail, explainability).
- Primary users: fraud analysts (case management), risk/compliance auditors.

## Success Metrics
- Fraud loss rate reduced by 30% within 6 months of launch.
- False-positive decline rate held under 0.5% (current baseline 0.4% with batch system —
  BRD requires no regression).
- p99 decision latency under 150ms in production, sustained at peak throughput.

## Notes
This BRD has the highest ambiguity/contradiction density in the knowledge base and is used as
the "complex" calibration case for guardrail testing — specifically the 150ms-vs-explainability
conflict (NFR-1 vs NFR-4) and the undecided build-vs-buy case management system. Per guardrail
policy, both were flagged rather than resolved silently; the conservative default applied
downstream was to buy an off-the-shelf case management tool (lower engineering scope) and to
document the latency/explainability trade-off as an open decision for the EM rather than pick
one side.
