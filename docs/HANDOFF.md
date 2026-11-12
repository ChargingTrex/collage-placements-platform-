# Handoff: Placement Cell Portal (Sai University)

Written 2026-10-19, sections 4–5 updated 2026-10-20. Paste this into a new chat to resume. Never write the real
transcript's PRN or the student's name into any repo file.

## 1. Project and objective

**Repo:** `/Users/fi-it/Documents/projects/collage placements Platform` (git,
branch `main`, nothing pushed yet).

**Product:** a placement-cell portal.

- Students log in with a **PRN** or their college email.
- They build a verified profile: experience, projects, skills, resume.
- Companies browse and filter profiles, subject to each student's visibility setting.
- The placement admin verifies profiles and manages the roster.

**Specs at the root:**

- `placement-cell-portal-prd.md`: original PRD.
- `agents.md`: phased build with smoke-test gates.
- `REQUIREMENTS-ADDENDUM.md`: R1–R5.
- `IMPLEMENTATION_PLAN.md`: phases A–E and the 6-agent split.
- `PLAN_PHASE_A_AND_ADDENDUM.md`: the approved step-by-step for the current work.
- `PLAN_CHECKLIST.md`: tracker for that plan (untracked, new).
- `DECISIONS.md` (D1–D14+), `LEFTTODO.md` (resume point), `TODO.md`, `SMOKE_TESTS.md`, `PROGRESS.md`.
- `CONTEXT.md`: read-first context for all agents.
- `agents/A1..A5-*.md`: agent charters. `backend/checkpoints/QA-GATE.md`: QA charter.
- `DEMO_LOGINS.md`: gitignored, plain-text demo credentials.

**Binding external contract:** `/Users/fi-it/Documents/projects/culturas:club management platform /shared/`

- `Identity_Login_Shared_Data.docx`
- `API_Standards_Integration_Contract.docx`

The portal is a **separate app that shares the institutional SSO** (D1). So the
identity, claims and token rules are binding; the API-namespace and adapter
rules are not.

## 2. Key decisions and constraints

- **D2/D3:** finish the identity retrofit (Phase A) first, then R1–R5. **Phases B–D** (Opportunities, Certifications, Company self-service) are **outline only for now**, in `NEXT_PHASES.md`, which is not yet written.
- **D4 PRN format:** nine digits, validator `^[0-9]{9}$`, to be moved into `settings.IDENTITY["PRN_REGEX"]`. Template `YY0200NNN`, where **YY = entry year** (a PRN starting `24` = joined 2024).
  - Fixture PRNs must satisfy entry year = batch − 4 (4-year UG): batch 2026 → `22…`, 2027 → `23…`, 2025 → `21…`. Sequences in the `9xx` range.
- **D5:** the portal issues its own **RS256** tokens carrying the exact §5.4 claim set: `sub, iss, aud, iat, exp, email, student_id, prn, display_name, roles[], department, programme, year, mfa`. Optional claims are `null`, never omitted.
  - Roles: `student`, `placement_admin`, `company_recruiter:<company_uuid>`.
  - JWKS at `/api/auth/jwks`.
  - 15-minute access tokens.
  - Refresh reuse revokes the whole family (`RevokedTokenFamily`).
- **D8:** **UUID carries every join.** PRN is the human key: login, display, exports, and the `?prn=` / `?prns=` filters. It is **never a foreign key, never a path parameter.** The email+PRN compound-key idea was rejected.
- **D9:** human keys for every role, issued sequentially and immutable: `ADM-0001`, `CMP-0001`. `Company` is an entity (UUID, `company_id`, name, email), and recruiter `User`s belong to it. `CompanyShortlist.company` → `Company`.
- **D10:** the registrar confirmed PRN is issued once and never reused, and that it identifies the student's transcript and documents. A transcript's PRN must equal the uploading student's.
- **D11:** the UUID primary-key migration **refuses loudly** on a populated DB, because Django would otherwise silently leave int ids in UUID columns. The decision is to re-scope the checkpoint test to assert the refusal. Data is synthetic; reset with `rm backend/db.sqlite3 && migrate && seed_demo`.
- **D12:** unknown query params → 400, via `core.filters.RejectUnknownQueryParams`.
- **D13:** `status` (6-value registrar lifecycle) is separate from `is_placement_eligible`.
- **D14:** profiles are addressed by the **student UUID** (`student_id`), not the profile row's.
- **Admin MFA: deferred until after the demo** (email OTP later, D23). The failing MFA checkpoint test becomes `xfail(strict=True)`.
- **Addendum recommendations all accepted (D24):**
  - Career path is single-select (9 options incl. `placement` and `undecided`; Business, Entrepreneurship and Family business stay distinct, each with a one-line explanation) plus an `also_attending_placements` checkbox.
  - Companies never see career path or transcript.
  - Onboarding is a dismissible prompt + banner (phone + career path required).
  - On a CGPA mismatch, flag it for the admin; **roster CGPA stays authoritative**.
  - The outcomes dashboard covers all cohorts, grouped by school, filterable by batch.
  - Resume and transcript views are audit-logged.
  - Documents are served only through authenticated endpoints (D25).
- **Working rules:**
  - Tests are written **before** the code that ticks a checkbox, and must fail first.
  - Commit per task, explicit paths only (never `git add -A`). Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Sonnet subagents implement. An Opus agent verifies and updates `PLAN_CHECKLIST.md` (`[~]` implemented → `[x]` verified / `[!]` failed). The orchestrator commits only `[x]` items.
  - Comments must be **short, plain, and explain why**, so the user can fix issues themselves.
  - Never write temp files to `/tmp`; use the session scratchpad. An earlier attempt failed because `/tmp` had been cleared.

