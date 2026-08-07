---
source_id: pattern-layered-01
source_type: architecture_pattern
title: Layered (N-Tier)
domain: general
complexity: null
tags: [layered, n-tier, traditional]
created_at: 2024-09-01
---

# Pattern: Layered (N-Tier)

## Description
Organizes the system into horizontal layers (presentation, application/business, data access,
database), each depending only on the layer below it. Often implemented within a monolith, but
distinct from "monolith" in that it prescribes internal structure rather than deployment unit.

## Trade-offs
- **Scalability:** Medium. Each layer can in principle be scaled or replaced independently (e.g.
  swap the data-access layer's database), but in practice most implementations still deploy as
  one unit, inheriting monolith-like scaling limits.
- **Team familiarity:** High. Well-understood, widely taught pattern; easy onboarding for new
  engineers.
- **Integration risk:** Medium. Clear internal seams (layer boundaries) make it easier to later
  extract a layer into its own service than an unstructured monolith, but layer boundaries are
  often violated in practice ("layer leakage") without strict discipline.
- **Cost:** Low-to-medium, similar to monolith unless layers are deployed as separate services.

## When to Use
Teams wanting more internal structure than a plain monolith without committing to distributed
systems complexity. Good stepping stone toward microservices if layer boundaries are kept clean
from the start.

## When to Avoid
Systems with genuinely independent scaling needs per layer/component in production — layered
architecture's boundaries are a code-organization discipline, not a deployment/scaling
mechanism, so it doesn't solve throughput isolation problems on its own.
