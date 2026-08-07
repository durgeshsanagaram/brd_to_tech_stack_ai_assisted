---
source_id: pattern-cqrs-01
source_type: architecture_pattern
title: CQRS (Command Query Responsibility Segregation)
domain: general
complexity: null
tags: [cqrs, read-write-split, audit-trail, event-sourcing-adjacent]
created_at: 2024-09-01
---

# Pattern: CQRS (Command Query Responsibility Segregation)

## Description
Separates the write model (commands that change state) from the read model (queries), often
with each optimized independently — e.g. a normalized write store plus a denormalized read store
built for fast queries. Frequently paired with event sourcing, though not required.

## Trade-offs
- **Scalability:** High for read-heavy systems — read models can be scaled and denormalized
  independently of the write path's consistency requirements.
- **Team familiarity:** Low. One of the more conceptually demanding patterns in this library;
  teams unfamiliar with it tend to underestimate the operational complexity of keeping read and
  write models in sync.
- **Integration risk:** Medium-to-high. Read-model staleness (eventual consistency lag between
  write and read sides) must be handled explicitly by every consumer — a naive UI built assuming
  read-after-write consistency will show bugs intermittently.
- **Cost:** Medium-to-high. Effectively maintaining two data models (and often two data stores)
  increases both infra cost and the engineering cost of keeping them in sync.

## When to Use
Systems needing a full audit trail of state changes (every command recorded) combined with
demanding read-side query patterns that don't map well to the write model's schema. Good fit for
systems like a fraud-detection ledger where every decision must be traceable (audit) and the
case-management UI needs fast, flexible querying.

## When to Avoid
Simple CRUD systems with no meaningful audit requirement — the dual-model overhead has no
corresponding benefit and just adds complexity.
