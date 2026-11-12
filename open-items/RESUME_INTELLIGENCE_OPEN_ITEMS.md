# Resume Intelligence: Open Items and Decisions Needed

Everything about [`RESUME_INTELLIGENCE_PLAN.md`](../RESUME_INTELLIGENCE_PLAN.md) that still needs a person: work that could not be done here, decisions only you or the placement cell can make, and known problems that were left open on purpose.

**Where things stand (2026-10-19):** all nine tasks are built and verified, and they are signed off **for running without the LLM and MongoDB**, which is how a clean clone starts. The evidence is in [`RESUME_INTELLIGENCE_CHECKLIST.md`](../RESUME_INTELLIGENCE_CHECKLIST.md) and [`SMOKE_TESTS.md`](../SMOKE_TESTS.md). Nothing is pushed: the repo has no remote configured.

Each item carries a status. **Today** is what the code does right now if you change nothing.

---

## 1. Must happen before the AI features go live

These block sign-off for the live configuration: Ollama + MongoDB.

### 1.1 The live run (plan §5.4)

- **Why it is open:** this environment has no network, so Ollama, the Llama model and MongoDB could not be installed. Every test used a fake model and a local vector store.
- **What it proves:**
  - the real model returns usable JSON from real resumes
  - real embeddings rank resumes sensibly
  - MongoDB's `$vectorSearch` works with our index
- **Needs:** a machine with network, Docker, and about 8 GB of free RAM for `llama3.1:8b`.
- **Steps:**
  ```sh
  docker compose --profile llm --profile vectors up
  docker compose exec ollama ollama pull llama3.1:8b
  docker compose exec ollama ollama pull nomic-embed-text
  # .env: LLM_ENABLED=true  LLM_BASE_URL=http://ollama:11434/v1
  #       MONGO_URI=mongodb://mongo:27017/?directConnection=true
  python manage.py init_vector_index
  python manage.py eval_extraction --llm      # paste the table into SMOKE_TESTS.md
  MONGO_URI=... pytest matching/tests/test_vectorstore.py   # the one skipped test
  ```
  Then upload the sample resumes, run a job-description (JD) search, and record the results.
- **Pass when:**
  - the LLM column of `eval_extraction` is close to the regex column
  - the two backend resumes rank above the other three
  - the sample JD creates a "Backend Engineer" category
  - the MongoDB round-trip test passes
- **Status:** pending a human.

### 1.2 Confirm the `pymongo` version

`requirements.txt` pins `pymongo==4.10.1`. That pin was written without network access, so it has never been installed or tested here. Install it during 1.1 and adjust the pin if needed.

### 1.3 Re-measure four provisional numbers

These were set without a real model. Measure them during 1.1 and change them in `.env` or `config/settings.py`.

| Setting | Now | What it controls | How to re-measure |
| --- | --- | --- | --- |
| `MATCH_SCORE["CALIBRATION"]["embedding"]` | floor 0.40, ceiling 0.85 | How raw embedding similarity becomes the 0–100 score | Score the 10 samples against the sample JD and set the floor and ceiling around the observed range. The spaCy and TF-IDF values were measured this way |
| `CATEGORY_MERGE_THRESHOLD` | 0.75 | How similar two JDs must be to share a role category | Post several JDs for the same role and for different roles, and check for merges and splits |
| `SKILL_ALIAS_SUGGESTION_THRESHOLD` | 0.85 | When an unknown skill is suggested as an alias of a known one | Look at the suggestions an admin receives; too many wrong ones means raise it |
| `CATEGORY_MIN_FIT` | 0.4 | How good a fit a student needs to be shown a role | Check whether students get sensible "roles you fit" |

---

## 2. Decisions for you

Each has a recommendation. The **Today** line is what happens if you do nothing.

### Infrastructure

**2.1 Where does the production Ollama server run, and who protects it?**
Ollama has no login of its own: anyone who can reach its port can use the model and read the prompts it is sent, which contain resumes.
- *Options:*
  - a GPU machine on the college network, firewalled so only the backend can reach it
  - a CPU machine, which takes about 10–30 s per resume
