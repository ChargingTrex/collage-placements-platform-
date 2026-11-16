# Remaining work

Written 2026-11-16 from the state of the repo and the machine at that moment. Three Claude
sessions are working in parallel, so check `git log` before trusting any line here.

Detail lives in the plans this file points to: [`E2E_SUITE_PLAN.md`](E2E_SUITE_PLAN.md),
[`ADDENDUM2_PHASE_B_CHECKLIST.md`](ADDENDUM2_PHASE_B_CHECKLIST.md),
[`LIVE_RUN_PLAN.md`](LIVE_RUN_PLAN.md) and [`open-items/OPEN_ITEMS.md`](open-items/OPEN_ITEMS.md).

## 1. Needs you first

| # | What | Why it blocks |
| --- | --- | --- |
| 1 | **Force quit and reopen Docker Desktop.** It has been stuck at "starting" since the morning and every `docker` command hangs. Commands: `pkill -9 -f "Docker.app"; pkill -9 -f "docker-ai"; pkill -9 -x docker`, then `open -a Docker` | The Docker trim (section 2) and the MongoDB live run (section 5) |
| 2 | **Lower Docker's memory to about 4 GB** (Settings → Resources) once it is up | Gemma timed out earlier under memory pressure |
| 3 | **Say when to push.** `main` is 91 commits ahead of GitHub | Section 6 |
| 4 | **Decide on the stale agent worktrees** (section 7). Five have uncommitted changes | Cleanup |

## 2. Docker trim (not started)

Nothing has been deleted. It starts once Docker's engine is running.

1. Record an inventory: every image with tag, digest and size, plus containers, volumes and
   build-cache totals.
2. Remove stopped containers, unused images and the build cache, **except** the protected
   items below. No volume is removed, because volumes hold data that cannot be re-downloaded.
3. Write `DOCKER_TRIM_LOG.md` at the repo root: each removed image with its exact
   `docker pull` command (pinned by digest), or the project and compose file to rebuild it from.

**Protected — agritag** (`agriGitag/infra/docker-compose.yml`, compose project `agritrace`):

- Images: `postgis/postgis:16-3.4`, `valkey/valkey:8-alpine`, `localstack/localstack:4.14.0`,
  `amazon/aws-cli:2.39.1`, `eclipse-mosquitto:2`, `python:3.12-slim`, every `agritrace-api:*` tag.
- Every container and volume in a compose project starting with `agritrace`, including
  `agritrace-p07qa`. The `db-data` Postgres volume above all.

**Protected — Tamil OCR/HTR:** neither `TAMIL OCR` nor `Tamil-OCR-HTR-Benchmark` has a
Dockerfile or compose file. Anything in Docker whose name points at them (tamil, ocr, htr,
tesseract, kraken, paddle, trocr) is kept.

## 3. Phase B and Addendum 2 (in progress, another session)

The checklist shows **0 of 46 boxes ticked**. Code has landed on `main` (the Phase B frontend
pages and their tests, the E2E runner), but only the verifier ticks boxes, and it has not run.

- [ ] **QB:** `checkpoints/test_checkpoint_b.py` written and red for "not built yet" reasons.
- [ ] **S2:** opportunities, applications, screening, stats, notifications (backend).
- [ ] **S3:** suggestions (backend).
- [ ] **S4:** recruiter exports: CV zip, AES-encrypted contact zip, the leak test.
- [ ] **FE:** Suggestions page and Shortlist page. The opportunity, applicant and notification
      pages are committed (`f7bb7b7`, `7ca439d`) but unverified.
- [ ] **SEED:** `seed_demo` creates opportunities, applications and notifications; `DEMO_LOGINS.md` describes them.
- [ ] **GATE:** checkpoints A, E and B pass; backend passes on spaCy and TF-IDF; frontend
      tests, typecheck and build pass; the `agents.md` Phase 4 smoke test runs live on `main`
      with output in `SMOKE_TESTS.md`.

## 4. E2E suite (in progress, another session)

**Layer 1, API journeys (`backend/e2e/`):** the runner and the `phase_0_3`, `identity`,
`addendum`, `phase_b`, `suggestions` and `exports` suites are committed (`b5bacfb`, `dd8530a`,
`911f82d`). It was built on Robot Framework, not the plain `python e2e/run.py` runner the plan describes.

- [ ] Run every suite on `main` and record the output. The Phase B suites report "not built"
      until the backend merges.
