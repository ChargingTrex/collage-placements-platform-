# PROGRESS

Running status of the phased build defined in [`agents.md`](agents.md).
Agreed scope for this prototype: **Phases 0–3 plus the halfway E2E
checkpoint.** Phases 4–6 (Opportunities Board, Certifications, Company
self-service) are out of scope for this pass; their Django apps exist as
empty scaffolding so the wiring is ready.

## Decisions taken before Phase 0

| Question | Decision |
| --- | --- |
| Scope | Phases 0–3 done properly, ending at the halfway E2E checkpoint |
| Database | SQLite by default for zero-setup dev; Postgres via docker-compose and in CI |
| Similarity backend | spaCy `en_core_web_md` preferred, scikit-learn TF-IDF fallback so a clean checkout and CI never block on the model download |
| Auth | JWT (SimpleJWT); OTP email through Django's console backend, echoed in the API response while `DEBUG` is on |
| Frontend | Vite + React 19 + TypeScript + Tailwind 4 |
| Uploads | Local filesystem behind a storage boundary (`core/storage.py`); `STORAGE_BACKEND=s3` swaps backends with no code change |
| Fixtures | Synthetic — 10-student roster, generated PDF/DOCX resumes, hand-checked reference file |
| Git | `git init` here, one commit per completed task, local only |

### Deviations from `agents.md`, and why

- **An `accounts` app exists alongside the five apps the Phase 0 checklist
  names.** `AUTH_USER_MODEL` has to be in place before the very first
  migration, and keeping identity (`User`, OTP) separate from the roster
  (`Student` master list) keeps the roster app a pure data source, which is
  how the PRD describes it.
- **A `core` app exists** for things with no single owner: the health
  endpoint, the upload storage boundary, and the admin audit log.

---

## Phase 0 — Scaffold & Environment

- [x] Django project with apps `roster`, `profiles`, `matching`,
      `opportunities`, `certifications` (plus `core`, `accounts`)
- [x] PostgreSQL configured for docker-compose and CI; migrations run cleanly
      from an empty database
- [x] React + TypeScript app scaffolded, talks to `/api/health`
- [x] Object storage config stubbed — local filesystem in dev behind an
      S3-ready interface (`core/storage.py`)
- [x] Environment variables documented in `.env.example`
- [x] CI runs backend + frontend suites on push (`.github/workflows/ci.yml`)

**Checkpoint:** `docker compose up --build` brings up backend + frontend + DB
from a clean clone with no manual step beyond `cp .env.example .env`.

**Smoke test:** see the Phase 0 section of [`SMOKE_TESTS.md`](SMOKE_TESTS.md).

## Phase 1 — Roster & Authentication

- [x] `Student` roster model: PRN, college email, department, batch, CGPA
      (plus phone and a placement-eligibility flag)
- [x] Admin roster upload (CSV) with row-level validation errors reported back,
      including a dry-run mode that validates without writing
- [x] Signup flow: PRN + email → matched against roster → OTP emailed
- [x] Login flow: password *or* emailed OTP; PRN or email accepted as the
      identifier, PRN unique across the system
- [x] Mismatched PRN/email blocked and flagged, with a distinct reason for
      each failure mode (unknown PRN / wrong email / wrong PRN / wrong domain /
      not eligible / already registered)
- [x] Company and admin accounts created separately by `manage.py seed_demo`
      (email + password, no PRN)
- [x] Rate limiting on OTP requests: per-account window plus a per-IP DRF throttle

**Checkpoint:** met — seeded roster students sign up, verify and log in; three
kinds of non-roster pair are rejected and appear in the admin's flagged queue.

**Smoke test:** PASS, recorded in [`SMOKE_TESTS.md`](SMOKE_TESTS.md).

Notes for whoever picks this up:
- OTP codes are stored HMAC-hashed, single-use, expiring, and locked after
  `OTP_MAX_ATTEMPTS` wrong guesses.
- `debug_otp` appears in API responses only while `DEBUG` is on; it is what
  lets the prototype UI be driven without reading the mail log.
- Route guards in the frontend are convenience only — every rule is enforced
  server-side by `accounts/permissions.py` and the viewset querysets.

