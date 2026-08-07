---
source_id: pattern-microservices-01
source_type: architecture_pattern
title: Microservices
domain: general
complexity: null
tags: [microservices, distributed, independent-deploy, multi-team]
created_at: 2024-09-01
---

# Pattern: Microservices

## Description
Decomposes the system into independently deployable services, each owning its own data store,
communicating over the network (REST/gRPC/messaging). Services are organized around business
capabilities, not technical layers.

## Trade-offs
- **Scalability:** High. Each service scales independently based on its own load profile — the
  primary reason to choose this pattern when one component (e.g. search, scoring) has NFRs far
  exceeding the rest of the system.
- **Team familiarity:** Low-to-medium. Requires distributed-systems literacy: network failure
  handling, eventual consistency, distributed tracing/debugging. Steepest learning curve of the
  patterns in this library for teams without prior experience.
- **Integration risk:** Medium-to-high. Clear service boundaries help external integration, but
  internal inter-service integration introduces its own risk surface — version skew between
  services, network partition handling, and distributed transaction complexity (no free ACID
  across service boundaries).
- **Cost:** Medium-to-high. Per-service infra (deploy pipeline, monitoring, service discovery),
  plus inter-service network cost and often a service mesh or API gateway layer.

## When to Use
Multiple teams needing independent deploy cadence; components with significantly different
scaling profiles; systems expected to grow well beyond a single team's ownership.

## When to Avoid
Small teams (under ~8 engineers) — the operational overhead (multiple deploy pipelines, service
discovery, distributed observability) typically outweighs the scaling benefit before the team is
large enough to have dedicated platform/infra capacity.
