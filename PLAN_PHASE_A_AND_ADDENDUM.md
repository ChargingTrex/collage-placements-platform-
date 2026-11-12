# Finish Phase A + build REQUIREMENTS-ADDENDUM R1–R5, outline Phases B–D

> **Execution plan for the current session**, approved 2026-10-07 and updated
> 2026-10-09 (PRN template = the transcript's format). It sits underneath
> [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), which is the overall
> phase/agent plan. This file is the step-by-step for finishing Phase A and
> building REQUIREMENTS-ADDENDUM R1–R5. **Status: not started.** The first
> attempt at step 1a changed nothing, because its scripts were written to a
> cleared `/tmp`.

## Context

Phase A (identity retrofit) is part-done: streams A-1, A-2, A-6 and the frontend half of A-5 are committed (`e270126`), and `backend/checkpoints/` stands at **45 pass / 16 fail**. The addendum's five features (admin profile view, career path, outcomes dashboard, onboarding form, transcript CGPA) are unbuilt. The user wants both finished now, Phases B–D outlined (not built) so the next session moves straight on, and has settled the open decisions:

- **Scope:** Phase A remainder + R1–R5. Phases B–D → written outline only.
- **Admin MFA:** deferred until after the demo (email OTP later). The one failing MFA test becomes a recorded, strict `xfail`.
- **Addendum decisions:** accept every stated recommendation — career path single-select + `also_attending_placements`; `placement` and `undecided` included; companies never see career path or transcript; onboarding is a dismissible prompt + banner (phone + career path required), not a hard gate; CGPA mismatch flagged for admin, roster CGPA stays authoritative; dashboard covers all cohorts, grouped by school, filterable by batch; resume/transcript views are audit-logged.
- **D11:** re-scope the migration test to assert the UUID migration *refuses loudly* on a populated DB.

Working rule kept from earlier sessions: **each checkbox gets a failing test before the code that ticks it**; commit per task; main agent executes (QA subagent stalled last time).

Out of scope, unchanged: the GitHub push (still waiting on the history-rewrite permission decision).

---

## Part 1 — Close Phase A (16 failing → 0 failing + 1 strict xfail)

### 1a. Synthetic PRNs everywhere (A-5 fixtures) — do first, everything else builds on it

**PRN template = the transcript's format** (decided 2026-10-09, corrected
2026-10-19). Nine digits: `YY` + `0200` + `NNN`, where **`YY` is the entry
year** (a PRN starting `24` = joined in 2024). A fixture PRN must agree with
its `batch` (graduating year): entry year = batch − 4 for these 4-year UG
fixtures, so batch 2026 → `22…`, 2027 → `23…`, 2025 → `21…`. Sequences sit in
the `9xx` range. The validator stays `^[0-9]{9}$` in shared config (D4).
**The full per-fixture mapping is in [`PLAN_CHECKLIST.md`](PLAN_CHECKLIST.md)
§1a, and it supersedes the table below**, which used `26` throughout and was
wrong.

| Role in fixtures | Old | Template PRN |
| --- | --- | --- |
| Demo roster students (11) | `PRN2022CS001` … `PRN2022ME010`, `PRN2021CS011` | `260200901` … `260200910`, `250200911` (former, ineligible) |
| Error-CSV rows | `PRN2022CS900/902–905` | `260200950`, `260200952`–`260200955` |
| Not-on-roster pairs | `PRN9999XX999`, `PRN0000XX000`, `PRN0000ZZ000` | `260200999`, `260200998`, `260200997` |
| Importer unit tests | `PRN1`, `PRN2` | `260200961`, `260200962` |
| Storage-path test | `PRN2021001` | `260200901` |
| Lower-case PRN tests | `prn2022cs001` | `" 260200901 "` (now tests trimming; digits have no case) |
| **Real student series** (scrub) | the supplied transcript's PRN and the four neighbours used in tests | `260200921/22/23/24/20` |
| Real-derived truncations | its 8-digit, 10-digit and trailing-letter variants | `26020092`, `2602009211`, `26020092X` (keep 8-digit / 10-digit / trailing-letter shapes for the reject tests) |
| Real name | the student name in `REQUIREMENTS-ADDENDUM.md` | `SAMPLE STUDENT` |