- [ ] Add a strict mode that turns "not built yet" into a failure, for the final gate.

**Layer 2, browser (`frontend/e2e/`):** not started. The folder does not exist.

- [ ] Pin `@playwright/test` to exactly `1.62.1`. `package.json` still says `^1.65.1`,
      uncommitted. `1.62.1` uses Chromium build 1234, which is on disk; a caret resolves to
      1.65.x, which needs a 600 MB download.
- [ ] Exclude `e2e/` from Vitest in `vite.config.ts`, or `npm test` and CI will collect the Playwright specs and fail.
- [ ] Add `backend/e2e/.runs/`, `frontend/test-results/` and `frontend/playwright-report/` to `.gitignore` if not already there.
- [ ] `playwright.config.ts` on a free port with `reuseExistingServer: false`.
- [ ] Specs 1–3 (student, admin, company), then 4–5 after their pages merge.

**Both layers:**

- [ ] Add them to `ci.yml`. CI runs backend and frontend tests today, and neither E2E layer.
- [ ] Decide whether the weekend-demo features (admin users list, demo sign-in, `DEMO_MODE`) get a suite.

## 5. Live run with Gemma and MongoDB ([`LIVE_RUN_PLAN.md`](LIVE_RUN_PLAN.md))

- [ ] Step 1: MongoDB in Docker. Blocked on Docker (section 1).
- [ ] Step 4, remainder: the category merge-threshold check. Needs the API run.
- [ ] Step 5: end-to-end through the API.
- [ ] Step 6: record, verify, commit.

While `.env` sets `MONGO_URI`, `test_real_mongo_round_trip` runs instead of skipping, and fails until MongoDB is up.

## 6. Publishing

GitHub (`ChargingTrex/collage-placements-platform-`, public) holds one snapshot commit, `16fa806`.

- [ ] Push `main`. The 91 unpushed commits contain no hit for the real student's PRN or name
      (checked 2026-11-16). Re-check before pushing, because more commits will have landed.
- [ ] Install a local, untracked pre-push hook that runs that check and refuses any branch but `main`.
- [ ] Update the notes that still call publishing an open decision: [`LEFTTODO.md`](LEFTTODO.md),
      [`NEXT_PHASES.md`](NEXT_PHASES.md), `open-items/OPEN_ITEMS.md` §1.1, `docs/HANDOFF.md`.
- [ ] Refresh `LEFTTODO.md` and `TODO.md`, both dated 2026-10-20 or earlier.

**Never push:** `backup/pre-scrub`, `backup/pre-rewrite-main`, `phase-a-addendum`, or any
`worktree-agent-*` branch that does not descend from `16fa806`. They carry the real PRN.
`history/scrubbed` is clean but unrelated to `main`.

## 7. Cleanup

- [ ] About 27 agent worktrees under `.claude/worktrees/` (92 MB when measured). Remove the
      finished ones. Five had uncommitted changes when checked: `agent-a153…`, `agent-a632…`,
      `agent-a899…`, `agent-abcd…`, `agent-ae81…`. Harvest or discard those deliberately.
- [ ] Delete the `worktree-agent-*` branches on the old history once nothing is needed from them.
- [ ] Disk: free space swung between 293 MB and 6.5 GB during the day. E2E run folders should be deleted on success.

## 8. After the demo

- [ ] Admin MFA by emailed one-time code (D23). The strict xfail in checkpoint A becomes a failure when it lands.
- [ ] Token refresh in the frontend. Users are signed out after 15 minutes today.
- [ ] Phases C and D per `NEXT_PHASES.md`.

## 9. Waiting on someone else

| Ref | Question | Owner |
| --- | --- | --- |
| ID-05 / API-04 | The authoritative programme list, to replace the website-derived one in `roster/reference.py` | Registrar |
| — | Does the portal cover MBA / M.Sc. / Ph.D. cohorts, or undergraduates only? | Registrar |
| — | 3–5 more real transcripts, read locally and never committed | Placement cell |
| ID-04 | Institutional email domain and alumni policy | IT |
| ID-06 | How long a graduated student keeps access | Registrar |
| ID-07 | Is MFA available on the chosen SSO provider? | IT |

One proposal is recorded as **not approved, do not build**: the importer warning when a PRN's
entry year does not fit the batch (`PLAN_CHECKLIST.md`).
