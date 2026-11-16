# Plan: full E2E suite, finishing Phase B + Addendum 2, and publishing

Written 2026-11-16. This covers what's left after the interruption: the E2E suite you
asked for, the end of the Phase B and Addendum 2 build, and committing and pushing.

## Where things stand right now

- **Committed on local `main`:**
  - `16fa806` is the public snapshot, already on GitHub.
  - `48fed87` (groundwork for Phase B and Addendum 2) is on top of it and **not pushed yet**.
- **Uncommitted:** `frontend/package.json` and `package-lock.json` now include
  `@playwright/test ^1.65.1`. That version needs a browser build that is **not on disk**,
  because the download failed. Recommendation: pin `1.62.1` instead (see blocker 2), or
  revert these two files.
- **Running in the background,** each in its own worktree and with nothing merged yet:
  1. **QA:** `checkpoints/test_checkpoint_b.py`, the Phase B acceptance tests, written red first.
  2. **S2:** the Phase B backend. That's opportunities, applications, screening, stats,
     notifications and demo data.
  3. **FE:** the frontend for Stage 2 and notifications.

## Blockers to clear first (your call)

### 1. The disk is almost full: 283 MB free

Nothing in this project is the cause. The large users are:

| What | Size | Whose |
| --- | --- | --- |
| Docker Desktop data | 6.5 GB | yours |
| Ollama models (`~/.ollama`, includes `gemma4:e4b`) | 6.4 GB | yours, and needed for the Gemma work |
| Playwright browser cache (`~/Library/Caches/ms-playwright`) | 1.7 GB | 3 Chromium builds installed by other projects (campus-club-ui, zshield, anaconda) |
| Other projects' Claude scratch folders (`/private/tmp/claude-501/…`) | about 1.2 GB | other sessions |

**Until about 2 GB is free, the running agents may fail** on test databases and migrations.
**Recommendation:**
- Run `docker system prune` (it removes unused images and containers; check what it lists first).
- Or delete the oldest Playwright build (`chromium-1223` plus its headless shell, about 550 MB, from May), if no project still uses it.

I won't delete anything outside this project without your go-ahead.

### 2. Which Playwright version

Playwright `1.62.1` uses Chromium build **1234**, which is **already on disk**, so pinning to it
needs **no download**. The latest version, `1.65.1`, needs a new build of about 600 MB.
**Recommendation: pin `1.62.1`.**

---

## Part 1: finish Phase B and Addendum 2 (in progress)

1. **Merge the three running agents** as they finish:
   - Review each diff.
   - Cherry-pick it onto `main`.
   - Run the backend and frontend suites **on `main`**.
2. **Wave 2:**
   - **S3:** suggestions (backend).
   - **S4:** recruiter exports (backend). That's the CV zip, the AES-encrypted contact zip and the leak test.
   - **FE:** the Suggestions and Shortlist pages. The same frontend agent continues the work.
3. **Opus verifier** ticks [`ADDENDUM2_PHASE_B_CHECKLIST.md`](ADDENDUM2_PHASE_B_CHECKLIST.md) from its own runs.
4. **The `agents.md` Phase 4 smoke test runs live on `main`,** with the output recorded in `SMOKE_TESTS.md`.

## Part 2: the full E2E suite

### What it covers

Everything built in these sessions:
- Phases 0–3, through the existing script, unchanged;
- Phase A, the identity retrofit;
- requirements addendum R1–R5;
- Phase B and Addendum 2 stages 2–4.

Stage 1 marksheets belong to another session and appear only as test data in the "companies never see this" checks.

**What it does not repeat:** the pytest checkpoint suites (A, B, E) stay where they are. Key rotation, the MFA xfail and the rate-limit (429)
tests need to change settings mid-run, so they stay in pytest. The E2E suite tests **cross-role journeys
against a running server**.

### Layer 1: API journeys against a live server (`backend/e2e/`)

**One command, `python e2e/run.py`, does everything:**
1. Makes a fresh run folder under `backend/e2e/.runs/<timestamp>/`, which is gitignored, and points both `DATABASE_URL` and
   `MEDIA_ROOT` at it. **The server and every `manage.py` call share it**, because a mismatch caused a false
   failure before. It never touches `db.sqlite3` or `backend/media`.
2. Generates the sample resumes and transcripts if they're missing, so a clean clone works.
3. Runs `migrate` and the seed, then starts the server with OTPs returned in responses and high rate limits for
   OTP, anonymous, matching and export requests, so the run never throttles itself.
4. Runs the selected suites, then stops the server and prints `N/M passed` per suite.
   - **"not built yet" is reported apart from failures,** so the Phase B suites can sit
     unbuilt without hiding real regressions.
5. Exits non-zero on any failure.

`--suite` picks suites, and `--keep` keeps the run folder for debugging.

