# Next phases — B, C, D

What to build after Phase A and the addendum (R1–R5) close. This is an outline,
not a build: enough that the next session starts on the checkpoint tests
straight away instead of re-deriving the design.

Each phase follows the same rule as Phase A: **write the checkpoint tests first,
run them red, then build until they pass.** Definitions of done come from
[`agents.md`](agents.md) Phases 4–6 and [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §6.

| Phase | agents.md | Lead agent | Gate |
| --- | --- | --- | --- |
| B · Opportunities Board | Phase 4 | A2 | agents.md Phase 4 smoke test |
| C · Certification Suggestions | Phase 5 | A3 | agents.md Phase 5 smoke test |
| D · Company Self-Service & Notifications | Phase 6 | A4 | **Full comprehensive E2E**, every role |

---

## Carry-ins: true for every phase

These come from decisions already taken. A design that breaks one is wrong.

- **UUID carries every join; PRN is a filter and an export column** (D8, D14).
  Every new list endpoint declares `?prn=` and `?prns=` with `unmatched_prns`
  (`core.filters.HumanKeyFilter`, `HumanKeyInFilter`,
  `ReportUnmatchedPrnsMixin`). Every CSV export has PRN as its first column.
- **Unknown query parameters are a 400** (D12). Declare every filter.
- **Opportunities and applications belong to a `Company`**, never to a recruiter
  `User`. Otherwise two recruiters at one company see different data, which is
  the bug already fixed for shortlists.
- **Department, programme, school and year are snapshotted onto the application
  row at apply time** (G16). If you join them live, a student who changes programme
  rewrites last year's figures.
- **Authorisation is local** (§4.4). A `company_recruiter:<uuid>` role authorises
  nothing by itself. Each view checks that the recruiter's company owns the object.
- **Applying creates the `CompanyShortlist` link.** Without it, a student on
  "shortlisted only" visibility can never be reached by a new company. Pinned by
  `test_narrowing_to_shortlisted_keeps_the_companies_already_interested`.
- **Notifications go to in-app and email only**, and the server rejects any other
  channel with a 422.
- **Documents go through authenticated endpoints** (D25), and each admin or
  company open is audit-logged.
- **Career path and transcripts stay hidden from companies** (D24). Do not add them
  to any company-facing payload, ranking signal or export.

---

## Phase B — Opportunities Board

**Goal.** An admin posts an opportunity. Students see a ranked feed with an
eligible / not-eligible flag and apply in-app. Admins move applications through
the status lifecycle, bulk-screen with the matching engine, and export a shortlist.

**Models** (`opportunities/`)

| Model | Fields |
| --- | --- |
| `Opportunity` | UUID `id`, `company` FK → `Company`, `title`, `role_type` (internship / full_time), `description` (the job description the engine scores against), `required_skills` (M2M via slugs, same as `ProfileSkill`), `eligible_departments` (programme codes from `roster.reference`), `min_cgpa`, `deadline`, `status` (draft / open / closed), `similarity_threshold` (nullable, so it falls back to the config default), `min_experience_years`, `required_education_levels`, `created_by` |
| `Application` | UUID `id`, `opportunity` FK, `profile` FK, `status` (applied → shortlisted → interview → offer / rejected, plus withdrawn), the snapshot fields (`department`, `programme`, `school`, `batch`, `year_of_study`, `cgpa_at_apply`), `resume_snapshot` (file or text, frozen at apply time), `score`, `similarity` |
| `ApplicationEvent` | Status history: who moved it, from what, to what, and when. The audit trail and the source for the "time to shortlist" metric |

**Endpoints** (plural nouns, verb sub-resources, so the Phase E `/api/v1` move is mechanical)

- `opportunities/` CRUD (admin), with `close` as a sub-resource
- `opportunities/feed` (student): ranked, with `eligible`, `score` and `reasons`
- `opportunities/<id>/apply` (student)
- `applications/` filters: `?opportunity=`, `?status=`, `?prn=`, `?prns=`. Lists are admin-wide, scoped to the company for recruiters, and own-only for students
- `applications/<id>/status` (admin, later the owning company)
- `opportunities/<id>/screen` takes a threshold and hard filters and returns the ranked shortlist. It wraps `matching.engine.get_engine().screen(...)`
- `opportunities/<id>/shortlist/export` returns a CSV with PRN first

**Ranking.** Skills overlap, department and CGPA eligibility, and certifications
held (once Phase C lands), blended with the engine's similarity score. The weights
and the threshold come from settings, never from literals in code. Eligibility is a
hard flag, separate from the score.

**UI.**
- Student: feed page, opportunity detail, apply button, "My applications" with status.
- Admin: opportunity editor, applicants table per opportunity, screening panel (threshold slider and filters), export.

**Checkpoint B tests to write first**

1. A student matching on skills and department ranks an opportunity above a student who doesn't, and is flagged eligible.
2. Applying creates an `Application` with status `applied` and the snapshot fields filled. It also creates the `CompanyShortlist` link.
3. Screening with a threshold and a minimum experience excludes the non-matching applicant, whatever their similarity.
4. A status change is visible to the student and writes an `ApplicationEvent`.
5. The export CSV has PRN as its first column and contains the applicant.
6. A recruiter at company B cannot read or change company A's opportunity or applications (404).
7. `?prns=` on applications names the misses.
8. Changing a student's programme after applying does not change the application's snapshot.

**Open questions**
- Can a student withdraw an application? (Recommendation: yes, as status `withdrawn`, never a delete.)
- Is one CV per application enough, or can a student attach a different resume per opportunity?

---

## Phase C — Certification Suggestions

**Goal.** Suggest certifications that close a student's skill gaps against open
opportunities, give the reason, take proof, and show verified completions on the
company-facing profile.

**Models** (`certifications/`)

| Model | Fields |
| --- | --- |
| `Certification` | UUID `id`, `name`, `provider`, `skill_tags` (slugs), `level`, `link`, `is_active` (admin-managed catalogue) |
| `StudentCertification` | UUID `id`, `profile` FK, `certification` FK, `status` (in_progress / completed), `proof` file (via `core/storage.py`, same boundary as resumes), `verified_by`, `verified_at` |

**Logic (rule-based, v1).** For each skill that open opportunities ask for and
the student lacks, count the opportunities asking for it (weighted toward the
student's department). Suggest the catalogue certifications that cover those
skills, ranked by count. Each suggestion carries a reason string that names the
skill and the count, e.g. "3 open opportunities in your department ask for AWS".
Recompute on read; no cache to invalidate.

**Endpoints.** `certifications/` (catalogue CRUD for admins, read for students),
`certifications/suggestions` (student), `me/certifications` (mark progress, upload
proof), `admin/certifications/<id>/verify`.

**Checkpoint C tests to write first**

1. With 3 open opportunities needing a skill the student lacks, the matching certification is suggested, and its reason names that skill and the count 3.
2. Adding the skill to the profile removes the suggestion. Closing the opportunities removes it too.
3. In progress → completed with proof → admin verifies → the certification shows in the company payload. An unverified one never does.
4. Proof files are served only through an authenticated endpoint (D25).

**Open question.** Does a verified certification feed back into Phase B ranking
as "certifications held"? The PRD says yes; confirm the weight.

---

## Phase D — Company Self-Service & Notifications

**Goal.** A company account, unaided by an admin, posts an opportunity, screens
its applicants, and shortlists one. The student is notified. Analytics reflect
the PRD's success metrics.

**Work**
- Company-scoped versions of the Phase B admin endpoints, gated by `company_recruiter:<company_uuid>` and checked against `opportunity.company`.
- A `notifications/` app (or a module in `core/`): a `Notification` model (UUID, recipient, kind, payload, `read_at`), an in-app list and mark-read, and email through Django's email backend (console in dev). Triggers:
  - a new opportunity that matches the student
  - a deadline within N days (a management command run on a schedule)
  - an application status change
- An analytics endpoint and page with:
  - applications per opportunity
  - profile completion rate
  - certification start and completion rates
  - applications per active student
  - admin time to shortlist, from `ApplicationEvent`

  These are the PRD's success metrics.

**Checkpoint D tests to write first**

1. A recruiter creates, edits and closes their own company's opportunity. Another company's recruiter gets a 404.
2. A recruiter screens and shortlists, and the student gets an in-app notification, plus an email in the outbox.
3. A channel other than in-app or email is rejected with a 422.
4. The deadline command notifies only students who are eligible and haven't applied, once.
5. Analytics counts match a hand-counted seeded set.

**Then the full comprehensive E2E**: the `agents.md` final checkpoint covering
every role, the security pass and the performance check. Extend
`backend/checkpoints/e2e_phase_0_3.py` into a new `e2e_full.py` rather than
starting again.

---

## Post-demo items (not phase-bound)

| Item | Why it waits | Where it's recorded |
| --- | --- | --- |
| **Admin MFA**: an emailed one-time code as the second factor | Deferred by the product owner until after the demo. The strict xfail flips when it lands | DECISIONS D23 |
| **Publishing to GitHub**: local history contains a real student's PRN in early commits, and the repo is public | Needs a decision: push a history-free snapshot, make the repo private, or rewrite history | `LEFTTODO.md` |
| **Browser E2E (Playwright)**: nothing drives the built app in a real browser | jsdom catches React errors but not layout or routing in a real browser | `TODO.md` |
| **Registrar confirmations**: PRN format (ID-01), the programme list (ID-05), whether R3 covers PG and PhD cohorts | One conversation each. The code reads them from config and `roster/reference.py`, so the answers are edits, not rewrites | IMPLEMENTATION_PLAN §11 |
| **Phase E API conventions**: RFC 9457 errors, `/api/v1/` paths, drf-spectacular schema checked in CI | Deferred by D2. New endpoints are shaped so the move is a rename | IMPLEMENTATION_PLAN §2 |
| **More sample transcripts**: 3–5 real-format samples and the scanned-document fallback | The parser is built against one real layout. A wrapped line in another sample could break the name and degree patterns | REQUIREMENTS-ADDENDUM R5 |
