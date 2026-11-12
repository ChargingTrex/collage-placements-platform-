# Smoke test results

Each phase's smoke test from [`agents.md`](agents.md), run for real, with the
output recorded here. A failing step blocks the next phase.

---

## Phase 0 — Scaffold & Environment

Run: 2026-09-21 · macOS 24.6.0 · Python 3.13.5 · Node 24.7.0

### 1. Fresh `.env`, standard bring-up

Database rebuilt from empty, migrations applied in order:

```
$ rm -f db.sqlite3 && python manage.py migrate --noinput
  Applying contenttypes.0001_initial... OK
  ... (18 migrations)
  Applying accounts.0001_initial... OK
  Applying core.0001_initial... OK
  Applying sessions.0001_initial... OK

$ python manage.py makemigrations --check --dry-run
No changes detected                       # exit 0 — no model drift

$ python manage.py check --deploy --fail-level ERROR
System check identified 6 issues (0 silenced)   # exit 0 — all W-level,
                                                # all expected under DEBUG
```

### 2. `/api/health` → 200 OK

```
$ curl http://127.0.0.1:8000/api/health
HTTP 200
{
  "status": "ok",
  "service": "placement-cell-portal",
  "debug": true,
  "checks": {
    "database":       { "ok": true, "engine": "sqlite" },
    "storage":        { "ok": true, "backend": "local", "location": ".../backend/media" },
    "matching_engine":{ "ok": true, "backend": "spacy", "detail": "en_core_web_md (300d vectors)" }
  }
}
```

### 3. Frontend root page renders, and reaches the API

```
$ curl http://localhost:5173/
root page HTTP 200                 # index.html served, #root present

$ curl http://localhost:5173/src/main.tsx
HTTP 200                           # module graph resolves

$ curl http://localhost:5173/api/health
proxied /api/health HTTP 200       # browser origin -> Vite proxy -> Django
```

Render correctness is asserted by the component tests rather than by eyeballing
the console:

```
$ npm test
 Test Files  1 passed (1)
      Tests  3 passed (3)
   - renders the portal heading
   - shows backend status once /api/health answers
   - tells the user how to start the backend when it is unreachable

$ npm run typecheck    # exit 0
$ npm run build        # exit 0, 262 kB / 83 kB gzipped
```

Backend suite:

```
$ pytest -q
......                             # 6 passed
```

Django request log across the whole run: no 500s, no tracebacks.

**Phase 0 smoke test: PASS** — proceeding to Phase 1.

> Note on `docker compose up`: the compose file, both Dockerfiles, and the
> Postgres service are committed and CI exercises the same code against
> PostgreSQL 16 on every push. The local bring-up above was run on the
> SQLite path, which is the agreed default for this prototype.

---

## Phase 1 — Roster & Authentication

Run: 2026-09-23 · fresh database, seeded admin + 2 company accounts, roster
cleared before the run.

### 4. Seeded admin account logs in and reaches the admin area

```
POST /auth/login (admin)  HTTP 200
  role: admin | prn: None | access token: eyJhbGciOiJIUzI1NiIsIn...
```

The admin has no PRN, as the PRD requires. The dashboard shell it lands on is
covered by the frontend tests (`admin-roster.test.tsx`), which assert the
roster count and open-flag count render.

### 1. Upload a test roster CSV (5 students)

```
POST /roster/upload  HTTP 200
{ "dry_run": false, "created": 5, "updated": 0, "unchanged": 0,
  "processed": 5, "error_count": 0, "errors": [] }
```

A deliberately broken file is also exercised by the test suite — bad rows come
back as `{"row": 3, "prn": "...", "errors": {"cgpa": ["..."]}}` with HTTP 207,
and the valid rows in the same file are still saved.

### 2. Sign up as a roster student → OTP → verify → login

```
POST /auth/signup  HTTP 201
{ "detail": "Verification code sent to aarav.mehta@college.edu.",
  "expires_at": "2026-09-23T06:26:59Z", "debug_otp": "362701",
  "prn": "PRN2022CS001", "email": "aarav.mehta@college.edu" }
```

The email actually sent (console backend):

```
Your verification code is 362701.
It expires in 10 minutes and can be used once.
If you did not request this, tell the placement cell — somebody may be
trying to use your PRN.
```

```
POST /auth/verify  HTTP 200
  activated: PRN2022CS001 - Aarav Mehta | is_verified: True

POST /auth/login (student, by PRN)  HTTP 200
GET  /auth/me                       HTTP 200
{ "email": "aarav.mehta@college.edu", "prn": "PRN2022CS001",
  "full_name": "Aarav Mehta", "role": "student", "is_verified": true }

POST /auth/otp/request  HTTP 200      # password-free login also works
POST /auth/otp/login    HTTP 200
```

### 3. Non-roster PRN/email pairs are rejected and flagged

Three distinct failure modes, each with its own reason so an admin can tell a
typo from an unknown PRN:

```
(a) PRN not on the roster        POST /auth/signup  HTTP 403  no_such_prn
(b) real PRN, wrong email        POST /auth/signup  HTTP 403  email_mismatch
(c) roster student, gmail.com    POST /auth/signup  HTTP 403  domain_not_allowed
```

All three appear in the admin's queue:

```
GET /roster/flagged?status=open  HTTP 200
  open flags: 3
    PRN2022IT004   sana.qureshi@gmail.com   Not a college email domain
    PRN2022CS002   impostor@college.edu     PRN is on the roster under a different email
    PRN9999XX999   ghost@college.edu        PRN not on the roster
```

And none of them produced an account:

```
    PRN2022CS001   Aarav Mehta        has_account=True
    PRN2022CS002   Diya Sharma        has_account=False
    PRN2022EC007   Vihaan Patil       has_account=False
    PRN2022IT004   Sana Qureshi       has_account=False
    PRN2022ME009   Arjun Deshmukh     has_account=False
  -> 1 of 5 roster students have an account
```

### Extra checks run alongside

```
Authorization
  student token -> /roster/students : HTTP 403
  anonymous     -> /roster/students : HTTP 401
  anonymous     -> /auth/me         : HTTP 401

OTP rate limiting (3 per 15 minutes per account; one was spent in step 2)
  request #1 : HTTP 200
  request #2 : HTTP 200
  request #3 : HTTP 429
  request #4 : HTTP 429
```

### Server log across the whole run

```
  12 x 200,  4 x 403,  2 x 429,  2 x 401,  1 x 201
  5xx responses: 0        tracebacks: 0
```

Every non-2xx is a deliberate refusal.

### Test suites

```
backend   pytest -q     69 passed
frontend  npm test      20 passed
          npm run typecheck   exit 0
          npm run lint        exit 0 (2 fast-refresh warnings, no errors)
```

**Phase 1 smoke test: PASS** — proceeding to Phase 2.

### Bugs found and fixed during this smoke test

1. **Flagged signups were being rolled back.** `register_student` was wrapped
   in `transaction.atomic`, so raising the rejection undid the `FlaggedSignup`
   and audit row it had just written — the queue was always empty. Caught by
   `test_repeat_attempts_collapse_into_one_flag_with_a_counter`.
2. **Half the API answered 301.** The DRF router minted trailing-slash URLs
   (`/api/roster/flagged/`) while every hand-written route is slashless. A GET
   survived the redirect; a POST with a body would not have. Router now uses
   `trailing_slash=False`.

