---
source_id: org-standards-001
source_type: org_standard
title: Org Engineering Standards
domain: general
complexity: null
tags: [standards, governance, approved-stacks, security, ci-cd]
created_at: 2025-06-01
---

# Org Engineering Standards

## 1. Approved Stacks

The following are pre-approved for new projects without an architecture review exception:

- **Backend:** Node.js, Go, Python (FastAPI/Django), Java (Spring). Any other backend language
  requires an architecture review exception (Section 5).
- **Frontend:** React (preferred), or plain server-rendered templates for low-interactivity
  internal tools.
- **Databases:** PostgreSQL (default relational choice), Redis (caching/session store), Kafka
  (event streaming). MongoDB and Cassandra are approved but require a documented justification
  in the architecture review (they are not default choices — see decision log entries dec-005
  and dec-008 for past outcomes).
- **Cloud:** AWS is the primary approved provider. Multi-cloud requires an exception.

## 2. Coding Standards

- All services must have automated linting and formatting enforced in CI (no merge without
  passing lint).
- Public APIs (REST/gRPC) must be documented with an OpenAPI or protobuf schema before merge.
- No secrets in source control — secrets must be sourced from the org secrets manager at runtime.
- Minimum 70% unit test coverage for new services; 100% coverage on payment/fraud-adjacent code
  paths specifically.

## 3. CI/CD

- All services deploy through the central CI/CD pipeline (no manual production deploys).
- Every production deploy requires: passing test suite, passing lint, and one peer approval on
  the pull request.
- Staged rollout (canary or percentage-based) is required for any service handling checkout,
  payment, or fraud-scoring traffic. Non-critical internal tools may deploy directly to 100%.
- Rollback must be automatable within 5 minutes for any customer-facing service.

## 4. Security

- All data in transit must use TLS 1.2+.
- PII and payment data must be encrypted at rest.
- Services touching payment data must not expand PCI-DSS scope without a security review sign-off
  — this is a hard gate, not a recommendation (see brd-003's NFR-5 for an example of a project
  where this constraint directly shaped the architecture).
- Access to production data stores requires named individual credentials — no shared service
  accounts for human access.

## 5. Architecture Review Criteria

An architecture review is required before build begins when any of the following apply:
- The system introduces a new database technology not in the pre-approved list.
- The system has a hard real-time latency budget under 200ms.
- The system is expected to handle regulated data (PCI, PII at scale, or data subject to
  compliance audit).
- The system spans more than one team's ownership boundary.

Review criteria evaluated: does the chosen pattern match team familiarity and scale needs
(reference the architecture pattern library); does the plan account for the NFRs as stated in the
BRD; is there a documented fallback/degradation behavior if a dependency fails.

## 6. Observability & Monitoring

- Every production service must emit structured logs, request-level tracing, and at minimum:
  error rate, p50/p95/p99 latency, and throughput metrics.
- Alerting thresholds must be defined before launch, not added reactively after an incident.
- Services with a hard latency budget (per Section 5) must have latency-budget alerting
  specifically, not just generic error-rate alerting.
- No raw customer PII or payment data in log output — log hashes or redacted identifiers only.
