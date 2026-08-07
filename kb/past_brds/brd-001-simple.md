---
source_id: brd-001
source_type: past_brd
title: Internal Employee Directory Refresh
domain: internal-tools
complexity: simple
tags: [crud, internal, low-risk]
created_at: 2024-11-04
---

# BRD: Internal Employee Directory Refresh

## Objectives
Replace the aging employee directory (last updated 2016) with a searchable, self-service
directory. Employees should be able to find colleagues by name, team, or location, and update
their own profile photo and contact info.

## Functional Requirements
- FR-1: Search employees by name, team, or office location.
- FR-2: Employees can edit their own phone number, office location, and profile photo.
- FR-3: Org chart view showing manager and direct reports.
- FR-4: Admin role can bulk-import employees from HRIS CSV export.
- FR-5: Export current directory to CSV for offline use.

## Non-Functional Requirements
- NFR-1: Support up to 3,000 employees (current headcount 1,800).
- NFR-2: Page load under 2 seconds on internal network.
- NFR-3: Only accessible on corporate VPN.

## Constraints
- Must integrate with existing SSO (Okta).
- No budget for a dedicated mobile app; responsive web only.

## Stakeholders
- Sponsor: VP of People Operations.
- Primary users: all employees.
- Admin users: HR operations team (3 people).

## Success Metrics
- 80% of employees use self-service edit within first month.
- Directory search reduces "who is X" Slack questions (informal, not tracked numerically).

## Notes
Low ambiguity. Requirements were reviewed with HR ops twice before submission. No known
contradictions. Timeline expectation from sponsor: "a few weeks," not formally scoped.