---

## Phase 2 — Resume Parsing & Semantic Matching Engine

Run: 2026-09-23 · run twice, once per similarity backend, because CI runs
TF-IDF and a developer machine with the model runs spaCy.

Inputs: the five sample resumes rendered to real PDF and DOCX binaries by
`manage.py make_sample_resumes`, plus one backend-engineer job description.
The expected values live beside the resume text in `matching/samples.py`.

### 1. Five resumes (PDF + DOCX) and one job description go in

```
  aarav_mehta_backend.pdf            PDF     2062 bytes ->  672 chars
  sana_qureshi_data.docx             DOCX   36974 bytes ->  589 chars
  kabir_nair_frontend.pdf            PDF     1877 bytes ->  436 chars
  arjun_deshmukh_mechanical.docx     DOCX   36950 bytes ->  553 chars
  ishita_banerjee_marketing.pdf      PDF     1897 bytes ->  481 chars

  job description: 718 chars, backend engineer role
```

### 2. Extracted values vs the hand-checked reference

```
  resume                        experience          education
                             got  expected      got   expected
  backend_engineer           3.0       3.0       UG         UG   ok
  data_engineer              2.5       2.5  Masters    Masters   ok
  frontend_intern            0.5       0.5       UG         UG   ok
  mechanical_designer        4.0       4.0       UG         UG   ok
  marketing_executive        1.0       1.0       UG         UG   ok

  [PASS] all 5 match the hand-checked experience and education reference
```

Identical on both backends — extraction is regex-based and backend-independent.

### 3. Similarity ranking

spaCy (`en_core_web_md`, content words):

```
  1.  0.964  backend_engineer       (relevant)
  2.  0.926  data_engineer          (relevant)
  3.  0.847  frontend_intern        (not relevant)
  4.  0.836  mechanical_designer    (not relevant)
  5.  0.801  marketing_executive    (not relevant)
```

TF-IDF fallback:

```
  1.  0.237  backend_engineer       (relevant)
  2.  0.102  data_engineer          (relevant)
  3.  0.048  mechanical_designer    (not relevant)
  4.  0.018  frontend_intern        (not relevant)
  5.  0.014  marketing_executive    (not relevant)
```

```
  [PASS] the 2 relevant resumes rank above the 3 irrelevant ones  (both backends)
```

### 4. Hard filter: minimum 2 years of experience

```
  ranked after the filter:
     0.964  backend_engineer       exp=3.0y
     0.926  data_engineer          exp=2.5y
     0.836  mechanical_designer    exp=4.0y
  excluded by the filter:
        --  frontend_intern        Needs 2 years of experience; resume shows 0.5.
        --  marketing_executive    Needs 2 years of experience; resume shows 1.

  [PASS] both sub-2-year resumes are excluded
  [PASS] an excluded resume appears in no ranked list, whatever it scored
```

The mechanical designer survives the hard filter (4 years) and is correctly
still ranked last of the three — the filter and the score are independent, as
the PRD requires.

### 5. Changing the threshold changes the pass count

```
   threshold  shortlisted   below
         0.0            5       0
       0.835            4       1
       0.925            2       3
       0.963            1       4
         1.0            0       5

  [PASS] raising the threshold monotonically reduces the shortlist
```

And the shipped default, on each backend:

```
  spaCy   threshold 0.85 shortlists: ['backend_engineer', 'data_engineer']
  TF-IDF  threshold 0.10 shortlists: ['backend_engineer', 'data_engineer']

  [PASS] the default threshold shortlists exactly the 2 relevant resumes
```

### Test suites

```
backend (spaCy)   pytest -q                         164 passed
backend (TF-IDF)  MATCHING_BACKEND=tfidf pytest -q  164 passed
```

**Phase 2 smoke test: PASS on both backends** — proceeding to Phase 3.

### Findings during this phase

1. **The prototype's `b\.?e\.?` pattern matched the English word "be"**, so any
   resume containing ordinary prose was recorded as holding a bachelor's
   degree. Bare abbreviations are now matched case-sensitively.
2. **`m\.?s\.?` matched "MS Office", "MS SQL", "MS Teams"** — a skills list was
   enough to claim a master's. Those product names are now excluded.
3. **Experience was the largest number before the word "years" anywhere in the
   document**, so "4 year full-time degree" outranked "2 years experience".
   Durations adjacent to the word "experience" now win.
4. **The similarity scores were too bunched for the threshold to be useful.**
   Averaging spaCy vectors over every token let stopwords dominate: the whole
   sample set landed between 0.909 and 0.971, so the PRD's adjustable
   threshold had no useful range. Averaging over content words only widened
   that to 0.801–0.964, which is what makes the control worth exposing.
5. **The two backends do not share a scale.** A single hardcoded 0.6 would
   shortlist everybody on spaCy and nobody on TF-IDF, so each backend now
   carries its own suggested threshold and `DEFAULT_SIMILARITY_THRESHOLD`
   overrides it only when explicitly set.

---

## Phase 3 — Student Profile

Run: 2026-09-23 · fresh database, seeded roster and accounts, live API.

### 1. Log in as the seeded student, add 2 experience entries and 2 projects, upload a resume

```
  POST /profiles/me/experience  HTTP 201  Backend Intern
  POST /profiles/me/experience  HTTP 201  Teaching Assistant
  POST /profiles/me/projects    HTTP 201  Fleet tracker
  POST /profiles/me/projects    HTTP 201  Campus notice board
  POST /profiles/me/resume      HTTP 201  2062 bytes

  [PASS] 2 experience entries and 2 projects saved
```

### 2. Experience and education are pre-filled from the resume, and editable

```
  parser read       : 3.0 years, UG
  profile pre-filled: 3.0 years, UG
  awaiting the student's confirmation: True

  [PASS] experience and education are pre-filled from the resume
  [PASS] the pre-filled values are not yet treated as confirmed

  student corrects to 2.5 years -> HTTP 200, stored 2.5

  [PASS] the student can correct the pre-filled values
  [PASS] a later upload does not overwrite the student's correction
         — still 2.5, parser said 3.0
```

That last check is the one worth keeping: the parsed value is a suggestion,
the student's correction is the record, and re-uploading records the new
reading without quietly undoing the correction.

### 3. Visibility "hidden" — the company cannot find the profile

```
  PUT /profiles/me/visibility hidden  HTTP 200
  GET /profiles/students              HTTP 200  -> 0 results
  GET /profiles/students/PRN2022CS001 HTTP 404  (direct fetch)

  [PASS] a hidden profile is absent from the company's search
  [PASS] a hidden profile cannot be fetched directly either
```

The second check matters: an empty list proves only that the UI filtered it.
The detail route refusing a PRN the company already knows proves the rule is
in the queryset.

### 4. Visibility "all companies" — found, with the right data

```
  GET /profiles/students  HTTP 200  -> 1 result
    Aarav Mehta (PRN2022CS001) — Backend developer
    department Computer Engineering, CGPA 8.72, 2.5 yrs
    skills   : Django, PostgreSQL, Python
    projects : Campus notice board, Fleet tracker

  filters:
    department                 -> 1 result(s)
    skills python,django       -> 1 result(s)
    CGPA 8.0-9.0               -> 1 result(s)
    project keyword 'fleet'    -> 1 result(s)
    skills that nobody has     -> 0 result(s)

  contact details before verification: None

  [PASS] the company now finds the profile with the correct data
  [PASS] every PRD filter returns the expected profile
  [PASS] contact details are withheld on an unverified profile
```