## Phase 2 — Resume Parsing & Semantic Matching Engine

- [x] Text extraction for PDF (PyPDF2) and DOCX (python-docx), including
      DOCX tables, with whitespace normalisation and a typed `ResumeParseError`
- [x] Regex extractor for years/months of experience
- [x] Regex extractor for education level (UG / Masters / PG)
- [x] spaCy `en_core_web_md` loaded once per process as a service, with a
      semantic similarity function between two texts
- [x] Configurable similarity threshold — per call, per environment, and a
      per-backend default
- [x] Hard filters (minimum experience, required education) applied before ranking
- [x] Bulk screening: a candidate pool against one job description, returning
      ranked / below-threshold / excluded groups with extracted attributes
- [x] Packaged as the `matching` Django app with a clean callable boundary
      (`get_engine()`); no models, no views, no UI

**Checkpoint:** met — the engine reproduces the hand-checked experience and
education values for all five sample resumes and ranks the two relevant ones
above the three irrelevant ones.

**Smoke test:** PASS on both backends, recorded in [`SMOKE_TESTS.md`](SMOKE_TESTS.md).

Notes for whoever picks this up:
- The source prototype now lives at
  [`docs/reference/resume-matcher-prototype.py`](docs/reference/resume-matcher-prototype.py)
  with a table of what changed in the port. It is not imported by anything.
