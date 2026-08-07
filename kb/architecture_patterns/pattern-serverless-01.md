---
source_id: pattern-serverless-01
source_type: architecture_pattern
title: Serverless (Function-as-a-Service)
domain: general
complexity: null
tags: [serverless, faas, low-ops, variable-load]
created_at: 2024-09-01
---

# Pattern: Serverless (Function-as-a-Service)

## Description
Business logic runs as individually deployed functions (AWS Lambda, Azure Functions, Cloud
Functions) invoked by triggers (HTTP request, queue message, schedule), with the cloud provider
managing scaling and infrastructure entirely.

## Trade-offs
- **Scalability:** High and automatic — scales to zero when idle and up on demand without
  capacity planning. Best suited to workloads with variable or unpredictable traffic.
- **Team familiarity:** Medium. Concepts are approachable, but cold-start latency, execution time
  limits, and provider-specific deployment tooling introduce a learning curve distinct from
  traditional server deployment.
- **Integration risk:** Medium. Vendor lock-in is a real cost — migrating off a specific
  provider's FaaS platform later is nontrivial. Also, cold-start latency can violate strict
  real-time NFRs (a poor fit for e.g. a 150ms p99 hard latency budget).
- **Cost:** Low at low-to-moderate, spiky traffic (pay only for execution time); can exceed
  always-on server costs at sustained high, constant load.

## When to Use
Spiky or unpredictable workloads (e.g. scheduled batch jobs, low-frequency admin operations,
notification sending) where paying for idle capacity would be wasteful.

## When to Avoid
Hard real-time latency budgets (cold starts are unpredictable), or sustained high-throughput
workloads where always-on infrastructure is cheaper per-request than FaaS pricing.