### 5. Admin marks the profile verified — the badge reaches the company view

```
  POST /profiles/admin/PRN2022CS001/verification  HTTP 200
  GET  /profiles/students/PRN2022CS001            HTTP 200
    is_verified : True
    verified_at : 2026-09-23T23:58:42+05:30
    contact     : {'email': 'aarav.mehta@college.edu', 'phone': '9820011001'}

  [PASS] the verified badge appears on the company-facing view
  [PASS] contact details are released once verified
```

### Authorization checks run alongside

```
  another student edits my experience entry  : HTTP 404
  another student deletes my experience entry: HTTP 404
  a student verifies their own profile       : HTTP 403
  anonymous browses student profiles         : HTTP 401
```

404 rather than 403 on another student's entry is deliberate — a 403 would
confirm the entry exists.

### Server log across the run

```
  25 x 200, 11 x 201, 3 x 404, 1 x 403, 1 x 401
  5xx responses: 0        tracebacks: 0
```

### Test suites

```
backend   pytest -q              246 passed
frontend  npm test                39 passed
          npm run typecheck   exit 0
          npm run lint        exit 0 (4 fast-refresh warnings, no errors)
          npm run build       exit 0
```

**Phase 3 smoke test: PASS** — proceeding to the halfway E2E checkpoint.

---

## HALFWAY CHECKPOINT — Full E2E Test (after Phase 3)

Run: 2026-09-24 · fresh database, roster uploaded through the API, 196
requests against the live server. **30 of 30 checks passed.**

### 1. Fresh environment, fresh DB, roster of 10+ synthetic students

```
  POST /roster/upload HTTP 200
  {'created': 11, 'updated': 0, 'unchanged': 0, 'processed': 11, 'error_count': 0}

  [PASS] roster CSV uploaded with no rejected rows
  [PASS] 10 placement-eligible students on the roster
         — 11 rows total, 1 not eligible
```

### 2. All 10 sign up, verify and log in; 2 invalid pairs are rejected

```
  10 of 10 students signed up, verified and logged in
  PRN9999XX999 / ghost@college.edu     -> HTTP 403 (no_such_prn)
  PRN2022CS002 / impostor@college.edu  -> HTTP 403 (email_mismatch)

  [PASS] every eligible roster student completed signup -> verify -> login
  [PASS] both deliberately-invalid PRN/email pairs are rejected
  [PASS] both rejected pairs appear in the admin's flagged queue
  [PASS] a roster row marked not placement-eligible cannot sign up
```

### 3. Each student builds a full profile; admin verifies at least half

```
  10 of 10 profiles have experience, projects, skills and a resume
  admin verified 5 of 10 profiles

  [PASS] every student built a full profile
  [PASS] admin verified at least half the profiles
```

### 4. Resume extraction spot-checked against hand-verified values

```
  PRN              sample                     experience        education
                                           got     want      got     want
  PRN2022CS001     backend_engineer         3.0      3.0       UG       UG   ok
  PRN2022CS002     data_engineer            2.5      2.5  Masters  Masters   ok
  PRN2022CS003     frontend_intern          0.5      0.5       UG       UG   ok
  PRN2022EC007     mechanical_designer      4.0      4.0       UG       UG   ok
  PRN2022EC008     marketing_executive      1.0      1.0       UG       UG   ok

  [PASS] extraction matches the hand-verified reference for 5 students
```

### 5. Two companies search and filter; visibility holds across all 10

Visibility was spread across all three settings, with company A having
shortlisted its students while they were still public:

```
  company A shortlisted 3 students while they were public
  visibility spread after each student chose: {'all': 4, 'shortlisted': 3, 'hidden': 3}

  company A (shortlisted them)  sees 7: expected 7
  company B (shortlisted nobody) sees 4: expected 4

  [PASS] company A sees all-companies plus its own shortlisted students
  [PASS] company B sees only all-companies students
  [PASS] no hidden profile is visible to either company
  [PASS] a hidden profile cannot be fetched directly
  [PASS] one company's shortlist does not expose the profile to another
  [PASS] a company cannot shortlist its way into a profile it cannot see

  filters (company A):
    department=Computer Engineering    ->  2 result(s)  within visible set
    skills=python                      ->  3 result(s)  within visible set
    skills=python,django               ->  1 result(s)  within visible set
    cgpa 8.0-9.2                       ->  4 result(s)  within visible set
    project keyword                    ->  7 result(s)  within visible set
    verified only                      ->  4 result(s)  within visible set

  [PASS] every filter stays inside the visible set
```

### 6. Edit and delete flows, success and failure

```
  [PASS] a student edits their own experience entry
  [PASS] another student editing that entry is rejected        (404)
  [PASS] another student deleting that entry is rejected       (404)
  [PASS] the entry survived both hostile attempts
  [PASS] a student deletes their own project
  [PASS] an invalid entry is refused with a validation error   (400)
  [PASS] a student cannot verify their own profile             (403)
  [PASS] a company cannot reach the admin profile list         (403)
```

### 7. Load check at the seeded roster size

```
  operation                        n    median       p95       max
  ----------------------------------------------------------------
  filter                          16     25.7ms    787.7ms   787.7ms
  login                           13   1047.1ms   1205.1ms  1205.1ms
  resume_upload                   10     37.7ms     65.0ms    65.0ms
  search                          12     33.7ms     59.6ms    59.6ms
  signup                          10     15.8ms     30.6ms    30.6ms
  bulk scoring (spacy)            10    323.9ms

  shortlisted 4 of 10 at threshold 0.85:
    PRN2022CS001, PRN2022IT004, PRN2022CS002, PRN2022IT005

  [PASS] profile search responds in under 500ms  — median 34ms over 12 calls
  [PASS] filtered search responds in under 500ms — median 26ms over 16 calls
  [PASS] bulk scoring 10 resumes under 5s        — 324ms on the spaCy backend
  [PASS] bulk screening ranks the backend-relevant resumes first
```

**Login is the one operation over 500ms, at ~1s.** That is Django's PBKDF2
password hashing (870k iterations) doing its job, not a query problem — it is
deliberate cost, and it is why the OTP path exists alongside it. Worth
revisiting only if login volume during a drive makes it a bottleneck.

The 787ms filter outlier is the first request after the spaCy model loads in
the same process; subsequent filters sit at ~25ms.

### 8. No console errors, no unhandled 500s

```
  server log across 196 requests:
    93 x 201, 90 x 200, 6 x 404, 5 x 403, 1 x 400, 1 x 204
    5xx responses: 0        tracebacks: 0
```

Every non-2xx is a deliberate refusal asserted by a check above.

Frontend console errors: the React suite runs in jsdom, which surfaces React
errors and unhandled rejections as test failures; all 39 pass. No headless
browser drove the real UI in this run — that is a gap worth closing before
release, and it is noted in `PROGRESS.md`.

### 9. Result