- `matching/samples.py` holds the reference set: resume text *and* the values
  a human read off it. `manage.py make_sample_resumes` renders them into real
  PDF/DOCX binaries (gitignored — regenerate, don't commit).
- spaCy and TF-IDF scores are on different scales. Never hardcode a threshold;
  read `engine.default_threshold` or the backend's `suggested_threshold`.
- `screen()` returns three groups on purpose: an empty shortlist should tell
  an admin *why* it is empty.

## Phase 3 — Student Profile

- [x] Profile model with experience entries, project entries (tech stack,
      links, team size), tagged skills and resume upload
- [x] Students create, edit and delete their own experience and project entries
- [x] Resume upload runs the Phase 2 engine; extracted experience and education
      pre-fill the profile for the student to review and correct
- [x] Visibility toggle (all companies / shortlisted only / hidden) enforced in
      the queryset, so a hidden profile is unreachable by any route
- [x] Admin verification with a badge on the company-facing view, and an audit
      entry in both directions
- [x] Company-facing search: department, skills, CGPA range, project keywords,
      plus experience, education level and verification state
- [x] Authorization: a student reaches only their own entries; companies see
      only what the visibility rule allows

**Checkpoint:** met — a test student's profile is correctly hidden and shown to
a test company per the visibility setting, and a resume upload pre-fills
experience and education for the student to confirm.

**Smoke test:** PASS, recorded in [`SMOKE_TESTS.md`](SMOKE_TESTS.md).

Notes for whoever picks this up:
- `parsed_experience_years` is what the engine read; `experience_years` is what
  the student confirmed. Never collapse the two — re-uploading a resume must
  not undo a correction.
- `StudentProfile.objects.visible_to(user)` is the visibility rule. Every list,
  detail and filter path goes through it. Do not add a queryset that skips it.
- `CompanyShortlist` lives in `profiles` rather than waiting for Phase 4,
  because "shortlisted companies only" is untestable without it. Phase 4's
  applications should build on it rather than duplicate it.
- The company serializer is deliberately narrower than the student's own: no
  resume text, no parser internals, and contact details only once verified.

## Halfway checkpoint — full E2E

**PASS — 30 of 30 checks.** Full output in [`SMOKE_TESTS.md`](SMOKE_TESTS.md).

- [x] Fresh environment, fresh DB, 11-row roster uploaded through the API
- [x] All 10 eligible students signed up, verified and logged in; 2 invalid
      PRN/email pairs rejected and flagged; the ineligible row refused
- [x] All 10 built full profiles (experience, projects, skills, resume);
      admin verified 5
- [x] Extraction spot-checked against the hand-verified reference for 5 students
- [x] 2 company accounts filtered by department, skill, CGPA range and project
      keyword; visibility held across hidden / shortlisted-only / all-companies
      for all 10
- [x] Edit and delete checked for success and failure, including a student
      attacking another student's entries
- [x] Load check: search 34ms median, filter 26ms median, bulk scoring 10
      resumes in 324ms
- [x] No 5xx responses and no tracebacks across 196 requests
- [x] Results recorded

### Carry into Phase 4

1. **The application flow is the only way a new company reaches a
   "shortlisted only" student.** A company can shortlist only a profile it can
   already see, so that visibility setting means "keep the companies already
   interested". Phase 4's applications must create the `CompanyShortlist`
   relationship, or those students stay unreachable. Locked down by
   `test_narrowing_to_shortlisted_keeps_the_companies_already_interested`.
2. **Login costs ~1s**, entirely Django's PBKDF2 hashing. Fine now; revisit if
   login volume during a drive makes it a bottleneck. The OTP path is the
   alternative.
3. **No headless browser drives the real UI.** The React suite runs in jsdom,
   which catches React errors, but nothing exercises the built app in a real
   browser. Worth closing before release.

---

## Resume intelligence (ahead of Phase B)

Built to [`RESUME_INTELLIGENCE_PLAN.md`](RESUME_INTELLIGENCE_PLAN.md) and tracked
item by item in [`RESUME_INTELLIGENCE_CHECKLIST.md`](RESUME_INTELLIGENCE_CHECKLIST.md).
Implementer agents marked items `[~]`; only a separate Opus verifier marked them
`[x]`. It lands in `matching/` (A2's surface) before Phase B, so Phase B's
`Opportunity` calls `get_engine().match_score(...)` and feeds `RoleCategory`
rather than building its own (see `agents/A2-opportunities.md`). Decisions are
D15–D22 in [`DECISIONS.md`](DECISIONS.md).

| Task | What | Commits |
| --- | --- | --- |
| 1 | Regex: ages and study durations are not experience; date ranges; word numbers; M.E./B.E.; age, DOB, emails, phones, CGPA for verification | `ac827c2`, `3e3113f` (also fixed Tasks 2–3), `dfc7232` |
| 2 | Llama (Ollama, local only) structured extraction, validated, experience recomputed from grounded dates | `1b48da2` |
| 3 | Embeddings, MongoDB `$vectorSearch` store, local fallback store | `736c460`, `5cd1f79` |
| 4 | Skill graph: aliases, implications, admin-approved alias suggestions | `11d9523`, `5c8a2ec`, `f31f58f`, `a13a481` |
| 5 | `ResumeAnalysis`, analyze/analysis endpoints, form suggestions, vector lifecycle | `fe5f54a`, `abf2a02` |
| 6 | 0–100 match score with breakdown; search, score and `me/match` | `fa9a5f6` |
| 7 | Role categories learnt from recruiters' JDs | `c7a7bd1`, `df87d1e` |
| 8 | Admin-only preliminary verification flags | `a2c60ed` |
| 9 | Frontend: analysis, match, categories, admin flags | `41724c0`, `140dea8`, `9de631e` |
| fixes | From verification rounds (V2, V5–V7, W1–W6) | `454ca14`, `6969b0c` |

**Migrations**, in dependency order, each in its own commit:
- matching `0001` StoredVector → `0002` skill graph → `0003` seed skills → `0004` RoleCategory → `0005` re-slug + C family
- profiles `0003` ResumeAnalysis → `0004` re-slug skills
- core `0003` `RESUME_ANALYSED` audit action

**Deploying it:**
1. `migrate`.
2. To turn the model on, set `LLM_ENABLED=true` and point `LLM_BASE_URL` at the college's Ollama server, then `ollama pull llama3.1:8b && ollama pull nomic-embed-text`. For MongoDB, set `MONGO_URI` and run `manage.py init_vector_index`. Both are opt-in compose profiles (`llm`, `vectors`).
3. With the LLM on, run `manage.py reindex_vectors` (full, not `--dirty-only`), then `manage.py recategorise`. The V1 slug change and the new skill edges invalidate existing vector metadata. With the LLM off, `reindex_vectors` exits with "nothing can be embedded"; skip it, because search falls back to the similarity backend.
4. **Configure a shared `CACHES` (Redis or Memcached) in production.** It is unset today, so the DRF throttles, the JD facts cache and the JD-recorded marker all count per worker process: with N workers the `matching` throttle is effectively N × 30/hour.

**Not yet verified in this environment** (no network, so no Ollama, MongoDB or `pymongo`):
- the live run in plan §5.4
- the provisional calibration for `nomic-embed-text` (0.40/0.85)
- `CATEGORY["MERGE_THRESHOLD"]` (0.75)
- the real MongoDB store, which is tested only against a fake collection

**Carried forward:**
- V3: bulk ORM writes skip the skill-graph cache signals; the 300 s TTL covers it.
- V4: the analysis time budget does not cap httpx's fixed 2 s connect timeout.
- `frontend/src/api/client.ts` `describeError` drops other keys when the body has a string `detail`, so `LoginPage`'s `needs_verification` check never fires (pre-existing; the page works through its 403 check).
- C/C++/C#: the canonical name of a merged `.NET` row stays `dotnet`; rename it in admin if wanted.
- X1: with the LLM off, a resume that *states* an inflated experience ("experience 40 years") is read as stated, and no flag fires, because the "not supported by dates" check needs the model's reading. Admins see the stated figure; the pre-fill asks the student to confirm it.
- X7: `ExperienceEntry.duration_months` counts end-exclusive (Jan–Jun = 5) while resume ranges count both end months (6), so the admin experience-gap check can warn falsely at the 6-month boundary.

---

## Addendum 2 — Stage 1: academics on the student form

Plan: `~/.claude/plans/addendem-2-1-add-a-sharded-quokka.md`. Four stages;
this is the first. Stages 2–4 (job postings + apply, suggestions, recruiter
exports) are not started.

**Done:**
- **School marksheets.** Class 10 and Class 12, each a file plus percentage,
  board and year of passing. Ten new fields on `StudentProfile` (migration
  `0007`), stored the way every other document on that model is: a `FileField`
  beside a `<field>_filename`, which is the shape `audited_document` resolves.
  PDF or a photo (PNG/JPG), through the shared `core.storage` validator —
  `validate_marksheet`, alongside the resume and transcript ones.
- **CGPA as its own entry.** No fifth CGPA column: `confirmed_cgpa` already
  meant "what the student says", and the only thing gating it was the UI, which
  showed the field solely when a transcript had failed to parse or a review was
  open. It is now its own card, always available, usable before any transcript
  exists. What the student types is a claim stored beside the roster's figure,
  the transcript's printed one and the recomputed one — it overwrites none.
- **The placement cell sees all four.** New `profiles.verification.cgpa_sources`
  returns every CGPA on record plus the pairs that disagree, surfaced on
  `AdminProfileDetailSerializer` and rendered with a badge per disagreeing
  source. Deliberately *not* routed through `matching.verification.compare`:
  that returns nothing until a resume has been read, so a student who stated a
  CGPA but uploaded no resume would have had their disagreement go unseen.
- **Closed a documented gap.** `profiles/verification.py` had
  `transcript_cgpa=None` with the comment "until stream A5's extractor lands".
  It landed; the printed CGPA is now passed through, and `compare` gained a
  fourth `student` source beside roster/transcript/resume.

**Deliberately not done:**
- Marksheets do **not** count toward `completion_percent`. The labels are
  duplicated by hand in `ProfilePage.tsx`, the frontend fixture carries seven
  keys against the backend's eight, and a test asserts the literal `0 of 7
  done`. Moving that denominator is its own piece of work.
- `Board` has an `OTHER` choice but no free-text detail field, unlike
  `career_path_detail`. Revisit if "Other" turns out to be common.
- No marksheet or transcript **file** is seeded. `seed_demo` fills the marks
  and the stated CGPA only: a seeded scan would be a document on record that
  no institution issued and nothing can be checked against.

**Checked:** backend suite, frontend 18 files / 145 tests, typecheck clean.
Two UI bugs were found by the new tests rather than by reading: a rejected
marksheet upload rendered no message at all (the error arrives under a `file`
key with no control bound to it), and the admin CGPA column lost its second
decimal once the values came from the server as numbers — `8.40` showing as
`8.4` in a column meant for comparison.
