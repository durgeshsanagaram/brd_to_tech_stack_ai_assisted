---
source_id: pattern-service-mesh-01
source_type: architecture_pattern
title: Service Mesh
domain: general
complexity: null
tags: [service-mesh, microservices-add-on, observability, multi-team]
created_at: 2024-09-01
---

# Pattern: Service Mesh

## Description
An infrastructure layer (e.g. Istio, Linkerd) added atop a microservices architecture, handling
service-to-service traffic concerns — retries, timeouts, mTLS, load balancing, and observability
— via sidecar proxies, out of application code. Not a standalone architecture; it's an
augmentation applied on top of microservices.

## Trade-offs
- **Scalability:** High — same benefit as the underlying microservices architecture, with better
  operational control over traffic (canary releases, circuit breaking) at scale.
- **Team familiarity:** Low. Adds a substantial new operational surface (sidecar proxies, mesh
  control plane) on top of microservices' own learning curve; typically only justified once an
  organization already has meaningful microservices operational maturity.
- **Integration risk:** Medium. Simplifies cross-cutting concerns (retries, mTLS) that would
  otherwise be duplicated per-service, but the mesh itself becomes a critical-path dependency —
  a mesh misconfiguration can take down inter-service traffic broadly.
- **Cost:** High. Additional infra (sidecars per service instance, control plane), plus the
  engineering cost of operating it.

## When to Use
Organizations already running microservices at meaningful scale (dozens of services, multiple
teams) that need consistent traffic policy, mTLS, and observability without duplicating that
logic in every service.

## When to Avoid
Any organization not already past the microservices adoption threshold — adding a mesh before
microservices complexity justifies it is pure overhead with no payoff.
