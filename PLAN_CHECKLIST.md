# Phase A + Addendum: Implementation Checklist

Tracks [`PLAN_PHASE_A_AND_ADDENDUM.md`](PLAN_PHASE_A_AND_ADDENDUM.md). One line per deliverable.

**Who may tick what:**

- An implementer (Sonnet agent) marks an item `[~]` (done, unverified) and names the files it changed.
- Only the Opus verifier turns `[~]` into `[x]`, after running the tests and reading the code against the plan.
- A verifier that finds a problem marks the item `[!]` and adds a note under **Findings**.
- Opus (the orchestrator) commits only items marked `[x]`.

Legend: `[ ]` not started · `[~]` implemented, awaiting verification · `[x]` verified · `[!]` verification failed

## Progress

| Step | Status | Commits | Verified |
| --- | --- | --- | --- |
| 1a Synthetic PRNs (template `YY0200NNN`, `YY` = entry year) | 8 of 8 verified (two `[!]` fixed in `82190d6`, confirmed by the second verifier) | `3a267d4`, `8ad07c6` | 2026-10-20 |
| 1b Shared PRN regex + school/programme code list | verified (9 of 9; unapproved warning confirmed not built) | `bc308be`, `2792051` | 2026-10-20 |
| 1c UUID keys, batch misses, human-key filters | verified (5 of 5) | `83f512e` | 2026-10-20 |
| 1d Identity access logging | verified (3 of 3) | `83f512e` | 2026-10-20 |
| 1e Test-suite items (rotation, D11, MFA xfail, E2E script) | verified (5 of 5) | `6f8f82c`, `2750f59`, `82190d6` | 2026-10-20 |
| 1f Reset-safe demo seed | verified (2 of 2) | `1e078db` | 2026-10-20 |
| E0 Checkpoint E tests written red | verified (74 red) | `97d2c37`, `72725d4` | 2026-10-20 |
| E1 Data model migration | verified (2 of 2) | `58023cf` | 2026-10-20 |
| R2 Career path | verified (4 of 4) | `5975205`, `2e89126`, `43450db` | 2026-10-20 |
| R1 Admin profile + document view | verified (5 of 5) | `5975205`, `bfadb6a`, `b7d9b7b` | 2026-10-20 |
| R5 Transcript CGPA | verified (8 of 8) | `aa67190`, `5975205`, `b0cda69` | 2026-10-20 |
| R4 Onboarding | verified (3 of 3; addendum gap closed in `57636dc`) | `5975205`, `9232d78` | 2026-10-20 |
| R3 Outcomes dashboard | verified (3 of 3) | `5975205`, `664e5fc` | 2026-10-20 |
| P3 Phases B–D outline (`NEXT_PHASES.md`) | verified | `81ae1c3` | 2026-10-20 |
| P4 Docs | `[x]` re-checked at `f3b0f1e`: `DECISIONS.md` has one heading each for D1–D25; every `D15`–`D25` ref in the repo points at the decision its sentence means (HANDOFF §2 and the plan's xfail line now say D23/D24/D25) | `6f8f82c`, `58cd2c2`, `350d8e7` | 2026-10-20 |
| Final verification gate | 5 of 5 verified (no browser walkthrough) | at `58cd2c2` | 2026-10-20 |

**Checkpoint A at last count:** 60 pass + 1 strict xfail (MFA, D23) of 61 (2026-10-20, verifier, HEAD `57636dc`). **Checkpoint E:** 75 / 75 pass (74 + the company-completion test). Evidence: `pytest checkpoints -q -p no:cacheprovider -o addopts="" -rfxX` → `135 passed, 1 xfailed in 201.34s`. Previous: `134 passed, 1 xfailed in 297.57s` at `58cd2c2`. Earlier count: 51 pass / 10 fail at `72725d4` (after 1a + 1b), with E 74/74 red.

---

## Before any more work: two blockers

- [x] **Another session is committing to `main` in this same folder** — it finished its final gate 2026-10-19 23:46; work continues on `main`, staging explicit paths only. Original note: (resume intelligence: `ac827c2` … `9fe0c10`). Two sessions sharing one working tree can sweep each other's half-done files into commits or break each other's test runs. A worktree on branch `phase-a-addendum` exists at `../collage-placements-phase-a` (clean, at `9fe0c10`). Moving the 1a edits into it failed (empty patch), so **they are still uncommitted in this folder's working tree**. Decide whether to continue in the worktree or here.
- [x] **R5 overlaps the other plan** (resolved as below). `RESUME_INTELLIGENCE_PLAN.md` reads CGPA from resumes for verification (never stored or used for eligibility). So R5 checks behaviour ("a resume upload never writes a CGPA field") instead of banning CGPA parsing in `matching/extractors.py`.

---

## 1a: Synthetic PRNs

### The PRN format

**The first two digits are the student's entry year.** A PRN starting `24` belongs to a student who joined in 2024. Layout: `YY` (entry year) + `0200` + `NNN` (sequence), nine digits in total.

So a fixture PRN has to agree with the student's `batch` (graduating year): **entry year = batch − programme length**. All fixtures are 4-year UG, so entry year = batch − 4.

| Batch (graduates) | Entry year | PRN prefix |
| --- | --- | --- |
| 2025 | 2021 | `21` |
| 2026 | 2022 | `22` |
| 2027 | 2023 | `23` |

Synthetic PRNs use sequences in the `9xx` range, away from real low-numbered sequences. Never write the real transcript's PRN into a repo file.

### [!] What the first attempt got wrong

The Sonnet agent stopped partway on a network error (ENOTFOUND). Its edits are in the working tree, 25 files, uncommitted. They also used `26` (entry year 2026) for every student, including batch-2026 students who joined in 2022. Those edits need remapping before anything else.

| Fixture | Batch | Current (wrong) | Correct |
| --- | --- | --- | --- |
| Demo roster: Aarav, Diya, Rohan, Sana, Kabir, Vihaan, Arjun, Ishita | 2026 | `260200901`–`905`, `907`, `909`, `910` | `220200901`–`905`, `907`, `909`, `910` |
| Demo roster: Ananya, Meera | 2027 | `260200906`, `260200908` | `230200906`, `230200908` |
| Demo roster: Farhan (former, ineligible) | 2025 | `250200911` | `210200911` |
| Error-CSV rows | 2026 | `260200950`, `952`–`955` | `220200950`, `952`–`955` |
| Not-on-roster pairs | — | `260200999`, `998`, `997` | `220200999`, `998`, `997` |
| Importer unit tests | 2026 | `260200961`, `962` | `220200961`, `962` |
| Checkpoint students Anaya, Kabir Rao (replace the real series) | 2026 | `260200921`, `260200922` | `220200921`, `220200922` |
| Checkpoint students Meera Iyer, Luna Pillai | 2027 | `260200923`, `260200924` | `230200923`, `230200924` |
| Batch-cap test range base | — | `260200920` | `220200920` |
| Reject-test variants (8 digits, 10 digits, trailing letter) | — | `26020092`, `2602009211`, `26020092X` | `22020092`, `2202009211`, `22020092X` |

`ABSENT_PRN = "999999999"` stays as is: valid shape, belongs to nobody.

- [x] PRN prefixes remapped to entry year = batch − 4, per the table above (orchestrator fix-up, 170 replacements in 25 files) — verified: every PRN in `roster_sample.csv` (11 rows) is `^[0-9]{9}$` with prefix = batch − 4; `roster_with_errors.csv` likewise except its two deliberately bad rows (blank PRN, batch "next year")
- [x] Real student's PRN series and name removed at HEAD, docs included — verified: the real-series grep (pattern in the session plan) → 0 hits; the name tokens removed by `3a267d4`/`8ad07c6` → 0 hits at HEAD (the `test_extractors.py` occurrence went in `8ad07c6`)
- [x] Invented `PRN2022…` PRNs replaced in code, tests and fixtures (`matching/samples.py` deliberately left alone, owned by the other session) — the three leftover files and `matching/samples.py` remapped in `82190d6`; second verifier confirmed only deliberate reject cases remain
- [x] Case-insensitivity tests rewritten to test trimming — `accounts/tests/test_signup.py:36`, `roster/tests/test_importers.py:37`
- [x] Backend suite green — verifier run on a `git archive 72725d4` snapshot: `938 passed, 1 skipped in 475.15s`; `makemigrations --check --dry-run` → `No changes detected`
- [x] Checkpoint suite: 15 known failures, all in 1b–1e areas; `TestExistingSuitesSurvive` now passes because the other session committed `*e2e*` files, not ours — that claim was false (an untracked resume PDF's random name contained "e2e"); the census now requires the committed `e2e_phase_0_3.py` (`82190d6`, `2750f59`)
- [x] Frontend tests + typecheck green (91/91) — verifier, snapshot `72725d4`: `Tests 91 passed (91)`, `tsc` exit 0
- [x] `roster_sample.csv` gets `school` + real programmes (done in 1b, `bc308be`)

## 1b: Shared config + code list

- [x] `IDENTITY["PRN_REGEX"]` = `^[0-9]{9}$` in `config/settings.py` (`settings.py:323`, env-overridable)
- [x] `roster.models.PRN_VALIDATOR` reads it at call time — `PrnValidator` uses `re.fullmatch(settings.IDENTITY["PRN_REGEX"], …)`; verifier: `"220200921\n"` rejected, `override_settings` takes effect and reverts without reload
- [x] `roster/reference.py`: 8 schools, programmes per school, `normalise_code()`, `school_for_programme()`
- [x] Importer accepts optional `school`, `year_of_study`
- [x] Unknown school/programme stored as given, named in `unknown_codes`, logged, never remapped
- [x] `prn_entry_year(prn)` helper: the first two digits as a year (`22` → 2022) — used only by its own test
- [ ] **Proposed, NOT approved — do not build:** the importer warns, without rejecting, when a PRN's entry year doesn't fit the batch (batch − entry year outside 2–6, which covers PG through 5-year programmes). The registrar's data still wins; the warning only surfaces likely typos. *(Verifier: confirmed not built; `roster/importers.py` has no entry-year check and does not import `prn_entry_year`.)*
- [x] `roster_sample.csv` regenerated with schools + real programmes
- [x] Checkpoint: `TestPrnRegex` (5), `TestUnknownDepartmentCode` (1) pass — snapshot `72725d4` Checkpoint A: `10 failed, 51 passed`, none of them in these classes
- [x] `FlaggedSignup` UUID pk + refuse-on-populated guard in `roster/migrations/0004_*` (pulled forward from 1c) — verifier: scratch DB at 0003 with one flagged row → `migrate roster 0004` raises "Refusing to migrate…" naming the reset path, row untouched, 0004 not recorded

## 1c: A-1 follow-ups

- [x] UUID pks on `FlaggedSignup`, `StudentProfile`, `ExperienceEntry`, `ProjectEntry`, `ProfileSkill`, `CompanyShortlist`, with the refuse-on-populated guard — `profiles/0005` (also `ResumeAnalysis`) + `roster/0004`; verifier: scratch DB at `profiles 0004` with one profile row → `migrate profiles` exits 1 with "Refusing to migrate…" naming `rm`/`migrate`/`seed_demo`, row id still `1`, 0005 not recorded
- [x] Frontend entry ids `number` → `string` — `api/profiles.ts` (experience, project, skill, shortlist ids), `ExperienceCard`, `ProjectsCard`. *Residual, outside this item's scope: `api/roster.ts` still types `FlaggedSignup.id` and `RosterStudent.id` as `number`, and `api/auth.ts` `User.id`, though the API sends UUID strings (see Findings)*
- [x] `?prns=` responses add `unmatched_prns` (roster, company and admin lists) — `core.filters.ReportUnmatchedPrnsMixin` on all three viewsets; `core/tests/test_unmatched_prns.py`
- [x] Human-key filter normalised. Retargeted to `admin-profile-list?verified_by=…` (`StudentProfileFilter.verified_by = HumanKeyFilter("verified_by__admin_id")`); the test now asserts 200 and the exact verified row, with a comment saying why it moved
- [x] Checkpoint: `TestNoHumanKeyCarriesAJoin` (1), `TestPrnFilterFailsOpen` (3), `TestFilterInputNormalisation` (1) pass — inside the checkpoint run `134 passed, 1 xfailed`

## 1d: Identity access logging

- [x] `AuditLog.Action.IDENTITY_ACCESSED`, `DOCUMENT_ACCESSED` (`core/models.py`, `core/migrations/0004`)
- [x] Admin and company profile reads write a row naming the PRN; own-profile reads write nothing — `LogIdentityReadMixin.retrieve` (logs after `get_object`, so a hidden-profile 404 is unlogged); `profiles/tests/test_audit_access.py` (5). Live (verifier, scratch DB): 4 admin detail reads → 4 `identity_accessed`; the student's own profile and own transcript reads → 0 rows
- [x] Checkpoint: `TestIdentityAccessLogging` passes

## 1e: Test-suite items

- [x] Key-rotation test written (two key pairs, both mint, both verify, both in JWKS) — two `_generate_keypair()` pairs under `override_settings(IDENTITY={…KEYS, ACTIVE_KID})` + `reset_keyring()`; asserts each token's `kid`, both 200 on `my-profile` mid-rotation, JWKS publishes exactly both kids; resets the keyring in `finally`
- [x] `TestMigrations` re-scoped to "refuses loudly, names reset path, data untouched"; D11 marked confirmed — asserts non-zero exit, "Refusing to migrate", `manage.py migrate` + `seed_demo` in the message, rows still there with integer ids; `DECISIONS.md` D11 "Confirmed 2026-10-20"
- [x] MFA refusal test → `xfail(strict=True)` citing D23 (numbered after the resume-intelligence D15–D22) — checkpoint run shows exactly 1 strict XFAIL
- [x] `backend/checkpoints/e2e_phase_0_3.py` committed, runnable against a live server — tracked; verifier ran it against a fresh scratch DB (`migrate` + `seed_demo --with-students`, runserver :8770, `EXPOSE_OTP_IN_RESPONSE=1`, `OTP_THROTTLE_RATE=1000/hour`): `43/43 checks passed`, exit 0, server log 0 5xx / 0 tracebacks. `TestExistingSuitesSurvive` now accepts only four exact paths (this file is the only one that exists), no `*e2e*` glob
- [x] Checkpoint A: all pass except 1 strict xfail — 61 collected: 60 pass + 1 xfail

## 1f: Reset-safe demo

- [x] `seed_demo --with-students` reproduces the four populated students — `core/tests/test_seed_demo.py` (5: default seeds no students; four complete students who can log in; idempotent; visibility all/all/shortlisted/hidden; Acme sees 3, Nimbus 2). Verifier: seeded a fresh scratch DB twice, both exit 0, second run "0 created … 11 unchanged"
- [x] `DEMO_LOGINS.md` updated to template PRNs (gitignored; checked locally: `22020090x`/`23020090x` only)

## E0: Checkpoint E tests (written first, must fail)

- [x] `backend/checkpoints/test_checkpoint_e.py`, one test per R1–R5 checkbox, run and red — snapshot `72725d4`: 74 collected, 0 collection errors, `74 failed in 111.41s`; every failure is "not built yet" / missing URL name / missing field, none incidental

## E1: Data model

- [x] `StudentProfile` career, onboarding and transcript fields; `cgpa_review_status` — `profiles/0006_transcript_career_onboarding`; `makemigrations --check --dry-run` → `No changes detected`. *Minor: `transcript_text` is never filled (already in `TODO.md`)*
- [x] `core/storage.py`: `transcript_upload_path` (`transcripts/<prn>/…`, separate from `resumes/`), `validate_transcript` (PDF only) — live: a `.docx` upload → 400

## R2: Career path

- [x] Field + `other` requires detail; detail cleared otherwise — `check_career_path()` shared by `OwnProfileSerializer.validate` and `OnboardingSerializer`; E tests `test_other_with_blank_detail_is_rejected`, `test_leaving_other_clears_the_detail`
- [x] Own + admin serializers expose it; company serializer does not — `CompanyProfileSerializer.Meta.fields` read: no `career_path*`, `personal_email`, `transcript*` or `*_cgpa`; live: company detail and list carry none of those keys
- [x] Counts towards completion (blank/undecided = not done) — `completion_detail()["career_path"]`
- [x] `CareerPathCard.tsx` with one-line explanations, Other text, also-attending checkbox — `student-career-path.test.tsx`

## R1: Admin profile + documents

- [x] Authenticated document endpoints (own, admin, company-resume-only); transcript never for companies — every view resolves the profile first (own: `IsStudent` + own profile; admin: `IsPlacementAdmin` + `get_object`; company: `get_object` over `visible_to`) and only then opens the file; company `transcript` action raises 404 unconditionally. Live: company → own/admin routes 403, hidden student's resume 404, transcript 404
- [x] `DOCUMENT_ACCESSED` audit on admin/company opens — `audited_document()`; live: admin resume + transcript + Acme resume → 3 rows with `document` set; student's own open → none
- [x] `openDocument()` frontend helper; serializers return API URLs, not media URLs — `api/documents.ts` (bearer fetch → blob → tab); own/admin/company `resume_url`/`transcript_url` are `reverse(...)` routes; live: `/api/profiles/me/transcript/file`, `/api/profiles/students/<id>/resume`. `/media/` no longer routed even in DEBUG (`config/urls.py`; `core/tests/test_media_not_served.py`, 2); live: stored transcript path → 404 under `/media/` and `/`
- [x] `ProfileDetailPage.tsx` at `/admin/profiles/:studentId`; list rows link to it; hidden profiles fully visible — `admin-profile-detail.test.tsx`; live: admin GET of the hidden demo student → 200
- [x] Verify/revoke and CGPA review panel on the detail page — panel shows printed / recomputed / roster / confirmed and a resolve button; resolve endpoint checked live: 200, `resolved`, +1 `cgpa_review_resolved` row, `{"status":"open"}` → 400

## R5: Transcript CGPA

- [x] `matching/transcripts.py` (separate from the resume path): PRN, school, degree, credits, Cumulative GPA, semesters incl. `(contd.)`, recomputed CGPA — `matching/tests/test_transcripts.py`; not imported by `engine.py`/`extractors.py`
- [x] Upload: wrong PRN → 400 + audit, file not stored — the PRN check returns before `profile.transcript.save()`; live: 400 `prn_mismatch`, `MEDIA_ROOT/transcripts` file count 0 → 0, `transcript_url` still null, 1 `transcript_prn_mismatch` row
- [x] Mismatch (roster 0.05 / recompute 0.02) or unparseable → `cgpa_review_status=open` + audit — live: tampered → printed 9.40 / recomputed 8.50 / `open`; `cgpa_mismatch_flagged` written
- [x] Roster CGPA never written; eligibility filters still use it — code read: the only write to `Student.cgpa` outside tests is `roster/importers.py:251` (CSV import); transcript and resume paths only compare. `cgpa_min`/`cgpa_max` filter on `student__cgpa`. Live: roster 8.72 before and after transcript, confirm-CGPA and resume uploads
- [x] Confirm-CGPA (manual fallback) and admin resolve endpoints — live: `8.40` → 200, stored as `confirmed_cgpa` only; `11` → 400; a new transcript resets `confirmed_cgpa`
- [x] A resume upload never writes a CGPA field (behavioural test) — E `test_resume_upload_never_sets_a_cgpa_field`, `…leaves_transcript_cgpa_untouched`; live: every `*_cgpa` key identical before and after a resume upload
- [x] `make_sample_transcripts`: clean, `(contd.)`, tampered, wrong-PRN, image-only (+ roster-mismatch) — six PDFs in `backend/fixtures/transcripts/`
- [x] `TranscriptCard.tsx` — `student-transcript.test.tsx`; PRN-mismatch notice, review notice, confirm form when flagged or unread

## R4: Onboarding

- [x] `GET/POST /me/onboarding` (phone + career path required; personal email ≠ college email) and `/dismiss` — `TestR4Onboarding` (8)
- [x] `OnboardingPage.tsx`; VerifyPage routes new students there; banner until done; never re-shown once done — `student-onboarding.test.tsx`. *Gap vs addendum: the form has no transcript upload ("upload it from your profile"); addendum R4 box 2 left unticked, see Findings. Closed in `57636dc`: `TranscriptCard` on the onboarding page, outside the form; box ticked by the third verifier*
- [x] `admin/stats` counts onboarding completed — shown on `AdminHome`

## R3: Outcomes dashboard

- [x] `/admin/outcomes?batch=`: per-school × path counts, margins, columns sum to the cohort (undecided included), Unassigned row — `build_outcomes()` counts roster students with a student account; live: totals and row totals both sum to `grand_total` (14), every row carries every path key, `?bogus=1` → 400
- [x] `/admin/outcomes/export` CSV — live: header `school,placement,…,total`, final `total,…` row; company → 403
- [x] `OutcomesPage.tsx` with batch filter, export, nav link — `admin-outcomes.test.tsx`; `AppShell` nav + `AdminHome` card

## P3 / P4

- [x] `NEXT_PHASES.md` (Phases B–D outline + post-demo items) — per phase: goal, models, endpoints, UI, lead agent, checkpoint tests to write first, open questions; carry-ins section; post-demo table (MFA, publishing/history, Playwright). Linked from `README.md:79` and `LEFTTODO.md:56`
- [x] `DECISIONS.md` D11 confirmed, D23, D24, D25 (renumbered from a duplicate D20–D22 and moved beside the other decisions; the open-questions rows D24 answers removed); `LEFTTODO.md`, `TODO.md`, addendum boxes, `SMOKE_TESTS.md` — re-verified at `57636dc`: `DECISIONS.md` has exactly one each of D1–D25, D23–D25 under "The decisions", the four answered open-question rows gone; `CONTEXT.md`/`PROGRESS.md` D18–D22 refs correctly mean the resume-intelligence set. **Fails on one point:** `docs/HANDOFF.md:57,58,65` ("Key decisions and constraints") still cite MFA as D15, the addendum as D16 and documents as D17, which are now other decisions; `PLAN_PHASE_A_AND_ADDENDUM.md:80` still quotes the MFA xfail reason as "DECISIONS D15" — _Fixed in `f3b0f1e`, re-verified 2026-10-20: `docs/HANDOFF.md:57,58,65` now cite D23 (MFA), D24 (addendum) and D25 (documents); `PLAN_PHASE_A_AND_ADDENDUM.md:80` and `test_checkpoint_a.py:978` cite D23; the only D15–D17 mentions left are the two renumbering notes and the resume-intelligence refs, which are correct._

## Final verification gate

- [x] Checkpoint A: all pass except 1 strict xfail; Checkpoint E: all pass — `pytest checkpoints -q -p no:cacheprovider -o addopts="" -rfxX` at `58cd2c2`: `134 passed, 1 xfailed in 297.57s` (A 61 collected = 60 + the MFA xfail; E 74/74)
- [x] Backend suite green on spaCy and TF-IDF; `makemigrations --check` clean — default: `980 passed, 1 skipped in 518.93s`; `MATCHING_BACKEND=tfidf`: `980 passed, 1 skipped in 505.06s`; `makemigrations --check --dry-run` → `No changes detected`
- [x] Frontend test, typecheck, lint, build green — `Tests 112 passed (112)` (15 files); `tsc --noEmit` exit 0; `oxlint` exit 0 (6 warnings, 0 errors); `vite build` exit 0
- [x] Fresh DB + `seed_demo --with-students` + both E2E scripts against live servers; no 5xx in logs — verifier's scratch DB on :8770: `e2e_phase_0_3.py` `43/43 checks passed`; the verifier's own R1/R5 walk (the orchestrator's addendum script was not committed) `39/39 checks passed`; server log 0 5xx, 0 tracebacks. The browser walkthrough of `DEMO_LOGINS.md` was not done by the verifier
- [x] Real-series grep empty at HEAD (pattern in the session plan) — `git grep` exit 1, no hits

---

## Findings

Verifier notes go here: item, what failed, evidence.

**2026-10-20, verifier (1a, 1b, E0).** All runs used a `git archive 72725d4` snapshot in the session scratchpad, because `83f512e` (1c/1d) landed in this working tree mid-verification.

- **1a `[!]` invented PRNs.** `git grep -nE "PRN20[0-9]{2}"` outside `*.md` still finds the old shape in `profiles/tests/test_matching_api.py`, `profiles/tests/test_role_categories.py` and `profiles/tests/test_verification_flags.py` (all last touched by the other session, `6969b0c`), on top of the excused `matching/samples.py`. The tests pass because `make_student` skips `full_clean`. Fix: remap them, or widen the item's exclusion to name these files.
- **1a `[!]` checkpoint claim.** `TestExistingSuitesSurvive` does not pass because of committed `*e2e*` files: `git ls-files | grep -i e2e` is empty. In this folder it passes only because `REPO_ROOT.rglob("*e2e*")` matches the gitignored `backend/media/resumes/…/0c3c5e2e….pdf`, whose random hex name contains "e2e". On a clean checkout it fails. The real fix is 1e (commit `e2e_phase_0_3.py`). The test should also stop accepting any `*e2e*` file anywhere.
- **E0 notes (not failures).** `test_admin_resolves_a_cgpa_review` checks only `AuditLog.objects.count() > before`, not the contract's `cgpa_review_resolved` action. The onboarding GET test checks 3 of the 7 `student` keys. `uploaded_resume` writes to the system temp dir via `tempfile.mkdtemp()` and never cleans up.
- **1b note.** `2792051` (`fullmatch`) has no regression test for the trailing-newline case. The verifier checked it by hand: `"220200921\n"` is rejected.

**2026-10-20, verifier (1c–1f, E1, R1–R5, P3, P4, final gate).** Run on the working tree at HEAD `58cd2c2`; the only local change is this file. Live checks used a scratch SQLite DB and `MEDIA_ROOT` in the session scratchpad, runserver on :8770.

- **P4 `[!]` duplicate decision numbers.** `DECISIONS.md` has two D20s, two D21s and two D22s. `bf7d081` (resume intelligence) already took D15–D22; Phase A then added its own D20–D22, assuming only D15–D19 were taken. The plan's note ("renumbered because D15–D19 were taken") is therefore wrong. Each ref is now ambiguous: `CONTEXT.md:125-126` and `PROGRESS.md:193` mean the first set, while the MFA xfail reason, `config/urls.py`, `core/tests/test_media_not_served.py`, `NEXT_PHASES.md`, `LEFTTODO.md`, `TODO.md` and `docs/HANDOFF.md` mean the second. Fix: renumber Phase A's three to D23–D25 and update those refs. The new entries also sit under "Open questions that will become decisions", whose table still lists the career-path, onboarding-gate, transcript-visibility and CGPA-mismatch questions that the second D21 settles.
- **Doc numbers reproduce.** Checkpoint A 60 + 1 xfail, E 74/74, E2E 43/43, frontend 112/112: all re-measured (see the final gate). The `LEFTTODO.md` "R1–R5 walk 25/25" is a composite. `SMOKE_TESTS.md` says the first pass was 23/25 and only the four resume checks were re-run after a restart, yet the block it shows has all 25 as PASS. The verifier's independent walk is 39/39.
- **1a `[!]` items, resolved at HEAD (boxes left as the first pass set them).** `82190d6` remapped the invented PRNs; `git grep -nE "PRN20[0-9]{2}" -- ':!*.md'` now finds only deliberate rejection cases (`test_checkpoint_a.py:784`, `roster/tests/test_prn_validator.py:23`) and a comment. The `*e2e*` census glob is gone. Both can be flipped to `[x]`.
- **Addendum boxes left unticked (3 of 36):**
  - R1 "resume opens … with the original filename". The API sends `Content-Disposition: inline; filename="…"`, but `openDocument()` opens a `blob:` URL, so the browser shows and saves a random name. Fix: read the filename from the header and use `downloadFile`, or set `a.download`.
  - R4 "the form collects … and the transcript upload (R5)". `OnboardingPage.tsx` has no transcript field; it tells the student to upload from the profile.
  - R5 "CGPA is never parsed from a resume". The resume path does parse it (`matching/engine.py:281` `find_cgpa`, the D19 verification flag). Only the second half holds (nothing pre-fills or stores it), as the R5 blocker resolution above anticipated. This needs a product call to reword the box; the verifier cannot tick it as written.
- **Minor, not blocking:**
  - `api/roster.ts` types `FlaggedSignup.id` and `RosterStudent.id`, and `api/auth.ts` types `User.id`, as `number`; the API sends UUID strings.
  - `test_admin_resolves_a_cgpa_review` still asserts only `AuditLog.count() > before`, and the admin detail GET inside it writes an `identity_accessed` row, so the assertion would pass without the resolve audit. The verifier checked it live: +1 `cgpa_review_resolved`. No test pins that action.
  - `openDocument()` never revokes its object URL.
  - The company payload's `completion_percent` now moves with `career_path`, so a company can infer "has chosen a path" (not which one).
  - `profiles/verification.py:69` still passes `transcript_cgpa=None`; the parsed transcript CGPA is not fed into the resume-verification flags.
- **Second verifier's findings: what was done (orchestrator, 2026-10-20).**
  - **Duplicate D20–D22:** renumbered to D23–D25 and moved beside the other numbered decisions. The other session's refs in `CONTEXT.md` and `PROGRESS.md` were left as they were, because they still point at its own D20–D22.
  - **Company `completion_percent` leaked career path:** companies now get `company_completion_percent`, which leaves out the career_path item. Pinned by `test_company_completion_does_not_move_with_career_path`, which was red first.
  - **`test_admin_resolves_a_cgpa_review` was weak:** it now asserts exactly one `cgpa_review_resolved` row for the PRN.
  - **R5 box "CGPA is never parsed from a resume":** reworded to the behaviour agreed earlier (a resume never writes or pre-fills a CGPA; D19's admin-only flag reads it). Left unticked for the verifier.
  - **Sent to a Sonnet agent:** the download should keep the original filename, blob URLs should be revoked, the onboarding page should include the transcript upload, and frontend ids should be UUID strings.
  - **Logged in `TODO.md`:** the verification flags don't use the transcript CGPA.

**2026-10-20, third verifier (fixes in `350d8e7`, `57636dc`).** Working tree at HEAD `57636dc`; red-without-fix check in a `git archive HEAD` copy in the session scratchpad.

- **P4 `[!]` stale refs.** `git grep -nwE "D2[0-5]"` is clean, but the old numbers survive as D15–D17: `docs/HANDOFF.md:57` "(email OTP later, D15)", `:58` "Addendum recommendations all accepted (D16)", `:65` "authenticated endpoints (D17)"; `PLAN_PHASE_A_AND_ADDENDUM.md:80` xfail reason "DECISIONS D15". In `DECISIONS.md` D15–D17 are the Llama, optional-services and model-arithmetic decisions. Fix: D23/D24/D25 there (line 134 of HANDOFF can keep its "renumbered from" note). Everything else in P4 holds.
- **Company completion `[x]`.** `CompanyProfileSerializer.completion_percent` has `source="company_completion_percent"` (drops `career_path`); `OwnProfileSerializer`/`AdminProfileSerializer` keep the base full figure; `matching/views.py` reuses the company serializer. With the three serializer lines removed, `-k completion_does_not_move` fails: `company completion moved 0 -> 12`; at HEAD it passes.
- **`test_admin_resolves_a_cgpa_review` `[x]`.** Now asserts `AuditLog.objects.filter(action="cgpa_review_resolved", target=<prn>).count() == 1`; passes.
- **Frontend `[x]`.** `downloadFile` takes the `Content-Disposition` name (RFC 5987 form first), falling back to the passed name; URLs are relative and proxied, so the header is readable. `DocumentButton` gains a Download button. `openDocument` revokes after 60 s. `OnboardingPage` renders `TranscriptCard` outside the form; a test completes onboarding without a transcript. `User.id`, `RosterStudent.id`, `FlaggedSignup.id` and the flagged-page state are `string`. Minor: the transcript card sits below "Save and continue", so a student may submit before seeing it.
- **R5 resume CGPA `[x]`.** `MyResumeView.post` → `apply_parsed_resume` sets only resume text, experience, education and the upload time; `parsed_cgpa`/`recomputed_cgpa`/`confirmed_cgpa` are written only by `MyTranscriptView` and `MyConfirmCgpaView`; nothing writes `Student.cgpa`. `test_resume_upload_never_sets_a_cgpa_field` passes.
- **Runs:** checkpoints `135 passed, 1 xfailed in 201.34s` (XFAIL cites D23); `profiles core` `292 passed in 299.18s`; frontend `Tests 120 passed (120)` (16 files), `tsc` exit 0, `vite build` exit 0; real-series grep exit 1, no hits.

**2026-10-20, verifier (P4 re-check at HEAD `f3b0f1e`).**

- **P4 `[x]`.** `DECISIONS.md` has 25 headings, exactly one each for D1–D25 (D15 Llama, D16 optional services, D17 model arithmetic, D23 admin MFA, D24 addendum, D25 documents). `git grep -nwE "D1[5-9]|D2[0-5]"`: every hit matches its decision. HANDOFF and the plan cite D15–D17 only in the two renumbering notes. `CONTEXT.md` (D16, D18–D20, D21), `PROGRESS.md` (D15–D22) and `RESUME_INTELLIGENCE_CHECKLIST.md` (D15–D22) mean the resume-intelligence set. The strict MFA xfail cites D23.