```
  Section 1: 3/3    Section 5: 8/8
  Section 2: 4/4    Section 6: 8/8
  Section 3: 2/2    Section 7: 4/4
  Section 4: 1/1

  TOTAL: 30/30 checks passed
```

**HALFWAY CHECKPOINT: PASS**

### Finding: what "shortlisted only" actually means

The first run failed one check — company A saw 4 profiles where 7 were
expected. The cause was the order of operations, and it exposed a real
property of the rule rather than a bug:

A company can only shortlist a profile it can already see. So if a student
switches to "shortlisted only" *before* any company has shortlisted them, no
company can ever reach them — the setting is a permanent hide.

Read the other way round, the rule is exactly right: **"shortlisted only"
means "keep the companies already interested, drop everyone else."** A
company that has never seen the profile cannot shortlist its way in, which is
the protection the student is asking for.

The consequence for Phase 4: **the application flow is the only legitimate way
a new company reaches a "shortlisted only" student.** A student applies, the
company gains a relationship, and the profile becomes visible to them. That
dependency is now recorded in `PROGRESS.md`, and the sequence is locked down
by a regression test
(`test_narrowing_to_shortlisted_keeps_the_companies_already_interested`).

---

## Follow-up — a way back out of "shortlisted only"

Run: 2026-09-24 · live API, fresh database.

The halfway checkpoint established that a student who picks "shortlisted only"
before any company has shortlisted them is invisible to everyone. The student
was never actually *stuck* — `MyVisibilityView` reads their own profile
directly and never passes through the visibility rule, so switching back
always worked. The problem was that nothing said so: from the student's side,
"shortlisted only" with nobody shortlisted looks identical to being visible.

What changed: the profile now reports `shortlisted_by_count`, the visibility
control warns when that number is zero, and one button returns the profile to
"all companies".

```
  1. student picks 'shortlisted only' with nobody shortlisted
     shortlisted_by_count = 0  -> the UI now warns
     companies who can see the profile: 0

  2. a company tries to shortlist its way in      -> HTTP 404 (refused, by design)

  3. student clicks 'make visible to all'         -> HTTP 200, now 'all'
     companies who can see the profile: 1

  4. company shortlists, student narrows again
     shortlisted_by_count = 1  -> no warning shown
     companies who can see the profile: 1  (the interested one keeps access)
```

Step 2 is deliberate and stays that way: letting a stranger shortlist its way
in would defeat the setting. Step 4 is the sequence the setting exists for.

Locked down by:

- `profiles/tests/test_own_profile.py::TestVisibilityToggle::test_a_student_can_always_switch_back_out_of_shortlisted_only`
- `profiles/tests/test_own_profile.py::TestVisibilityToggle::test_the_student_is_told_how_many_companies_shortlisted_them`
- four cases in `frontend/src/test/student-profile.test.tsx` covering the
  warning, its absence when companies have shortlisted, the one-click return,
  and the plain "hidden" case

```
backend   pytest -q     249 passed
frontend  npm test       43 passed
          typecheck / lint / build   exit 0
```


---

## Resume intelligence: final gate (2026-10-19)

Run: 2026-10-19 · opus-verifier · the gate in `RESUME_INTELLIGENCE_PLAN.md` §5, at
`HEAD` `7acd92a` (code under the gate: `6969b0c`, `9de631e`). Backend commands run
from `backend/` with `-p no:cacheprovider -o addopts=--strict-markers`. The other
session's uncommitted edits (tests, fixtures, `core/filters.py`, `SignupPage.tsx`)
were in the tree; nothing failed, so nothing is external, and the frontend was
also run in a clean `HEAD` worktree.

### 1. Test suites

```
$ ../.venv/bin/pytest                                   # default backend: spacy
919 passed, 1 skipped in 296.05s (0:04:56)

$ MATCHING_BACKEND=tfidf ../.venv/bin/pytest
919 passed, 1 skipped in 288.95s (0:04:48)

$ ../.venv/bin/pytest matching profiles                 # plan §5.2, spacy
850 passed, 1 skipped in 263.31s (0:04:23)

$ MATCHING_BACKEND=tfidf ../.venv/bin/pytest matching profiles
850 passed, 1 skipped in 258.85s (0:04:18)

$ ../.venv/bin/pytest matching/tests/test_extractors.py -q   # plan §5.1
158 passed in 0.78s
```

The one skip on each run is the real-MongoDB round trip (`MONGO_URI` unset).

```
$ npx vitest run                                        # frontend/
 Test Files  10 passed (10)
      Tests  91 passed (91)
  (second run: Tests 91 passed (91); clean HEAD worktree: Tests 91 passed (91))

$ npm run typecheck
> frontend@0.0.0 typecheck
> tsc --noEmit -p tsconfig.app.json

exit 0

$ npm run lint
> frontend@0.0.0 lint
> oxlint

src/auth/AuthContext.tsx:69:17: warning react(only-export-components): Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
src/auth/AuthContext.tsx:76:17: warning react(only-export-components): Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
src/pages/company/StudentSearchPage.tsx:79:10: warning react(set-state-in-effect): Calling setState synchronously within an effect can trigger cascading renders help: Effects should synchronize React with external systems. Calling setState synchronously inside an effect starts another render and is usually unnecessary. Derive the value during render, initialize state directly, or update it from the event that caused the change. Use an effect only when synchronizing with an external system.
src/pages/student/ProfilePage.tsx:65:10: warning react(set-state-in-effect): Calling setState synchronously within an effect can trigger cascading renders help: Effects should synchronize React with external systems. Calling setState synchronously inside an effect starts another render and is usually unnecessary. Derive the value during render, initialize state directly, or update it from the event that caused the change. Use an effect only when synchronizing with an external system.
exit 0
```

The four lint warnings are the pre-existing ones.

### 2. Migrations and extraction accuracy

```
$ ../.venv/bin/python manage.py makemigrations --check --dry-run
No changes detected

$ DATABASE_URL=sqlite:///<scratchpad>/gate.sqlite3 ../.venv/bin/python manage.py migrate
Operations to perform:
  Apply all migrations: accounts, admin, auth, contenttypes, core, matching, profiles, roster, sessions, token_blacklist
Running migrations:
  Applying core.0003_auditlog_resume_analysed... OK
  Applying matching.0001_initial... OK
  Applying matching.0002_skill_graph... OK
  Applying matching.0003_seed_skills... OK
  Applying matching.0004_role_category... OK
  Applying matching.0005_reslug_skills_seed_c_family... OK
  Applying profiles.0003_resume_analysis... OK
  Applying profiles.0004_reslug_skills... OK
  [excerpt: the resume-intelligence migrations; 50 "Applying ... OK" lines in all, no failure]

$ DATABASE_URL=sqlite:///<scratchpad>/gate.sqlite3 ../.venv/bin/python manage.py eval_extraction
Extraction accuracy on 10 hand-checked sample resumes

field        scored        regex
experience       10   10/10 100%
education        10   10/10 100%
age               1     1/1 100%
cgpa              2     2/2 100%

Misses: none
exit 0
```

### 3. Contract tests (plan §5.3), both backends

