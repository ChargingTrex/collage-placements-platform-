# TODO

Open work and the bug record for the Placement Cell Portal.

**Resuming work? Start at [`LEFTTODO.md`](LEFTTODO.md)** — it has the current
state, the 34 failing checkpoint tests that define the rest of Phase A, and
what is blocked on whom. Decisions and their reasoning are in
[`DECISIONS.md`](DECISIONS.md). Phase status is in [`PROGRESS.md`](PROGRESS.md);
the run output behind every claim here is in [`SMOKE_TESTS.md`](SMOKE_TESTS.md).

**The six bugs found during Phases 0–3 are all fixed.** They are recorded at
the bottom with their regression tests, so nobody re-derives them. What is
genuinely outstanding is above.

---

## Open

### Blocking Phase 4

- [ ] **Applications must create the `CompanyShortlist` relationship.**
      A company can shortlist only a profile it can already see, so a student
      who sets visibility to "shortlisted only" before anyone has shortlisted
      them is unreachable by any *new* company. The application flow is the
      only legitimate route in. If Phase 4 creates applications without the
      shortlist link, a student in that state can still only be reached by
      going back to "all companies" first.
      Pinned by `profiles/tests/test_authorization.py::TestShortlisting::test_narrowing_to_shortlisted_keeps_the_companies_already_interested`.

      The student-side half of this is **done**: the profile reports
      `shortlisted_by_count`, the visibility control warns when that count is
      zero, and a single button returns the profile to "all companies". So
      nobody is silently trapped — but a new company still cannot initiate
      contact until applications exist.

### Before release

- [ ] **No headless browser drives the real UI.**
      The React suite runs in jsdom, which catches React errors and unhandled
      rejections, but nothing exercises the built app in a real browser. Add
      Playwright covering at least: signup → verify → profile build → resume
      upload, and the company search with visibility switched mid-run.
- [ ] **`docker compose up` has never been run end to end here.**
      The compose file, both Dockerfiles and the Postgres service are
      committed, and CI runs the same code against PostgreSQL 16 on every
      push, but the Phase 0 checkpoint was verified on the SQLite path. Run it
      from a clean clone once before trusting it.
- [ ] **`EXPOSE_OTP_IN_RESPONSE` must be off in any deployment.**
      It is tied to `DEBUG` and documented in `.env.example`, but it returns a
      live login code in an API response. Worth an explicit check in whatever
      deploy process gets built.

- [ ] **The frontend never refreshes the access token.**
      Access tokens last 15 minutes (shared spec §5.3), and `api/client.ts`
      has no refresh step, so any request after 15 quiet minutes, including
      opening a resume through `openDocument`, fails with 401 and the user
      signs in again. Add one retry through `/api/auth/refresh` on a 401,
      keeping the family-revocation rule (a reused refresh token kills the
      family).
- [ ] **The transcript parser knows one layout.**
      `matching/transcripts.py` was built from one real transcript and the
      synthetic ones in `checkpoints/transcript_fixtures.py`. It assumes
      `Name: … PRN: …` and `<Degree> Total Credits: … Cumulative GPA: …` each
      sit on one line. Get 3–5 more real samples (with permission, never
      committed) before trusting it beyond the demo. A transcript it cannot
      read is not lost: it opens a CGPA review and the student can type the
      value for an admin to check.

### Worth doing, not urgent

- [ ] **On the onboarding page the transcript upload sits below "Save and continue".**
      A student can submit the form before scrolling to it. It's optional and
      also on the profile page, so nothing is lost, but moving it above the
      button (or saying "optional, below" next to it) would get more uploads.

- [ ] **`year_of_study` is 4 for every row of `roster_sample.csv`.**
      Including batch 2025/2026 students who would have finished by October 2026.
      Harmless for the demo; worth a real value once the registrar's export
      has one.
- [ ] **`StudentProfile.transcript_text` is never filled.**
      `parse_transcript` returns facts, not the raw text, so the column stays
      empty. Either have the parser return the text too or drop the column.