- *Recommendation:* a firewalled college server, plus an authenticating reverse proxy if anything other than the backend shares the network.
- *Today:* `localhost:11434`, off by default.

**2.2 A GPU, or accept slow analysis?**
- On a CPU, one resume analysis can take up to the 25 s time budget (`RESUME_ANALYSIS_TIME_BUDGET_SECONDS`), and the student waits on a spinner while it runs.
- During a placement drive, with hundreds of uploads, a CPU server will queue up.
- *Recommendation:* a GPU if the budget allows. Otherwise keep the 25 s budget: the reading falls back to regex and the student can retry.

**2.3 Where does MongoDB run in production?**
The `mongodb/mongodb-atlas-local` image is for development only. For production, choose between:
- MongoDB Atlas, the hosted service
- a self-hosted MongoDB that supports vector search; confirm the edition and version you deploy actually serves `$vectorSearch`
- no MongoDB: the local vector table works, just more slowly at scale

Atlas stores student-derived data (vectors, department, skills) with a third party. That needs a data-location and privacy check (see 2.9). *Recommendation:* self-hosted, or no MongoDB at first; the local store is fine at college scale. *Today:* local store.

**2.4 Add a shared cache (Redis or Memcached).**
`CACHES` is not configured, so each worker process keeps its own counters. That affects three things:
- the 30-per-hour matching limit is really 30 × the number of workers
- the JD reading cache is not shared
- the "this JD already fed a category" marker can fire once per worker

*Recommendation:* Redis, before production. *Today:* in-memory, per process.

**2.5 Production web server and request timeouts.**
The Dockerfile runs `manage.py runserver`, which is a development server. Whatever replaces it (gunicorn, uvicorn, behind nginx) needs a request timeout longer than the 25 s analysis budget, or the analyse endpoint will be cut off. *Recommendation:* gunicorn with `--timeout 60` (or more) behind nginx.

**2.6 A background job queue?**
Analysis runs inside the web request because the repo has no task queue. That is simple, and acceptable at college scale, but every slow model call holds a worker.
- *Options:*
  - keep it synchronous
  - add Celery or RQ later, so an upload returns at once and analysis runs in the background; the frontend already polls for a `pending` status
- *Recommendation:* keep it synchronous until 2.2 shows it hurts.

**2.7 Search without embeddings only looks at the newest 500 resumes.**
- With the LLM off, search scores the newest 500 visible profiles. A larger cohort means older students are never ranked.
- The limit is `MATCH_FALLBACK_MAX_PROFILES`.
- *Options:* turn on embeddings (the real fix), or raise the cap. Raising it to 2000 costs about 4× the time per search; 500 takes about 9 s on spaCy at the cap.
- *Recommendation:* enable embeddings in production; until then, set the cap to the cohort size if the searches stay fast enough.

**2.8 The 30-per-hour matching limit.**
One shared limit per user covers search, score, check-my-fit and resume analysis. A recruiter screening many JDs during a drive may hit it. *Decide:* the rate for companies, students and admins, and whether they should differ. *Today:* 30/hour for everyone (`MATCHING_THROTTLE_RATE`).

### Privacy and policy (placement cell, ideally the college's privacy officer)

**2.9 Storing age, date of birth, phones and emails from resumes.**
- The model's reading (`ResumeAnalysis.facts`) stores these so admins can check them. Admins only, never companies.
- Under India's DPDP Act, data minimisation and purpose limits apply. *Decide:*
  - Is admin-only plausibility checking a good enough purpose to store age and DOB at all?
  - How long are the facts kept? (Today: until the resume is deleted. There is no automatic expiry, for example at graduation.)
  - Should students be told, in the upload screen or a privacy notice, that their resume is read by an AI model on a college server?
- *Recommendation:* add a one-line notice at upload; set a retention rule (delete facts some months after graduation); keep age and DOB admin-only as now.