- Apply the demo-shape mapping to code, tests and fixtures. Leave it out of `*.md` docs, which describe the old invented shape on purpose, and out of the `TestPrnRegex` row that needs `PRN2022CS001` rejected.
- Apply the real-series scrub **everywhere at HEAD**, docs included. This changes the working tree only. Rewriting history is still the separate push decision.
- Keep `ABSENT_PRN = "999999999"` in `checkpoints/conftest.py`. It is valid nine digits that belong to nobody.
- Write the replacement scripts to the **session scratchpad**, not `/tmp` (the last attempt failed because `/tmp/pcp` had been cleared).
- Regenerate `backend/fixtures/roster_sample.csv` with template PRNs, real Sai schools (`school` column), real programme names in `department`, and `year_of_study`.
- Verify afterwards: a grep for the real series and name (pattern held in the session plan, deliberately not written here) finds nothing at HEAD, and every fixture PRN matches `^[0-9]{9}$`.

### 1b. A-3 — shared config + code list

- `config/settings.py`: `IDENTITY["PRN_REGEX"] = env("PRN_REGEX", r"^[0-9]{9}$")`.
- `roster/models.py`: replace hard-coded `PRN_VALIDATOR` with a validator that reads `settings.IDENTITY["PRN_REGEX"]` at call time.
- New `roster/reference.py`: the 8 schools (keys/names from the addendum) and programmes per school; `normalise_code()` (strip punctuation/case, same idea as `profiles.models.slugify_skill`) so `BTech`/`B.Tech` match; `school_for_programme()`.
- `roster/importers.py`: accept optional `school`, `year_of_study` columns. Unknown school/programme → **row stored as given, named in a new `unknown_codes` list in the response, `logger.warning`** — never remapped (matches `TestUnknownDepartmentCode`).

### 1c. A-1 follow-ups

- **UUID primary keys** on `FlaggedSignup`, `StudentProfile`, `ExperienceEntry`, `ProjectEntry`, `ProfileSkill`, `CompanyShortlist` (`TestNoHumanKeyCarriesAJoin`). Migrations reuse the refuse-on-populated-DB guard pattern from `accounts/migrations/0003_…`. Frontend entry ids `number` → `string` (`api/profiles.ts`, `ExperienceCard`, `ProjectsCard`).
- **Batch misses named:** a mixin in `core/filters.py` (e.g. `ReportUnmatchedPrnsMixin`) overriding `get_paginated_response` to add `unmatched_prns` — computed against the full filtered-but-not-`prns` queryset — applied to `roster.StudentViewSet`, `profiles.CompanyProfileViewSet`, `profiles.AdminProfileViewSet`. A hidden student's PRN reported as unmatched to a company is correct (indistinguishable from absent).
- **Human-key normalisation:** read the full `test_a_human_key_filter_value_is_upper_cased…` before coding; declare `admin_id` / `company_id` `HumanKeyFilter`s where the test expects them (reuse `core.filters.HumanKeyFilter`).

### 1d. A-4 (minus MFA) — identity access logging

- `AuditLog.Action.IDENTITY_ACCESSED` and `DOCUMENT_ACCESSED`. `AdminProfileViewSet.retrieve` and `CompanyProfileViewSet.retrieve` write a row naming the PRN; own-profile reads write nothing.

### 1e. Test-suite items

- **Key rotation:** write the test QA left (`TestSigningKeys::…second_published_key_pair…`): two generated pairs in `override_settings(IDENTITY={…"KEYS": {...}})` + `accounts.identity.reset_keyring()`, mint with each, both authenticate, both in `/api/auth/jwks`.
- **D11:** rewrite `TestMigrations::…populated_phase_3_database` to assert refusal, the reset path in the message, and untouched data. Mark D11 *confirmed* in `DECISIONS.md`.
- **MFA:** `TestAdminMfa::test_an_admin_token_without_mfa_is_refused…` → `pytest.mark.xfail(strict=True, reason="Deferred post-demo: email OTP second factor — DECISIONS D23")`.
- **E2E script:** commit `backend/checkpoints/e2e_phase_0_3.py` — the 30-check halfway E2E rebuilt against today's API (student_id paths, `roles[]`, `Company`), runnable against a live server (`TestExistingSuitesSurvive`).

### 1f. Reset-safe demo

- New `manage.py seed_demo --with-students` (or `seed_demo_students`): reproduces the four populated students (profiles, resumes, visibility spread, Acme shortlist-while-public, verification) so a reset no longer breaks the demo. Update `DEMO_LOGINS.md` with the new PRNs.

