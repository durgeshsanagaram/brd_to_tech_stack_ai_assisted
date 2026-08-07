---
source_id: pattern-strangler-fig-01
source_type: architecture_pattern
title: Strangler Fig (Incremental Migration)
domain: general
complexity: null
tags: [migration, legacy, incremental, low-risk-rollout]
created_at: 2024-09-01
---

# Pattern: Strangler Fig (Incremental Migration)

## Description
An incremental migration strategy: a routing layer sits in front of a legacy system and
gradually redirects specific functionality to a new implementation, feature by feature, until the
legacy system can be retired. Not a target-state architecture itself, but a path to one.

## Trade-offs
- **Scalability:** Depends entirely on the target architecture being migrated to — this pattern
  is about the migration path, not the end state's scaling properties.
- **Team familiarity:** Medium. Conceptually simple, but requires discipline in maintaining the
  routing layer and running two systems in parallel during migration, which is easy to
  underestimate in planning.
- **Integration risk:** Low relative to a "big bang" rewrite — each migrated slice can be
  verified against the legacy system's behavior before full cutover, catching regressions early
  and in isolation.
- **Cost:** Medium — running legacy and new systems in parallel during migration has a real
  carrying cost (double infra, double on-call surface) for the migration's duration.

## When to Use
Replacing or modernizing a legacy monolith incrementally without a risky full cutover, especially
when the legacy system can't tolerate downtime and a rewrite-and-swap isn't acceptable to the
business.

## When to Avoid
Greenfield systems with no legacy system to migrate from — there's nothing to "strangle."