- [ ] **Two seeded demo students carry a resume that names someone else.**
      `seed_demo --with-students` has five sample resumes for four students,
      so Rohan gets Kabir's. The resume-verification flags may show a name
      mismatch on him. Advisory only; add matching sample resumes if it
      distracts in a demo.
- [ ] **`CASES["wrong_prn"]` in `checkpoints/transcript_fixtures.py` lists
      printed/recomputed CGPA as `None`**, but the PDF it renders does print
      8.50. Nothing reads those two values for that case (the PRN check
      refuses first), so it only misleads a reader.

- [ ] **The resume verification flags ignore the transcript CGPA.**
      `profiles/verification.py` compares a resume's CGPA with the roster
      only (its transcript argument is passed `None`). Now that R5 stores a
      parsed transcript CGPA, feeding it in would let the admin flags compare
      all three. Resume-intelligence code, so coordinate before changing it.
- [ ] **Login costs ~1s.**
      Entirely Django's PBKDF2 hashing (870k iterations) doing its job — not a
      query problem, and the OTP path is the alternative. Revisit only if login
      volume during a placement drive makes it a bottleneck.
- [ ] **`profiles/admin/stats` loads every profile to compute completion.**
      `completion_percent` is a Python property, so the aggregate walks the
      table. Fine at one college's roster size; push the counts into the
      database if it gets slow.
- [ ] **Skill names are free text per profile.**
      Matching is on a slug, so spelling variants collapse, but there is no
      catalog. Phase 5's certification skill tags will want one — decide then
      whether to normalise `ProfileSkill` against it.
- [ ] **The spaCy backend serialises on a lock.**
      spaCy pipelines are not thread-safe, so `_content_vector` holds a lock
      per call. Bulk screening 10 resumes takes 324ms; if a drive screens
      hundreds at once, move scoring to a worker instead of widening the lock.

---

## Fixed