```
== spacy
PASSED profiles/tests/test_matching_api.py::TestVisibility::test_hidden_and_unshortlisted_profiles_never_appear_even_when_the_store_returns_them
PASSED profiles/tests/test_matching_api.py::TestVisibility::test_the_fallback_search_respects_visibility_too
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_search_results_carry_no_age_dob_resume_cgpa_or_flags[off]
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_search_results_carry_no_age_dob_resume_cgpa_or_flags[on]
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_scored_results_carry_none_of_it_either
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_the_students_own_match_carries_none_of_it
PASSED profiles/tests/test_resume_analysis.py::TestPrivacy::test_a_student_payload_never_carries_age_dob_cgpa_phones_or_emails
PASSED profiles/tests/test_resume_analysis.py::TestPrivacy::test_the_facts_are_still_stored_for_admins
PASSED profiles/tests/test_resume_analysis.py::TestPrivacy::test_the_audit_row_holds_no_resume_content
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_students_own_profile
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_company_list_detail_and_search
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_analyze_and_analysis_responses
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_upload_response
PASSED matching/tests/test_llm.py::TestResumeFacts::test_invalid_json_is_retried_once_with_the_error
PASSED matching/tests/test_llm.py::TestResumeFacts::test_two_invalid_replies_raise_unavailable
PASSED matching/tests/test_llm.py::TestEngineAnalysis::test_an_unreachable_server_falls_back_to_regex
PASSED matching/tests/test_llm.py::TestEngineAnalysis::test_an_injected_claim_cannot_inflate_the_engines_reading
PASSED matching/tests/test_extractors.py::TestDateRanges::test_resume_instructions_cannot_inflate_the_range_total
PASSED matching/tests/test_verification.py::TestCgpa::test_a_resume_cgpa_above_the_roster_is_a_warning_naming_both
PASSED matching/tests/test_verification.py::TestCgpa::test_a_gap_within_the_tolerance_raises_nothing
PASSED matching/tests/test_verification.py::TestCgpa::test_the_tolerance_comes_from_settings
PASSED matching/tests/test_verification.py::TestCgpa::test_the_three_way_comparison_names_each_disagreeing_pair
PASSED matching/tests/test_verification.py::TestCgpa::test_a_transcript_that_disagrees_with_the_roster_is_flagged_without_a_resume_value
PASSED matching/tests/test_verification.py::TestCgpa::test_with_the_llm_off_the_regex_cgpa_is_the_resume_value
PASSED matching/tests/test_verification.py::TestCgpa::test_the_models_cgpa_wins_over_the_regex_reading
PASSED matching/tests/test_verification.py::TestCgpa::test_no_roster_cgpa_and_no_transcript_leaves_nothing_to_compare
26 passed in 9.74s
== tfidf
PASSED profiles/tests/test_matching_api.py::TestVisibility::test_hidden_and_unshortlisted_profiles_never_appear_even_when_the_store_returns_them
PASSED profiles/tests/test_matching_api.py::TestVisibility::test_the_fallback_search_respects_visibility_too
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_search_results_carry_no_age_dob_resume_cgpa_or_flags[off]
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_search_results_carry_no_age_dob_resume_cgpa_or_flags[on]
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_scored_results_carry_none_of_it_either
PASSED profiles/tests/test_matching_api.py::TestPrivacy::test_the_students_own_match_carries_none_of_it
PASSED profiles/tests/test_resume_analysis.py::TestPrivacy::test_a_student_payload_never_carries_age_dob_cgpa_phones_or_emails
PASSED profiles/tests/test_resume_analysis.py::TestPrivacy::test_the_facts_are_still_stored_for_admins
PASSED profiles/tests/test_resume_analysis.py::TestPrivacy::test_the_audit_row_holds_no_resume_content
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_students_own_profile
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_company_list_detail_and_search
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_analyze_and_analysis_responses
PASSED profiles/tests/test_verification_flags.py::TestNoOtherPayloadCarriesThem::test_the_upload_response
PASSED matching/tests/test_llm.py::TestResumeFacts::test_invalid_json_is_retried_once_with_the_error
PASSED matching/tests/test_llm.py::TestResumeFacts::test_two_invalid_replies_raise_unavailable
PASSED matching/tests/test_llm.py::TestEngineAnalysis::test_an_unreachable_server_falls_back_to_regex
PASSED matching/tests/test_llm.py::TestEngineAnalysis::test_an_injected_claim_cannot_inflate_the_engines_reading
PASSED matching/tests/test_extractors.py::TestDateRanges::test_resume_instructions_cannot_inflate_the_range_total
PASSED matching/tests/test_verification.py::TestCgpa::test_a_resume_cgpa_above_the_roster_is_a_warning_naming_both
PASSED matching/tests/test_verification.py::TestCgpa::test_a_gap_within_the_tolerance_raises_nothing
PASSED matching/tests/test_verification.py::TestCgpa::test_the_tolerance_comes_from_settings
PASSED matching/tests/test_verification.py::TestCgpa::test_the_three_way_comparison_names_each_disagreeing_pair
PASSED matching/tests/test_verification.py::TestCgpa::test_a_transcript_that_disagrees_with_the_roster_is_flagged_without_a_resume_value
PASSED matching/tests/test_verification.py::TestCgpa::test_with_the_llm_off_the_regex_cgpa_is_the_resume_value
PASSED matching/tests/test_verification.py::TestCgpa::test_the_models_cgpa_wins_over_the_regex_reading
PASSED matching/tests/test_verification.py::TestCgpa::test_no_roster_cgpa_and_no_transcript_leaves_nothing_to_compare
26 passed in 8.68s
```

The malformed-JSON chain is pinned at two seams. Composed in one probe
(two malformed replies into `MatchingEngine.analyse_resume`), on both backends:

```
prompts: 2 | retry carried the error: True | source: regex | years: 0.5 | levels: {'UG'}
1 passed
```

### 4. Fixes under the gate (`6969b0c`), re-run

W1, LLM off, `MatchingEngine.job_requirements(jd)["min_experience_years"]`:

```
history                  find_required=None   job_requirements.min=None
internship               find_required=None   job_requirements.min=None
bond                     find_required=None   job_requirements.min=None
intern+bond              find_required=None   job_requirements.min=None
requires 2+              find_required=2.0    job_requirements.min=2.0
minimum 3                find_required=3.0    job_requirements.min=3.0
SAMPLE_JOB_DESCRIPTION   find_required=2.0    job_requirements.min=2.0
ctc                      find_required=None   job_requirements.min=None
bond2                    find_required=None   job_requirements.min=None
ppo                      find_required=None   job_requirements.min=None
0-2 yrs                  find_required=None   job_requirements.min=None
freshers                 find_required=None   job_requirements.min=None
2-4 yrs                  find_required=None   job_requirements.min=None
at least 1               find_required=1.0    job_requirements.min=1.0
exp of 3                 find_required=3.0    job_requirements.min=3.0
we need 2                find_required=2.0    job_requirements.min=2.0
trainee 1yr              find_required=None   job_requirements.min=None
intern+bond match: {'score': 92, 'components': {'semantic': {'score': 0.824, 'weight': 0.45, 'raw': 0.206}, 'skills': {'score': 1.0, 'weight': 0.35}, 'experience': {'score': 1.0, 'weight': 0.1}, 'education': {'score': 1.0, 'weight': 0.1}}, 'matched_skills': ['Python', 'Django'], 'missing_skills': [], 'hard_filter_failures': [], 'flagged': False, 'semantic_source': 'tfidf'}
```