---

## Part 2 — REQUIREMENTS-ADDENDUM R1–R5 (Phase E)

Tests first: `backend/checkpoints/test_checkpoint_e.py`, one failing test per addendum checkbox, run and confirmed red before building.

### Data model — one migration in `profiles` (plus roster fields from 1b)

`StudentProfile` gains: `career_path` (9 choices), `career_path_detail`, `also_attending_placements`; `personal_email`, `onboarding_completed_at`, `onboarding_dismissed_at`; `transcript` (FileField), `transcript_filename`, `transcript_text`, `transcript_uploaded_at`, `transcript_prn`, `transcript_school`, `transcript_degree`, `parsed_cgpa`, `recomputed_cgpa`, `confirmed_cgpa`, `cgpa_matches_roster` (nullable), `cgpa_review_status` (`not_needed`/`open`/`resolved`). `core/storage.py`: `transcript_upload_path`, `validate_transcript` (PDF only).

### R2 — career path

- `ProfileSerializer` validation: `other` requires non-blank `career_path_detail`; detail cleared otherwise. Own + admin serializers expose it; **`CompanyProfileSerializer` does not**.
- `completion_detail()` gains `career_path` (blank/`undecided` = not done).
- Frontend `pages/student/CareerPathCard.tsx`: radio list with the one-line explanations (Business / Entrepreneurship / Family business distinctions), "Other" text field, "also attending placements" checkbox.

### R1 — admin profile & document view

- **Authenticated document endpoints** (replaces the unauthenticated `MEDIA_ROOT` resume URL — closes a TODO item): `GET /profiles/me/resume/file`, `/me/transcript/file`, `/admin/<student_id>/resume`, `/admin/<student_id>/transcript`, `/students/<student_id>/resume` (company; visibility-checked via `visible_to`; transcript **never** for companies). `FileResponse` with original filename; admin/company access writes `DOCUMENT_ACCESSED`.
- Frontend helper `openDocument(url)` (fetch with bearer → blob → new tab). Serializers return these API URLs instead of media URLs.
- New `pages/admin/ProfileDetailPage.tsx` at `/admin/profiles/:studentId`: roster facts, summary, links, skills, experience, projects, career path, onboarding status, resume + transcript buttons, verify/revoke, CGPA review panel (parsed vs recomputed vs roster, resolve button). List rows in `ProfilesPage.tsx` link to it; hidden profiles fully visible.

### R5 — transcript CGPA

- New `matching/transcripts.py` (separate from the resume path; reuses `matching.extraction.extract_text`): `parse_transcript()` → PRN, name, school, degree, total credits, `Cumulative GPA`, issue date, per-semester (credits, SGPA) handling `(contd.)` splits, and `recomputed_cgpa = Σ(c·s)/Σc` with an agreement flag.
- `POST /profiles/me/transcript`: validate PDF → parse → **PRN present and ≠ student's → 400, `TRANSCRIPT_PRN_MISMATCH` audit, file not stored** → store file + parsed values → compare with roster CGPA (tolerance 0.05) and printed vs recomputed (0.02) → any disagreement, or nothing parseable, sets `cgpa_review_status=open` + `CGPA_MISMATCH_FLAGGED` audit. Roster `cgpa` never written. `POST /me/confirm-cgpa` = manual entry / confirmation (stored as `confirmed_cgpa` only). `POST /admin/<id>/cgpa-review` resolves.
- Eligibility/company filters keep using `student__cgpa` (roster). A test asserts resume upload never touches any CGPA field, plus a source-level grep that `matching/extractors.py` has no CGPA parsing.
- `manage.py make_sample_transcripts`: synthetic PDFs in the real layout (reportlab, as `make_sample_resumes` does) — clean, `(contd.)` split, tampered (printed ≠ recomputed), wrong-PRN, image-only.
- Frontend `pages/student/TranscriptCard.tsx` (upload, parsed-value review, manual fallback, mismatch notice).

### R4 — onboarding

- `GET/POST /profiles/me/onboarding` (phone + career path required; personal email optional and ≠ college email; headline/summary optional; transcript via R5 endpoint) sets `onboarding_completed_at`; `POST /me/onboarding/dismiss`. Profile payload exposes `onboarding_completed`.
- Frontend `pages/student/OnboardingPage.tsx` at `/student/onboarding`: roster facts read-only, "Skip for now". `VerifyPage` sends new students there; `StudentHome` / `AppShell` show a banner until completed; never shown again once completed.
- `admin/stats` gains `onboarding_completed`.