### 12. A privacy test failed when a timestamp contained "8.9"
`profiles/tests/test_resume_analysis.py::TestPrivacy` searched the whole JSON
body for the substring `"8.9"` (the resume's CGPA). A timestamp like
`…:48.946142` matched it about one run in ten. It now compares values, not
text.

### 11. The E2E census passed because of a resume's file name
`TestExistingSuitesSurvive` accepted any file named `*e2e*` as "the E2E
script is committed". A resume upload whose random hex name contained `e2e`
satisfied it on one machine and not on a clean clone. It now requires
`backend/checkpoints/e2e_phase_0_3.py`, which exists and passes 43/43 live.

### 10. Resumes were served unauthenticated from `MEDIA_ROOT`
Under `DEBUG` the `/media/` route served every upload, and paths are keyed on
PRN, so they were guessable. Removed. Documents are served only by the audited
API views, which check who is asking and log every admin or company open
(DECISIONS D25). Pinned by `core/tests/test_media_not_served.py`.

### 9. A shortlist belonged to a recruiter, not a company
`CompanyShortlist.company` pointed at `User`, so two recruiters at one company
held separate shortlists and a "shortlisted only" student was visible to one
and 404 for the other. Fixed with the `Company` entity (A-6). Pinned by
`checkpoints/test_checkpoint_a.py::TestCompanyScope`.

### 8. The UUID migration would have corrupted a populated database
Confirmed approach (D11): it refuses loudly and names the reset path. Pinned by
`TestMigrations::test_the_uuid_migration_refuses_loudly_on_a_populated_phase_3_database`.

Each was found by a smoke test or unit test actually being run, not by reading
code. Listed so the reasoning is not lost.

### 7. An undeclared query parameter returned the whole table

`?prn=220200921` against a three-row roster returned all three — and so did
`?prn=999999999` for a PRN belonging to nobody. django-filter silently ignores
parameters it has not declared, so a reconciliation script reading `count > 0`
as "found" matched the wrong student, for a student who was not there. It
failed open, silently, and the output looked plausible.

Fixed in `core/filters.py` (Phase A, stream A-1): `RejectUnknownQueryParams` is
installed globally ahead of the other filter backends, `prn`/`prns` are
declared on the roster and profile endpoints, and filter input is trimmed and
upper-cased on the same path as write input.

Measured after the fix: `?prn=220200921` → 1 row, `?prn=999999999` → 0 rows,
`?prns=a,b` → 2 rows, `?prn=" 220200921 "` → 1 row, `?pm=…` → HTTP 400.
Regression: `checkpoints/test_checkpoint_a.py::TestPrnFilterFailsOpen`.

### 1. The flagged-signup queue was always empty

`register_student` was wrapped in `transaction.atomic`, so raising the
rejection rolled back the `FlaggedSignup` and audit rows it had just written —
losing exactly the record the PRD asks to keep.

Fixed in `accounts/signup.py` (Phase 1) by removing the decorator; each step
there is a single write, so there is no partial state to protect.
Regression: `accounts/tests/test_signup.py::TestRosterMatching::test_repeat_attempts_collapse_into_one_flag_with_a_counter`.

### 2. Half the API answered 301

The DRF router minted trailing-slash URLs (`/api/roster/flagged/`) while every
hand-written route is slashless. A GET survived the redirect; a POST with a
body would not have.

Fixed in `roster/urls.py` and `profiles/urls.py` (Phase 1) with
`DefaultRouter(trailing_slash=False)`.

### 3. `b\.?e\.?` matched the English word "be"

The prototype's pattern ran case-insensitively, so any resume containing
ordinary prose was recorded as holding a bachelor's degree.

Fixed in `matching/extractors.py` (Phase 2): bare abbreviations are matched
case-sensitively, and `B.E.` requires its trailing dot.
Regression: `matching/tests/test_extractors.py::TestEducation::test_the_word_be_does_not_count_as_a_bachelors_degree`.

### 4. `m\.?s\.?` matched "MS Office" and "MS SQL"

A skills list was enough to claim a master's degree.

Fixed in `matching/extractors.py` (Phase 2) with a negative lookahead over the
common Microsoft product names.
Regression: `matching/tests/test_extractors.py::TestEducation::test_microsoft_products_do_not_count_as_a_masters_degree`.

### 5. Experience took the largest number before "years" anywhere in the document

So "4 year full-time degree" outranked "2 years experience" on the same resume.

Fixed in `matching/extractors.py` (Phase 2): a duration counts as an experience
claim only when it sits within three words of "experience" with no sentence
break between them; the whole-document maximum is the fallback.
Regression: `matching/tests/test_extractors.py::TestExperience::test_experience_beats_an_unrelated_larger_number`.

### 6. The similarity threshold had no useful range

Averaging spaCy vectors over every token let stopwords dominate: the entire
reference set scored between 0.909 and 0.971, so the PRD's adjustable
threshold had nothing to adjust.

Fixed in `matching/backends.py` (Phase 2) by averaging over content words only,
which widened the spread to 0.801–0.964 on the same set. The two backends still
do not share a scale, so each carries its own `suggested_threshold` rather than
sharing a hardcoded default.
Regression: `matching/tests/test_engine.py::TestThreshold::test_the_engine_default_separates_relevant_from_irrelevant`.

---

## Now in scope — see [`LEFTTODO.md`](LEFTTODO.md)

Phases 4–6 of [`agents.md`](agents.md) were out of scope for the prototype and
are now scheduled, after the identity retrofit completes.

- [x] **Phase A** — identity & auth retrofit · *Checkpoint A green except admin MFA, deferred by D23*
- [x] **R1–R5** of the requirements addendum · *Checkpoint E 74/74*
- [ ] Phase B — Opportunities Board · outlined in [`NEXT_PHASES.md`](NEXT_PHASES.md)
- [ ] Phase C — Certification Suggestions · outlined
- [ ] Phase D — Company Self-Service & Notifications · outlined
- [ ] Phase E remainder — the deferred API conventions (RFC 9457, `/api/v1`, schema in CI)
