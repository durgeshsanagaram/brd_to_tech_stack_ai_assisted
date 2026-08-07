---
source_id: template-001
source_type: plan_template
title: Engineering Plan Template — Simple Internal Tool
domain: internal-tools
complexity: simple
tags: [crud, small-team, low-risk]
created_at: 2024-11-20
---

# Engineering Plan Template — Simple Internal Tool

Used for: single-team, low-risk internal tools (CRUD apps, internal dashboards, directory-style
systems). Reference case: Internal Employee Directory Refresh (brd-001).

## Phases
1. **Discovery & Data Model** (1 week) — confirm data model against HRIS export, SSO integration
   spike.
2. **Core Build** (2 weeks) — search, edit-profile, org chart views.
3. **Admin Tools & Import** (1 week) — bulk import, CSV export.
4. **Hardening & Rollout** (1 week) — VPN-only access verification, load test to NFR target,
   phased rollout by department.

## Risks
- R-1: HRIS export format drift (likelihood: medium, impact: low) — mitigate with a schema
  validation step on import.
- R-2: SSO integration delay from IT (likelihood: low, impact: medium) — mitigate by starting
  the SSO spike in week 1, not after core build.

## Milestones
- M-1: Data model confirmed, SSO spike passing — end of week 1.
- M-2: Search + edit-profile demoable — end of week 3.
- M-3: Rollout to 100% of employees — end of week 5.

## Team Composition
- 1 backend engineer (full-time, weeks 1–5).
- 1 frontend engineer (full-time, weeks 1–5).
- 0.25 FTE HR ops liaison (weeks 1, 4–5, for data validation and rollout comms).

## Notes for Reuse
This template fits BRDs with: single primary user group, no real-time/high-throughput NFRs, one
external integration (SSO or similar), and a sponsor who has not fixed a hard deadline. Total
duration ~5 weeks, team of 2 engineers. Scale phase count up, not duration per phase, if a second
integration is added.
