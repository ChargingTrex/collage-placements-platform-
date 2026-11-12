# A4 — Company & Notifications

Read [`CONTEXT.md`](../CONTEXT.md) first.

## Phase A — stream A-4 and A-6

| Stream | Gaps | Work |
| --- | --- | --- |
| **A-4** | G11–G15 | `display_name` · `personal_email` · MFA for admin roles · revocation on status change · identity access logging |
| **A-6** | G17, G18 | The `Company` entity · recruiter users belonging to it · `ADM-`/`CMP-` id issuance · repointing `CompanyShortlist.company` · `company_recruiter:<uuid>` role scoping |

### A-6 fixes a live bug

`CompanyShortlist.company` is a foreign key to **`User`**, so a shortlist
belongs to a recruiter rather than a company. Two recruiters at one company
hold separate shortlists — and because "shortlisted only" visibility is
computed from that table, **a student is visible to one recruiter and returns
404 for their colleague.** Invisible until a company has a second account.

`Company` is: `id` (UUID, what FKs reference) · `company_id` (`CMP-0001`, the
human key) · `name` · `email` (organisation contact, not a recruiter's).

`ADM-` and `CMP-` ids are portal-issued, sequential, unique, immutable, never
reused — the same discipline as PRN.

## Phase D — your lead phase

`agents.md` Phase 6. One hard rule: **notification channels are in-app and
email only**, enforced server-side. The platform rejects anything else with
422; the portal matches that policy rather than trusting callers.
