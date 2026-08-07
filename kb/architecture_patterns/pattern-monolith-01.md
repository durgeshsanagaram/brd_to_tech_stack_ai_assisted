---
source_id: pattern-monolith-01
source_type: architecture_pattern
title: Monolith
domain: general
complexity: null
tags: [monolith, single-deployable, low-team-overhead]
created_at: 2024-09-01
---

# Pattern: Monolith

## Description
A single deployable application containing all business logic, typically layered internally
(presentation, business logic, data access) but shipped and scaled as one unit.

## Trade-offs
- **Scalability:** Low-to-medium. Scales by running more copies of the whole app; cannot scale
  individual components independently. Fine up to moderate traffic; becomes costly when one
  hot path (e.g. search) needs 10x the capacity of the rest of the app.
- **Team familiarity:** High. Lowest cognitive overhead — one codebase, one deploy pipeline, one
  set of local-dev instructions. Best fit for small teams (1–5 engineers).
- **Integration risk:** Low for internal changes (single codebase, compiler/type-checker catches
  cross-module breakage); higher when *other* systems need to integrate with it, since there's no
  natural service boundary — external integration often means carving out an API from internal
  code not designed to be a boundary.
- **Cost:** Low. One deployment target, minimal infra overhead (no service mesh, no
  inter-service network cost).

## When to Use
Small teams, simple-to-medium complexity domains, no component with wildly different scaling
needs than the rest of the system. Reference: Internal Employee Directory Refresh (brd-001) used
a monolith successfully.

## When to Avoid
Multiple teams needing independent deploy cadence; one component with NFRs (throughput, latency)
far exceeding the rest of the system; regulatory need to isolate a sensitive component (e.g.
payment processing) for audit/compliance boundary reasons.