### R3 — outcomes dashboard

- `GET /profiles/admin/outcomes?batch=` → paths, per-school counts, row/column totals, grand total, `also_attending_placements`, verified count. Base set = roster students **with an account**; no profile / blank / `undecided` all count as `undecided` so columns sum to the cohort. Blank school → "Unassigned" row.
- `GET /profiles/admin/outcomes/export?batch=` → CSV (separate action; `format` is reserved by DRF and allowed by `RejectUnknownQueryParams`).
- Frontend `pages/admin/OutcomesPage.tsx` at `/admin/outcomes`: schools × paths table with margins, batch filter, Export CSV; nav link + card on `AdminHome`.

---

## Part 3 — Phases B–D outline (document only)

New `NEXT_PHASES.md` (linked from `LEFTTODO.md`, `README.md`): per phase — goal, models, endpoints, UI screens, owner agent, the checkpoint tests to write first, carry-ins (`CompanyShortlist` on application; snapshot dept/programme/year on applications; opportunities owned by `Company`; in-app/email-only notifications), open questions. Plus post-demo items: admin email-OTP MFA (D23), the push/history decision, Playwright browser E2E.

## Part 4 — Docs

`DECISIONS.md` (D11 confirmed; D23 MFA deferred; D24 addendum recommendations accepted; D25 documents served only via authenticated endpoints — numbered D23–D25 because D15–D22 were taken by the resume-intelligence work), `LEFTTODO.md` rewritten to the new state, `TODO.md`, tick boxes in `REQUIREMENTS-ADDENDUM.md`, `SMOKE_TESTS.md` entries, `DEMO_LOGINS.md` (gitignored).

---

## Critical files

Backend: `config/settings.py`, `roster/{models,importers,reference,views}.py`, `core/{filters,models,storage}.py`, `accounts/models.py`, `profiles/{models,serializers,views,urls,filters}.py`, `matching/transcripts.py` (new), `core/management/commands/seed_demo.py`, `matching/management/commands/make_sample_transcripts.py` (new), `checkpoints/test_checkpoint_a.py`, `checkpoints/test_checkpoint_e.py` (new), `checkpoints/e2e_phase_0_3.py` (new).
Frontend: `api/profiles.ts`, `App.tsx`, `components/AppShell.tsx`, `pages/admin/{ProfilesPage,ProfileDetailPage,OutcomesPage,AdminHome}.tsx`, `pages/student/{CareerPathCard,TranscriptCard,OnboardingPage,ProfilePage,ExperienceCard,ProjectsCard,StudentHome}.tsx`, `pages/VerifyPage.tsx`, `src/test/*`.

Reuse: `core.filters.HumanKeyFilter/HumanKeyInFilter/RejectUnknownQueryParams`, `matching.extraction.extract_text`, `profiles.models.slugify_skill` pattern, `StudentProfile.objects.visible_to`, `core.models.AuditLog.record`, `accounts.identity.reset_keyring`, the refuse-on-populated migration guard in `accounts/migrations/0003_*`, `make_sample_resumes.write_pdf`, the parsed-vs-confirmed pattern in `StudentProfile.apply_parsed_resume`.

## Order of commits

1a fixtures/PRNs → 1b → 1c → 1d → 1e → 1f → write `test_checkpoint_e.py` (red) → model migration → R2 → R1 → R5 → R4 → R3 → Part 3 → Part 4.

## Verification

- `pytest checkpoints/ -q` → all Checkpoint A pass except 1 strict xfail (MFA); all Checkpoint E pass.
- Full backend suite on both similarity backends (`MATCHING_BACKEND=tfidf` too); `manage.py makemigrations --check`.
- Frontend: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` (with `PATH=/usr/local/bin:$PATH`).
- Fresh DB: `migrate && seed_demo --with-students`, start both servers, run `checkpoints/e2e_phase_0_3.py` and a new addendum E2E (onboarding → career path → transcript happy path / wrong-PRN refusal / tampered flag → admin detail opens resume & transcript with audit rows → outcomes table sums to cohort → CSV export → company cannot see career path or transcript).
- Browser walkthrough of the three logins in `DEMO_LOGINS.md`; server log shows no 5xx/tracebacks.
- The real-series grep (pattern in the session plan, not in the repo) returns nothing at HEAD.