## 3. Stack and structure

**Backend:** Django 5.1 + DRF, SimpleJWT 5.4, `cryptography`, django-filter,
SQLite in dev / Postgres via docker-compose and CI, spaCy `en_core_web_md`
with a TF-IDF fallback.

- The custom `MultiKeyTokenBackend` is installed in `accounts/apps.py` `ready()` via `Token._token_backend`, because SimpleJWT 5.4 removed `TOKEN_BACKEND_CLASS`.
- Venv at `.venv`: from `backend/`, run `../.venv/bin/python manage.py …`.

Key modules:

- `accounts/`
  - `models.py`: `User` (UUID pk, `role`, `prn`, `status`, `admin_id`, `company` FK, `display_name_override` plus a `display_name` property), `Company`, `issue_human_key()`, `RevokedTokenFamily`, `OneTimeCode`.
  - `identity.py`: keyring, `build_claims`, `roles_for`, JWKS, `reset_keyring()`.
  - `views.py`: signup, verify, login (PRN or email), OTP, `RefreshView` with family revocation.
- `roster/`: `Student` (UUID pk, prn, school, programme, year_of_study, batch, cgpa), CSV importer, `FlaggedSignup`.
- `profiles/`: `StudentProfile` (`visible_to()` holds the visibility rule), entries, skills, `CompanyShortlist`. Views use `lookup_field = "student_id"`. Also contains **resume-intelligence additions from the other session**.
- `core/`: `AuditLog`, `storage.py`, `filters.py` (`HumanKeyFilter`, `HumanKeyInFilter`, `RejectUnknownQueryParams`).
- `matching/`: the engine plus the other session's LLM/vector work. **Owned by the resume-intelligence workstream; don't touch** `extractors.py`, `samples.py`, `tests/test_extractors.py`.
- `checkpoints/`: Phase A gate suite, 61 tests, plus `QA-GATE.md`.

**Frontend:** Vite + React 19 + TypeScript + Tailwind 4. Needs
`export PATH="/usr/local/bin:$PATH"`, otherwise node isn't found.

- `src/api/auth.ts`: `areaOf(user)` maps `roles[]` to student/admin/company.
- `src/api/profiles.ts`: calls are addressed by `student_id`.
- Pages live under `src/pages/{student,admin,company}`.

**Run:** backend `runserver 127.0.0.1:8000`; frontend `npm run dev` on :5173,
which proxies `/api`.

**Demo logins** (synthetic; full list in `DEMO_LOGINS.md`):

| Role | Login | Password |
| --- | --- | --- |
| Admin (ADM-0001) | `placement.officer@college.edu` | `AdminPass!234` |
| Company (Acme, CMP-0001) | `recruiter@acmetech.example` | `CompanyPass!234` |
| Student | PRN or college email | `StudentPass!234` |

## 4. Exact current state

Phase A and R1–R5 are **built and merged on local `main`**. Nothing is pushed.

- Checkpoint A: all pass except one strict xfail (admin MFA, D23).
- Checkpoint E (R1–R5): 74/74.
- `checkpoints/e2e_phase_0_3.py` against a live server: 43/43.
- A live R1–R5 walk: 25/25 with zero 5xx. The output is in `SMOKE_TESTS.md`.
- Frontend: 112 tests, typecheck and build clean.

Per-item status and evidence: `PLAN_CHECKLIST.md`. The shortest resume note is
`LEFTTODO.md`.

**Things to know:**

- **The local DB must be reset once.** The UUID migrations refuse to run on an
  older database (D11). Use `rm db.sqlite3 && migrate && seed_demo --with-students`.
- **New decisions D23–D25:**
  - D23: MFA after the demo.
  - D24: the addendum's recommendations are accepted.
  - D25: documents only through audited endpoints.

  These were renumbered from the plan's D15–D17, because the resume-intelligence work had already used D15–D22.
- **`/media/` is no longer served, even in DEBUG.** Resumes and transcripts come only from
  the API views, which check access and audit each admin or company open.
- **The importer warning for a PRN's entry year is still only proposed** and was not built.
- **Real student data.** None is at HEAD; the real-series grep pattern is in the session plan,
  not in the repo. It does exist in early local commits. A backup branch `backup/pre-scrub` exists.
- **A stale worktree** sits at `../collage-placements-phase-a` (branch `phase-a-addendum`).
  It's unused and safe to remove. Agent worktrees under `.claude/worktrees/` can go too.

## 5. Next steps, in order

1. **Decide how to publish.** The GitHub repo
   `https://github.com/ChargingTrex/collage-placements-platform-` is public and
   empty, and local history contains a real PRN. The agent's attempts to rewrite
   history or push a snapshot were blocked by the permission classifier. A
   history-free snapshot, run by you from the repo root:

   ```bash
   SNAP=$(git commit-tree HEAD^{tree} -m "Placement Cell Portal: initial public snapshot")
   git remote add origin https://github.com/ChargingTrex/collage-placements-platform-.git
   git push origin "$SNAP:refs/heads/main"
   ```

   The alternatives are to make the repo private first, or to allow a history rewrite.
2. **Phase B (Opportunities Board)** per `NEXT_PHASES.md`. Write the Checkpoint B
   tests first and run them red, then build.
3. **After the demo:**
   - admin MFA by email OTP (D23);
   - token refresh in the frontend (users are signed out after 15 minutes today);
   - a Playwright browser E2E.