W2–W6 and V5 through the DRF test client. `score` takes no `filters`, so that
key is ignored there.

```
W2 21 values on categories: 400 {'filters': {'categories': "'in' takes at most 20 values."}}
W2 21 values on skills: 400 {'filters': {'skills': "'in' takes at most 20 values."}}
W2 21 values on department: 400 {'filters': {'department': "'in' takes at most 20 values."}}
W2 21 values on batch: 400 {'filters': {'batch': "'in' takes at most 20 values."}}
W2 21 values on education_level: 400 {'filters': {'education_level': "'in' takes at most 20 values."}}
W2 score with 21-value filter: 200 b'{"count":0,"job":{"canonical_role":null,"required_skills":["Django","PostgreSQL","Python","Django REST Framework","SQL","Git","Docker","AWS"],"min_experience_years":2.0,"education_levels":["UG"],"sour'
W2 100,000 values: 400 in 0.057s, 1 queries
W2 resolve 20 names: 1 query; ['Backend Engineer', 'Backend Engineer', 'Data Analyst', 'nope']
W2 search queries, 1 vs 20 category values: {1: 6, 5: 6, 20: 6}
W3 student me/match 200 -> categories 0; company search 200 -> [('Backend Engineer', 1)]; again 200 -> [('Backend Engineer', 1)]
W4 search 200; stored name len 80: 'alert(1) AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'...
W4 variant names lengths: [80, 84] 'AA (2)'
W5 C.absorb(A,B): model m, count 4, centroid [0.75, 0.25], jd_count 5
W5 A.absorb(B,C): model m, count 4, centroid [0.75, 0.25]
W5 admin merge -> [('A', 5, 'm', 4, [0.75, 0.25])]
W6 admin list query counts by rows: {3: 6, 9: 6, 15: 6} ; shortlisted_by_count sample: [0, 1]
V5 upload 201, analyze 200 done; vectors 1; same resume again 201 -> 1; different resume 201 -> 0; analysis status pending, categories []
15 passed in 5.43s
```

### 5. Fallback run (plan §5.5): LLM off, no MongoDB, local store, fresh DB

```
$ env -u MONGO_URI DATABASE_URL=sqlite:///<scratchpad>/fallback.sqlite3 LLM_ENABLED=false \
      VECTOR_STORE_BACKEND=local ../.venv/bin/python <scratchpad>/fallback_run.py
engine backend: spacy
llm_enabled(): False  MONGO_URI: ''
vector store: LocalVectorStore
roster upload: 200 {'dry_run': False, 'created': 6, 'updated': 0, 'unchanged': 0, 'processed': 6, 'error_count': 0}

analyze results (LLM off):
  student                upload   status  source  retryable experience_years  education_level
  backend_engineer       pending  done    regex   False     3.0               UG
  data_engineer          pending  done    regex   False     2.5               Masters
  frontend_intern        pending  done    regex   False     0.5               UG
  mechanical_designer    pending  done    regex   False     4.0               UG
  marketing_executive    pending  done    regex   False     1.0               UG
  biotech_masters        pending  done    regex   False     0.5               Masters
  analyze keys: ['agreement', 'analysed_at', 'categories', 'education_level', 'experience_years', 'model_name', 'retryable', 'source', 'status', 'suggested_experience', 'suggested_skills']
  ResumeAnalysis rows: [('done', 'regex'), ('done', 'regex'), ('done', 'regex'), ('done', 'regex'), ('done', 'regex'), ('done', 'regex')]
  StoredVector rows (no embedder, so none): 0

student me/match: 200 score 95 missing [] failures []

company search: 200 fallback: True count: 6 keys: ['count', 'fallback', 'job', 'results']
  job: {'canonical_role': None, 'required_skills': ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'], 'min_experience_years': 2.0, 'education_levels': ['UG'], 'source': 'text'}
  rank prn        score semantic skills experience education  matched / missing / hard-filter failures
  1    260210001  95    0.8941   1.0    1.0        1.0        ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / [] / []
  2    260210002  77    0.6941   0.75   1.0        1.0        ['Django', 'PostgreSQL', 'Python', 'SQL', 'Git', 'Docker'] / ['Django REST Framework', 'AWS'] / []
  3    260210004  26    0.1353   0.0    1.0        1.0        [] / ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / []
  4    260210005  22    0.1647   0.0    0.5        1.0        [] / ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / ['Needs 2 years of experience; resume shows 1.']
  5    260210003  21    0.1941   0.0    0.25       1.0        [] / ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / ['Needs 2 years of experience; resume shows 0.5.']
  6    260210006  17    0.0      0.125  0.25       1.0        ['Python'] / ['Django', 'PostgreSQL', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / ['Needs 2 years of experience; resume shows 0.5.']
  admin-only keys in the company payload: none
  top two: ['260210001', '260210002'] (backend 260210001 and data 260210002 expected)
  categories (cold start, LLM off): {'count': 0, 'next': None, 'previous': None, 'results': []}

admin list: 200
  260210001  warning_count 2  warnings ['experience_years', 'experience_years']  info []
  260210002  warning_count 2  warnings ['experience_years', 'experience_years']  info []
  260210003  warning_count 0  warnings []  info []
  260210004  warning_count 2  warnings ['experience_years', 'experience_years']  info []
  260210005  warning_count 2  warnings ['experience_years', 'experience_years']  info []
  260210006  warning_count 1  warnings ['cgpa']  info []
admin detail 260210006: 200 warning_count 1
    {'field': 'cgpa', 'severity': 'warning', 'sources': ['roster', 'resume'], 'values': {'roster': 7.4, 'resume': 8.6}, 'message': 'The roster CGPA (7.4) and the resume CGPA (8.6) differ by more than 0.1.'}
admin marks it verified despite the warning: 200 True

request log:
  200  admin      POST /api/auth/login
  200  admin      POST /api/roster/upload  (6 rows)
  201  260210001  POST /api/auth/signup
  200  260210001  POST /api/auth/verify  (OTP from mail)
  200  260210001  POST /api/auth/login
  200  260210001  GET /api/profiles/me
  200  260210001  PATCH /api/profiles/me
  201  260210001  POST /api/profiles/me/skills
  201  260210001  POST /api/profiles/me/skills
  201  260210001  POST /api/profiles/me/experience
  201  260210001  POST /api/profiles/me/projects
  201  260210001  POST /api/profiles/me/resume  (aarav_mehta_backend.pdf)
  200  260210001  POST /api/profiles/me/resume/analyze
  200  260210001  GET /api/profiles/me/resume/analysis
  201  260210002  POST /api/auth/signup
  200  260210002  POST /api/auth/verify  (OTP from mail)
  200  260210002  POST /api/auth/login
  200  260210002  GET /api/profiles/me
  200  260210002  PATCH /api/profiles/me
  201  260210002  POST /api/profiles/me/skills
  201  260210002  POST /api/profiles/me/skills
  201  260210002  POST /api/profiles/me/experience
  201  260210002  POST /api/profiles/me/projects
  201  260210002  POST /api/profiles/me/resume  (sana_qureshi_data.docx)
  200  260210002  POST /api/profiles/me/resume/analyze
  200  260210002  GET /api/profiles/me/resume/analysis
  201  260210003  POST /api/auth/signup
  200  260210003  POST /api/auth/verify  (OTP from mail)
  200  260210003  POST /api/auth/login
  200  260210003  GET /api/profiles/me
  200  260210003  PATCH /api/profiles/me
  201  260210003  POST /api/profiles/me/skills
  201  260210003  POST /api/profiles/me/skills
  201  260210003  POST /api/profiles/me/experience
  201  260210003  POST /api/profiles/me/projects
  201  260210003  POST /api/profiles/me/resume  (kabir_nair_frontend.pdf)
  200  260210003  POST /api/profiles/me/resume/analyze
  200  260210003  GET /api/profiles/me/resume/analysis
  201  260210004  POST /api/auth/signup
  200  260210004  POST /api/auth/verify  (OTP from mail)
  200  260210004  POST /api/auth/login
  200  260210004  GET /api/profiles/me
  200  260210004  PATCH /api/profiles/me
  201  260210004  POST /api/profiles/me/skills
  201  260210004  POST /api/profiles/me/skills
  201  260210004  POST /api/profiles/me/experience
  201  260210004  POST /api/profiles/me/projects
  201  260210004  POST /api/profiles/me/resume  (arjun_deshmukh_mechanical.docx)
  200  260210004  POST /api/profiles/me/resume/analyze
  200  260210004  GET /api/profiles/me/resume/analysis
  201  260210005  POST /api/auth/signup
  200  260210005  POST /api/auth/verify  (OTP from mail)
  200  260210005  POST /api/auth/login
  200  260210005  GET /api/profiles/me
  200  260210005  PATCH /api/profiles/me
  201  260210005  POST /api/profiles/me/skills
  201  260210005  POST /api/profiles/me/skills
  201  260210005  POST /api/profiles/me/experience
  201  260210005  POST /api/profiles/me/projects
  201  260210005  POST /api/profiles/me/resume  (ishita_banerjee_marketing.pdf)
  200  260210005  POST /api/profiles/me/resume/analyze
  200  260210005  GET /api/profiles/me/resume/analysis
  201  260210006  POST /api/auth/signup
  200  260210006  POST /api/auth/verify  (OTP from mail)
  200  260210006  POST /api/auth/login
  200  260210006  GET /api/profiles/me
  200  260210006  PATCH /api/profiles/me
  201  260210006  POST /api/profiles/me/skills
  201  260210006  POST /api/profiles/me/skills
  201  260210006  POST /api/profiles/me/experience
  201  260210006  POST /api/profiles/me/projects
  201  260210006  POST /api/profiles/me/resume  (nandini_rao_biotech.docx)
  200  260210006  POST /api/profiles/me/resume/analyze
  200  260210006  GET /api/profiles/me/resume/analysis
  200  260210001  POST /api/profiles/me/match
  200  company    POST /api/auth/login
  200  company    POST /api/matching/search  (SAMPLE_JOB_DESCRIPTION)
  200  company    GET /api/matching/categories
  200  admin      GET /api/profiles/admin
  200  admin      GET /api/profiles/admin/27dceda1-6349-4f30-bf55-0837f299a018
  200  admin      POST /api/profiles/admin/27dceda1-6349-4f30-bf55-0837f299a018/verification

status counts: {200: 45, 201: 36} | requests: 81
5xx: 0
server errors logged: none
```

