---
source_id: brd-002
source_type: past_brd
title: Customer Loyalty Points Engine
domain: e-commerce
complexity: medium
tags: [loyalty, integrations, e-commerce]
created_at: 2025-02-18
---

# BRD: Customer Loyalty Points Engine

## Objectives
Introduce a points-based loyalty program: customers earn points per purchase, redeem points for
discounts, and see balance/history in their account. Must integrate with the existing checkout
and order-management systems without disrupting current checkout conversion.

## Functional Requirements
- FR-1: Award points on order completion (1 point per $1 spent, configurable rate).
- FR-2: Redeem points at checkout as a discount (max 50% of order value).
- FR-3: Points balance and transaction history visible in customer account page.
- FR-4: Points expire after 12 months of account inactivity.
- FR-5: Admin dashboard to adjust point rates and issue manual point grants (customer service
  use case — e.g., goodwill credit).
- FR-6: Email notification when points are about to expire (30 days prior).

## Non-Functional Requirements
- NFR-1: Points calculation must complete within checkout flow with no more than 200ms added
  latency.
- NFR-2: System must handle Black Friday peak load: ~15,000 orders/hour.
- NFR-3: Points ledger must be auditable — every point grant/redemption traceable to an order ID
  or admin action.
- NFR-4: PCI-DSS scope must not expand — points engine must not touch raw payment data.

## Constraints
- Must integrate with existing order-management system (proprietary, REST API, rate-limited to
  100 req/s).
- Existing checkout is a monolith; loyalty engine should not require a full checkout rewrite.
- Marketing wants configurable point rates without a code deploy (self-service admin UI).

## Stakeholders
- Sponsor: VP of Marketing.
- Secondary sponsor: Head of Customer Support (manual grant workflow).
- Engineering owner: Checkout platform team.

## Success Metrics
- 25% of active customers redeem points within 90 days of launch.
- Zero checkout latency regression beyond the 200ms budget.
- Support team able to issue manual grants without an engineering ticket.

## Notes
One ambiguity flagged during review: "configurable point rate" — unclear if rate can vary by
product category or is a single global rate. BRD does not specify; assumption applied by
downstream planning was a single global rate with per-category as a documented future
enhancement (conservative interpretation — lower scope).
