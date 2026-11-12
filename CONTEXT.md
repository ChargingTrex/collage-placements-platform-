# Shared context — every agent reads this first

The common truth for all six agents on the Placement Cell Portal. Your own
charter is in `agents/<your-id>.md` (the QA charter lives beside its tests, at `backend/checkpoints/QA-GATE.md`) and assumes you have read this.

Authoritative documents, in precedence order:

1. `shared/Identity_Login_Shared_Data.docx` — **binding**, identity and auth
2. [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — decisions, gap register, your stream
3. [`agents.md`](agents.md) — phase definitions, checkpoint discipline
4. [`REQUIREMENTS-ADDENDUM.md`](REQUIREMENTS-ADDENDUM.md) — R1–R5
5. [`TODO.md`](TODO.md) · [`PROGRESS.md`](PROGRESS.md) · [`SMOKE_TESTS.md`](SMOKE_TESTS.md) — running state

Where this file and the plan disagree, **the plan wins** and you raise the
conflict rather than choosing.

---

## 1. What exists

A working Django 5 + DRF backend and a Vite/React/TS/Tailwind frontend.
Phases 0–3 of `agents.md` are complete and green: **249 backend tests, 43
frontend tests**, and a halfway E2E at 30/30 checks.

```
backend/
  config/          settings, root URLconf
  core/            health, upload storage boundary, AuditLog
  accounts/        User (student/admin/company), OTP, JWT, permissions
  roster/          Student master list, CSV importer, FlaggedSignup
  profiles/        StudentProfile, experience, projects, skills, visibility
  matching/        resume parsing, matching engine, Llama extraction, vectors,
                   skill graph, role categories (RESUME_INTELLIGENCE_PLAN.md)
  opportunities/   EMPTY scaffolding — Phase B
  certifications/  EMPTY scaffolding — Phase C
frontend/src/
  api/             typed fetch client, one module per backend area
  auth/            AuthContext, route guards
  pages/           one file per screen, grouped by role
  components/ui/   shared design kit
```

Run it:

```bash
cd backend  && ../.venv/bin/python manage.py runserver
cd frontend && npm run dev          # http://localhost:5173
cd backend  && ../.venv/bin/python -m pytest -q      # ~4.5 min
cd frontend && npm test && npm run typecheck && npm run lint
```

`../.venv/bin/python` — always. There is no activated virtualenv.

---

## 2. The nine decisions

From [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §1. **Do not work
around any of these. Stop and raise it.**

| # | Decision |
| --- | --- |
| D1 | Separate application sharing the institutional SSO; not a platform module |
| D2 | Identity and auth retrofitted first, before feature work |
| D3 | Order: retrofit → agents.md Phases 4–6 → R1–R5 |
| D4 | PRN is nine digits (`220200921`) |
| D5 | Standalone tokens carrying the exact platform claim contract |
| D6 | Five feature agents, one QA gate agent |
| D7 | Department/programme codes from the real Sai University list |
| D8 | PRN is the human key; **UUID carries every join**; no FK references PRN or email |
| D9 | Every role has a human key — `prn` / `ADM-0001` / `CMP-0001`; `Company` is its own entity |

---

## 3. Binding rules you cannot break

From the shared identity spec. Violating one of these is not a bug to fix
later; it is a stop-and-raise.

- **UUID is the only key.** No foreign key references PRN or email, ever.
- **Email is never an identifier.** Authentication may match on it; nothing else may.
- **PRN is immutable, issued once, never reused.** Confirmed by the registrar 2026-09-30.
- **`full_name` is one field.** Never split into first and last.
- **Name validation is length-only.** Non-empty, under 160 characters. Any
  structural rule — requiring a space, two words, rejecting dots — rejects real students.
- **Store Unicode. Never transliterate or strip diacritics.**
- **Department and programme codes come from the shared list.** An unrecognised
  code surfaces as unknown and logs. It is never silently mapped to something plausible.
- **Claim structure is identical in standalone and platform mode.** Optional
  claims are `null`, never omitted.
- **Authorisation is always local.** A token proves identity and carries roles.
  It never grants access by itself — the portal checks scope server-side.
- **Records outlive accounts.** Graduated and withdrawn students keep their
  rows. Deactivate the account; never delete the history.
- **Identity access beyond a user's own record is logged.**

---

## 4. Conventions in this codebase

Match what is there. It is consistent, and consistency is worth more than your
preference.

- **No trailing slashes.** `DefaultRouter(trailing_slash=False)` everywhere.
- **snake_case on the wire.** The frontend converts if it wants to.
- **404, not 403, where existence is a disclosure.** Another student's entry
  returns 404 — a 403 confirms it exists.
- **Authorisation lives in the queryset**, not the view and never the UI. See
  `StudentProfile.objects.visible_to`.
- **Tests are named as sentences.** `test_a_student_cannot_edit_another_students_entry`.
- **Comments explain why, never what.** The codebase has a density; match it.
- **Every list endpoint is paginated.** No exceptions.

### Things that will bite you

| Trap | Why |
| --- | --- |
| `transaction.atomic` around a path that raises after writing | Rolled back the flagged-signup queue in Phase 1. If you write then raise, the write is lost |
| django-filter ignores undeclared query params | `?prn=x` currently returns the **whole table**. Declare filters; reject unknown params |
| spaCy is not thread-safe | `matching/backends.py` holds a lock. Do not remove it |
| Two similarity backends, different scales | Never hardcode a threshold. Read `engine.default_threshold` |
| DRF throttle state is process-global | Leaks across tests; `conftest.py` clears it |
| The test suite takes ~4.5 minutes | Run your module's subset while working; full suite before you report |
| Ollama and MongoDB are optional (D16) | `LLM_ENABLED` is off by default. Tests use `matching.testing.FakeLLMClient` and the local vector store; no test may need either service |
| Vector metadata is an allow-list (D21) | Only `vectorstore.FILTER_FIELDS` reach a store, never resume text or contacts. Visibility is `visible_to`, never the store |
| Age, DOB, resume CGPA and verification flags are admin-only (D18–D20) | Every student and company payload test asserts their absence. Keep it that way when adding fields |
| Changing `EMBED_MODEL`, the skill graph or skill slugs | Run `manage.py reindex_vectors` (full, not `--dirty-only`), then `manage.py recategorise` |

---

## 5. Rules of engagement

1. **Announce the phase and task before touching code.**
2. **Commit per completed task**, message naming phase and task.
3. **Never mark a checkpoint or smoke test passed.** Only QA does that.
4. **A failing test in another agent's module is raised, not fixed.**
5. **Never write a migration on a feature branch.** Raise it to A1, who owns
   migration ordering. Two agents generating migrations in parallel produce a
   conflict no rebase resolves.
6. **Update [`PROGRESS.md`](PROGRESS.md) at the end of each task**, so a
   cold session resumes without re-reading history.
7. **Report honestly.** If a test fails, say so with the output. If you skipped
   something, say that. A green report that is not green costs more than a red one.

### Shared surfaces — one owner each

| Surface | Owner | If you need a change |
| --- | --- | --- |
| `components/ui/` | A5 | Request it; never edit in a feature branch |
| `matching/` engine | A2 | Public boundary is `get_engine()` |
| `accounts/permissions.py` | A1 | Request a new role gate |
| `core/storage.py` | A1 | Request a new upload type |
| `config/settings.py` | A1 | Append a namespaced dict; never edit existing keys |
| root `conftest.py` | QA | Add module fixtures in your own `tests/conftest.py` |

---

## 6. Definition of done

A task is done when **QA says so**, and QA says so only when:

- The smoke test for it **was written before the work**, and now passes
- Its output is recorded in [`SMOKE_TESTS.md`](SMOKE_TESTS.md) — real output, not a summary
- Every prior smoke test still passes
- The full suite is green on both similarity backends
- No 5xx and no tracebacks in the logs of the run
- [`PROGRESS.md`](PROGRESS.md) reflects what a cold session would need

**A task is not done because the code is written.**