Each student's form carries one 2024-01-01 to 2024-06-30 internship, so the
`experience_years` warnings for the four students whose resumes show 1 year or
more are mostly expected. The one for 260210005 (1.0 years) is not: the form
counts that entry as 5 months and the resume extractor counts the same span as
6, so a 6-month gap reads as 7. That is finding X7 (minor) in the checklist.

The same run on TF-IDF (`MATCHING_BACKEND=tfidf`, its own fresh DB):

```
engine backend: tfidf
company search: 200 fallback: True count: 6 keys: ['count', 'fallback', 'job', 'results']
  job: {'canonical_role': None, 'required_skills': ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'], 'min_experience_years': 2.0, 'education_levels': ['UG'], 'source': 'text'}
  rank prn        score semantic skills experience education  matched / missing / hard-filter failures
  1    260210001  95    0.896    1.0    1.0        1.0        ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / [] / []
  2    260210002  63    0.38     0.75   1.0        1.0        ['Django', 'PostgreSQL', 'Python', 'SQL', 'Git', 'Docker'] / ['Django REST Framework', 'AWS'] / []
  3    260210004  28    0.172    0.0    1.0        1.0        [] / ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / []
  4    260210006  20    0.076    0.125  0.25       1.0        ['Python'] / ['Django', 'PostgreSQL', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / ['Needs 2 years of experience; resume shows 0.5.']
  5    260210005  17    0.052    0.0    0.5        1.0        [] / ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / ['Needs 2 years of experience; resume shows 1.']
  6    260210003  15    0.064    0.0    0.25       1.0        [] / ['Django', 'PostgreSQL', 'Python', 'Django REST Framework', 'SQL', 'Git', 'Docker', 'AWS'] / ['Needs 2 years of experience; resume shows 0.5.']
  admin-only keys in the company payload: none
  top two: ['260210001', '260210002'] (backend 260210001 and data 260210002 expected)
status counts: {200: 45, 201: 36} | requests: 81
5xx: 0
server errors logged: none
```

### 6. Live run (plan §5.4): pending, needs a human with network

Not runnable here: there is no network, so there is no Ollama, no MongoDB, and
`pymongo` is not installed. The commands to run:

```sh
docker compose --profile llm --profile vectors up
ollama pull llama3.1:8b
ollama pull nomic-embed-text
manage.py init_vector_index
```

Then upload the sample resumes and confirm:
- The extracted values match the reference.
- `/api/matching/search` with the sample JD ranks the two relevant resumes above the three others.
- The sample JD creates a "Backend Engineer" category holding the two backend resumes.
- An admin sees flags on a seeded profile whose form experience and CGPA disagree with its resume.

Also run the skipped real-MongoDB test with `MONGO_URI` set.

### 7. Result

**The offline gate passes:** both backends green, the frontend green,
migrations clean, eval with no misses, all five contracts pinned and passing,
and the fallback run with 0 5xx.

**The live gate (§5.4) is pending.**

There are no blockers and no majors. The minors and nits (X1–X7) are in
`RESUME_INTELLIGENCE_CHECKLIST.md`, final-gate Findings.

---

## Phase A + addendum R1–R5 (2026-10-20)

Run: 2026-10-20 · fresh SQLite database in the session scratchpad ·
`migrate` → `seed_demo --with-students` → `runserver 127.0.0.1:8765 --noreload`.

### Phase 0–3 E2E re-run against today's API

`backend/checkpoints/e2e_phase_0_3.py`, run against a live server started with
`EXPOSE_OTP_IN_RESPONSE=1` and `OTP_THROTTLE_RATE=1000/hour`. It rebuilds the
halfway checkpoint against UUID paths, `roles[]` and the `Company` entity, and
compares each filter's results to the exact expected set.

The run was on merged `main`, with `--block 1`, because a run interrupted
earlier had already used block 0's PRNs in the same database.