| Suite | Journeys |
| --- | --- |
| `phase_0_3` | The existing 43-check script, **on its own fresh database** with the plain seed, because it compares exact result sets |
| `identity` | Signup → verify → login. The token carries the full claim set and `roles[]`. The JWKS endpoint validates the token. Replaying a refresh token kills the session family. Suspending a student kills their live sessions (the suspension is set by a `manage.py` call, labelled as setup). `?prn=`, `?prns=` and `unmatched_prns`, and whitespace in a filter value. An unknown query parameter is a 400. `ADM-` and `CMP-` ids. Two recruiters at one company share one shortlist |
| `addendum` (R1–R5) | Onboarding: required fields, personal email ≠ college email, skip. Career path, including "Other" with text. Transcript: clean, someone else's PRN refused and not stored, tampered CGPA flagged, admin resolves the review. Admin opens the resume and transcript, and each open is audited. A company never gets a transcript, career path or CGPA field, and its completion figure ignores career path. The outcomes table adds up to the cohort, and the CSV export works. `/media/` is closed |
| `phase_b` | A recruiter posts, it waits for approval, and students can't see it. The admin approves, and eligible students get a notification. The feed ranks the matching student higher. Apply: each refusal reason; the snapshot holds the roster CGPA and the resume. Shortlist rules (D27): withdraw, manual shortlist, un-shortlist. A hidden student applies. Status moves are recorded as events, and a bad move is a 400. Bulk screening. The applicant CSV has PRN first. Admin stats. `notify_deadlines` runs as setup, twice: it notifies once, never twice |
| `suggestions` | Ranked suggestions above the cut-off. The two empty states. No "probability" wording anywhere. Works with the AI off |
| `exports` | `?shortlisted=true` returns the real shortlist only. The CV zip, counting students with no resume. The contact zip **needs the password** and contains the right rows. Unverified students have blank contacts. **A student who goes hidden after being shortlisted is in neither export.** One company cannot export another's shortlist. Each export is audited |

**PRN range for the E2E suite: sequences 800–899.** The ranges below are already used:

| Sequences | Used by |
| --- | --- |
| 901–911 | the demo roster |
| 920–935 | the checkpoint tests |
| 940–959 | the QA tests |
| 960–989 | the existing E2E script |
| 990–999 | the Phase B seed |

### Layer 2: a real browser (Playwright, `frontend/e2e/`)

This closes the open item that nothing drives the built app in a real browser.

- Chromium only, with `@playwright/test` pinned to `1.62.1` (blocker 2).
- `playwright.config.ts` starts Django on a fresh run folder with the seed, and starts Vite with
  `VITE_API_PROXY` pointing at it. Both stop when the run ends.
- **About one journey per role, plus the visibility demo.** The API layer covers the details.
  1. **Student:** sign in → onboarding → career path → upload a resume and review the pre-fill → upload a
     transcript and see the CGPA notice.
  2. **Admin:** sign in → profiles → open a student → open the resume (a new tab) → verify →
     outcomes dashboard → CSV export.
  3. **Company:** sign in → browse with filters → shortlist. As a second company, the same search
     no longer shows the shortlisted-only student.
  4. *After the Phase B frontend merges:* a recruiter posts → the admin approves → the student
     sees it in the feed, applies and withdraws → the recruiter moves the status → the student's
     notification badge.
  5. *After Stage 4 merges:* the recruiter's Shortlist page shows the contact password once.

  **Specs 4 and 5 wait for their pages to merge.** Selectors written against unbuilt pages
  would be guesses.

### How it's built and checked

| Step | Who | When |
| --- | --- | --- |
| Pin Playwright and add the config | me, on `main` | once blocker 2 is decided |
| Layer 1: runner + `phase_0_3`, `identity`, `addendum` suites | Sonnet agent | now; those features already exist |
| Layer 1: `phase_b`, `suggestions`, `exports` suites | the same agent, against the API contract | now; they report "not built yet" until merged |
| Layer 2: specs 1–3 | Sonnet agent | now |
| Layer 2: specs 4–5 | the same agent | after the frontend merges |
| Run both layers **on `main`**, tick the checklist, record output in `SMOKE_TESTS.md` | Opus verifier | after everything merges |

The two layers are added to the GATE section of the checklist. A pass in a worktree doesn't count;
before, a run in a worktree passed while the same run failed on `main`.

## Part 3: commit and push

- **Commit on `main` per merged step.** I stage named files only, never everything.
- **Push `main` only,** as a normal push on top of the snapshot that is already on GitHub.
  **Never** push `backup/pre-scrub`, `backup/pre-rewrite-main` or
  `history/scrubbed`: the older ones contain a real student's PRN.
- Before each push, I check that the real student's PRN appears nowhere in the commits being pushed.
- **Right now** I could push `48fed87`, the groundwork, as soon as you say so. The `package.json` change
  waits for the Playwright decision.

## What I need from you

1. **Disk:** free about 2 GB yourself, or tell me which of the items in blocker 1 I may remove.
2. **Playwright:** pin `1.62.1` (recommended), or download the latest.
3. **Pushing:** push `48fed87` now, or push once Part 1 is merged and verified.