**2.10 Should students see a numeric match score?**
- "Check my fit for a JD" shows a student "Match N of 100" with the breakdown.
- *For:* it is transparent and shows which skills are missing.
- *Against:* a low number may discourage applicants, and the score is a heuristic.
- *Today:* shown, labelled "match", never "probability", with the breakdown always visible.

**2.11 Match score weights.**
Today: meaning 45%, skills 35%, experience 10%, education 10% (`MATCH_SCORE["WEIGHTS"]`). The placement cell should confirm this reflects what recruiters value, or tune it.

**2.12 Stated experience vs. dated experience.**
- When the model finds dated jobs, their total beats a figure the resume states. "3 years of experience" with six months of dated internships pre-fills as 0.5, and admins get a warning that the stated figure is not supported by the dates.
- *Confirm* this is the policy. The student can always correct the pre-filled value.

**2.13 CGPA checks (a narrowing of R5).**
- The resume CGPA is used only to flag a mismatch with the roster (and the transcript, once R5 lands). It is never stored as a profile value, and the roster stays authoritative.
- *Confirm:*
  - the tolerance (0.1 points, `VERIFICATION_CGPA_TOLERANCE`)
  - converting a percentage to CGPA by dividing by 9.5, which is CBSE's formula; Sai University may publish its own conversion
- This also answers DECISIONS.md's open question "On a CGPA mismatch, which value wins": neither, it is flagged.

**2.14 Role categories: who curates them, and do companies see them?**
- Categories are learned from the JDs companies post. Admins rename and merge them in Django admin, and approve skill-alias suggestions. *Decide:*
  - which admin does this, and how often
  - whether companies may filter students by category (they can today)
  - whether production starts empty or seeded with the demo categories (Backend Engineer, Data Analyst, Frontend Developer, Mechanical Design Engineer)
- *Today:* empty until JDs arrive; the demo seed runs only with `seed_demo`.

**2.15 The analysis is only as private as the server it runs on.**
The design keeps resumes on college servers (D15). That guarantee only holds if `LLM_BASE_URL` really points at a college machine. Make "who may change that setting" part of the deployment checklist.

### Process

**2.16 The QA gate.**
- CONTEXT.md §5 says only the QA agent marks checkpoints passed. Here, a separate Opus verifier played that role, but the repo's own QA gate (`backend/checkpoints/QA-GATE.md`) has not been run over this work.
- *Recommendation:* run the repo's QA gate before treating it as done by house rules.

**2.17 Ownership reviews.**
- `matching/` belongs to A2 (Opportunities), and A1 owns migration ordering.
- This work added 8 migrations:
  - matching 0001–0005
  - profiles 0003–0004
  - core 0003
- It also changed A2's engine ahead of Phase B. *Recommendation:* A1 reviews the migration order and A2 reviews the engine API before Phase B builds on it.

**2.18 Building ahead of Phase B.**
AGENTS.md says to work phase by phase. This feature landed before Phase B (Opportunities). Phase B now reuses it: an `Opportunity` calls `get_engine().match_score(...)` and feeds role categories. *Decide:* accept this as a recorded deviation, or schedule a review.

---

## 3. Known problems, left open on purpose

All are minor. None blocks offline use.