```text
PASS  0. server answers /api/health with 200 - HTTP 200
PASS  1. seeded admin can log in - HTTP 200
PASS  1. admin token carries roles[] containing 'placement_admin' - roles=['placement_admin']
PASS  1. roster CSV of 12 synthetic rows uploaded with no rejected rows - HTTP 200 {'created': 12, 'updated': 0, 'unchanged': 0, 'error_count': 0}
PASS  1. 10 placement-eligible students are on the roster - count=10
PASS  2. all 10 students sign up, verify and log in - 10/10
PASS  2. student tokens carry roles == ['student']
PASS  2. PRN not on the roster is rejected - HTTP 403 no_such_prn
PASS  2. roster PRN with someone else's email is rejected - HTTP 403 email_mismatch
PASS  2. a roster row marked not placement-eligible cannot sign up - HTTP 403 not_eligible
PASS  2. both rejected pairs appear in the admin's flagged queue - 14 flagged row(s) matching 'e2e'
PASS  2. rejected pairs never produce a working login - HTTP 401 / 401
PASS  3. every student built a full profile (details, experience, projects, skills, resume) - 10/10
      220200975  aarav_mehta_backend.pdf            exp 3.0 (want 3.0)  edu ['UG'] (want ['UG'])  ok
      220200976  sana_qureshi_data.docx             exp 2.5 (want 2.5)  edu ['Masters'] (want ['Masters'])  ok
      220200977  kabir_nair_frontend.pdf            exp 0.5 (want 0.5)  edu ['UG'] (want ['UG'])  ok
      220200978  arjun_deshmukh_mechanical.docx     exp 4.0 (want 4.0)  edu ['UG'] (want ['UG'])  ok
      220200979  ishita_banerjee_marketing.pdf      exp 1.0 (want 1.0)  edu ['UG'] (want ['UG'])  ok
PASS  3. resume-derived experience and education match the hand-checked reference for 5 students - 5/5 match, and the profile was pre-filled with the parsed years
PASS  3. admin verifies half the profiles (5 of 10)
PASS  4. both seeded company accounts log in
PASS  4. company A shortlists three students while they are public - HTTP [201, 201, 201]
PASS  4. company A sees all-companies plus the profiles it shortlisted - sees 7, expected 7
PASS  4. company B (shortlisted nobody) sees only all-companies profiles - sees 4, expected 4
PASS  4. no hidden profile is visible to either company
PASS  4. a hidden profile cannot be fetched directly (404, not 403) - HTTP 404
PASS  4. one company's shortlist does not expose the profile to another - HTTP 404
PASS  4. a company cannot shortlist its way into a profile it cannot see - HTTP 404
PASS  4. admin still sees all 10 regardless of visibility - count=10
PASS  4. free-text search answers 200 for company A - 5 queries
PASS  4. filter by department returns exactly the expected visible profiles - got 2, expected 2
PASS  4. filter by skill python returns exactly the expected visible profiles - got 5, expected 5
PASS  4. filter by skills python+django returns exactly the expected visible profiles - got 3, expected 3
PASS  4. filter by cgpa 8.0-9.2 returns exactly the expected visible profiles - got 2, expected 2
PASS  4. filter by project keyword returns exactly the expected visible profiles - got 2, expected 2
PASS  4. filter by verified only returns exactly the expected visible profiles - got 4, expected 4
PASS  5. a student edits their own experience entry - HTTP 200
PASS  5. another student editing that entry is refused (404) - HTTP 404
PASS  5. another student deleting that entry is refused (404) - HTTP 404
PASS  5. the entry survived both hostile attempts, unchanged
PASS  5. a student deletes their own project - HTTP 204
PASS  5. an invalid entry (ends before it starts) is refused with 400 - HTTP 400
PASS  5. a student cannot verify their own profile (403) - HTTP 403
PASS  5. a company cannot reach the admin profile list (403) - HTTP 403
PASS  5. an unauthenticated request to a protected endpoint is refused (401) - HTTP 401

  operation            n    median      p95       max
  filter              6     25.0ms     29.2ms     29.2ms
  login              15   1061.7ms   1077.1ms   1116.4ms
  other              46      8.7ms     34.2ms     71.7ms
  profile_read       10     23.2ms     30.6ms     30.6ms
  profile_write      71      9.9ms     25.5ms     61.3ms
  resume_upload      10     41.2ms     64.7ms     64.7ms
  search              7     32.4ms     40.3ms     40.3ms
  signup             13     12.9ms     13.6ms     17.0ms
  verify             10   1057.8ms   1071.5ms   1071.5ms

PASS  6. search responds in under 500 ms - median 32 ms over 7 calls, p95 40 ms
PASS  6. filter responds in under 500 ms - median 25 ms over 6 calls, p95 29 ms
PASS  6. no 5xx response in the whole run - 188 requests, 0 server errors

43/43 checks passed
```

Server log for the run: **0** 5xx responses, **0** tracebacks.

### R1–R5 walk, live

A one-off script drove the addendum flow through the real endpoints. The
student was `220200901`, with roster CGPA 8.72. The transcript was a synthetic
one rendered by `checkpoints/transcript_fixtures.make_case`.

```text
PASS own profile has the addendum fields
PASS resume_url is an API url - /api/profiles/me/resume/file
PASS onboarding GET not completed, roster facts present
PASS onboarding refuses personal email = college email - {"personal_email":["Use an address different from your college email."]}
PASS onboarding completes
PASS career path other without detail refused
PASS career path saved
PASS someone else's transcript refused with prn_mismatch - {"detail":"The PRN on this transcript is not yours. Upload your own transcript.","reason":"prn_mismatch"}
PASS own transcript accepted and parsed - 201 printed=8.50 recomputed=8.50 review=open matches_roster=False
PASS roster 8.72 vs printed 8.50 opens a review
PASS student downloads own transcript
PASS admin detail shows career path and review
PASS admin opens the resume - inline; filename="aarav_mehta_backend.pdf"
PASS admin opens the transcript - inline; filename="transcript_clean.pdf"
PASS admin resolves the review
PASS admin sees the hidden student
PASS company payload carries no career path, transcript or CGPA review - []
PASS company resume opens (visible profile)
PASS company transcript is 404
PASS company cannot open a hidden student's resume
PASS outcomes totals sum to grand total - grand_total=4
PASS outcomes counts the family_business choice
PASS outcomes CSV has header and total row - ['school', 'placement', … 'total'] ... ['total', '0', '0', '0', '0', '0', '1', '0', '0', '3', '4']
PASS students are refused outcomes
PASS admin stats count onboarding - 1
```

The first pass showed 23/25. The two resume opens returned 404 because the
server had been started with a different `MEDIA_ROOT` from the one the seed
wrote to. That was a test-setup error, not an app bug. After a restart with the
matching folder, all four resume checks passed:

```text
PASS admin aarav 200 inline; filename="aarav_mehta_backend.pdf" b'%PDF'
PASS acme aarav 200 inline; filename="aarav_mehta_backend.pdf" b'%PDF'
PASS acme rohan (shortlisted) 200 inline; filename="kabir_nair_frontend.pdf" b'%PDF'
PASS nimbus rohan (not shortlisted) 404
```

Audit rows written during the walk:

```text
cgpa_mismatch_flagged|1
cgpa_review_resolved|1
document_accessed|4
identity_accessed|2
transcript_prn_mismatch|1
```

Server log: **0** 5xx responses, **0** tracebacks.
