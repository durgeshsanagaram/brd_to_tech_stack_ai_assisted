---
source_id: pattern-event-driven-01
source_type: architecture_pattern
title: Event-Driven Architecture
domain: general
complexity: null
tags: [event-driven, async, real-time, decoupled, streaming]
created_at: 2024-09-01
---

# Pattern: Event-Driven Architecture

## Description
Components communicate by publishing and subscribing to events on a broker (Kafka, EventBridge,
RabbitMQ, etc.) rather than calling each other directly. Producers and consumers are decoupled in
time and knowledge of each other.

## Trade-offs
- **Scalability:** High for throughput and for adding new consumers without touching producers.
  Well-suited to high-volume, real-time pipelines (e.g. fraud scoring, order processing) where
  multiple downstream systems need the same event stream.
- **Team familiarity:** Low-to-medium. Requires understanding of eventual consistency, message
  ordering guarantees (or lack thereof), idempotent consumers, and replay/dead-letter handling.
  Debugging is harder than synchronous call chains — a "request" has no single linear trace by
  default without added tracing infrastructure.
- **Integration risk:** Medium. Adding a new consumer is low-risk (doesn't touch producers), but
  schema evolution on events (changing an event's shape) risks breaking consumers that assumed
  the old shape — requires a documented event-schema versioning policy.
- **Cost:** Medium-to-high. Broker infrastructure (managed Kafka/EventBridge or self-hosted),
  plus monitoring for consumer lag and dead-letter queues.

## When to Use
Real-time or near-real-time pipelines with multiple independent consumers of the same data;
systems where producers shouldn't need to know who consumes their events (e.g. fraud detection
publishing risk scores that feed both a case-management UI and a retraining pipeline).

## When to Avoid
Simple request/response workflows where synchronous behavior is actually required (the caller
needs an immediate answer, not eventual delivery) — forcing these into an event-driven shape adds
latency and complexity without benefit.