| # | Problem | Effect | Suggested fix |
| --- | --- | --- | --- |
| X1 | With the LLM off, a resume that *states* an inflated figure ("40 years of experience") is taken at its word, and no flag fires | Admins see the stated number; the student is asked to confirm it at pre-fill | Flag stated experience that is implausible for a student (e.g. > 5 years) even without the model |
| X7 | The form counts months end-exclusive (Jan–Jun = 5); the resume counts both end months (6) | An admin can get a false "experience mismatch" warning right at the 6-month line | Pick one convention. Changing `ExperienceEntry.duration_months` touches Phase 3 code, so decide with its owner |
| V3 | Bulk edits to skills in the database skip cache invalidation | Other workers see the change up to 5 minutes later | Fine as is; or clear the cache after bulk scripts |
| V4 | The 25 s analysis budget does not cover the fixed 2 s connection timeout | Analysis can overrun by about 2 s when the server is unreachable | Fine at a 25 s budget |
| X4 | "2-4 years of experience" in a JD sets no minimum when the LLM is off | Nobody is wrongly filtered out (it fails safe) | Read ranges as their lower bound |
| m2 | A role and its dates on separate lines, with no section header, read as 0 years | Under-counts; the student corrects it at pre-fill, and the LLM path reads it | Deferred: loosening this read education dates as work |
| m4 | "First Class with Distinction (75%)" is not read as a CGPA | No CGPA flag for that resume | Deferred: loosening it risks reading school percentages as a degree CGPA |
| — | A standalone capital "C" ("Grade C", "C-suite") reads as the C language; lowercase "c programming" is missed | Occasional wrong or missed skill | Accept, or require context words |
| — | A year that appears only in a PRN (e.g. `2019BTCS042`) can vouch for an invented 2019 job | The model's experience total is very slightly harder to fake-proof | Exclude PRN-shaped tokens from the year check |
| — | A merged ".NET" skill is named `dotnet` | Cosmetic | Rename it in Django admin |
| — | The company filter `skills=c` now matches only C, not C++ or C# | An intended change; recruiters used to the old behaviour may notice | Mention it in release notes |
| — | **Outside this plan:** `describeError` in `frontend/src/api/client.ts` drops other keys when an error has a string `detail`, so `LoginPage`'s `needs_verification` check never fires | The login page still works through its 403 check | For A1/A5 |

---

## 4. Repo housekeeping

1. **Another session's uncommitted edits:** 28 files in the working tree, mostly changing the example PRN `220200921` → `260200921` across docs, fixtures and tests. None of this work committed, staged or reverted them. Whoever owns that change should commit or discard it.
2. **Leftover worktrees:** five agent worktrees under `.claude/worktrees/` (branches `worktree-agent-*`). All their commits are already on `main`, so they can be removed. Separately, `../collage-placements-phase-a` (branch `phase-a-addendum`) is not from this work; leave it alone.
3. **After the next migrate on any real database:**
   - with the LLM on: `manage.py reindex_vectors` (full), then `manage.py recategorise`
   - with the LLM off: skip `reindex_vectors`, because search falls back without vectors
   - details in [`PROGRESS.md`](../PROGRESS.md)
4. **No remote is configured,** so nothing has been pushed or reviewed outside this machine.

---

## Quick list

- [ ] 1.1 Live run with Ollama + MongoDB, recorded in `SMOKE_TESTS.md`
- [ ] 1.2 Confirm the `pymongo` pin
- [ ] 1.3 Re-measure the 4 provisional numbers
- [ ] 2.1 Production Ollama host + firewall
- [ ] 2.2 GPU or CPU
- [ ] 2.3 Where MongoDB runs (or none)
- [ ] 2.4 Shared cache (Redis)
- [ ] 2.5 Production web server and timeout
- [ ] 2.6 Background job queue: now or later
- [ ] 2.7 Fallback search cap vs. cohort size
- [ ] 2.8 Matching rate limit per role
- [ ] 2.9 Privacy: storing age/DOB/contacts, retention, the upload notice
- [ ] 2.10 Show students a numeric match score?
- [ ] 2.11 Match score weights
- [ ] 2.12 Dated experience beats a stated figure: confirm
- [ ] 2.13 CGPA tolerance and the percentage conversion
- [ ] 2.14 Who curates categories; do companies see them; seed demo categories?
- [ ] 2.15 Who may change `LLM_BASE_URL`
- [ ] 2.16 Run the repo's QA gate
- [ ] 2.17 A1 and A2 reviews
- [ ] 2.18 Accept building ahead of Phase B
- [ ] 3 Decide on X1 and X7
- [ ] 4 Commit or discard the other session's edits; remove the worktrees
