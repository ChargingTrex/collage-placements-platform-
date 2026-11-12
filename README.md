# Placement Cell Portal

A web portal where students log in with their PRN and college email, build a
verified profile of experience and projects, and see certifications and
opportunities matched to them. Companies get a filterable view of student
profiles instead of a folder of resume PDFs.

Built against [`placement-cell-portal-prd.md`](placement-cell-portal-prd.md),
phase by phase per [`agents.md`](agents.md). Current status:
[`PROGRESS.md`](PROGRESS.md).

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Django 5 + Django REST Framework, JWT auth (SimpleJWT) |
| Frontend | React 19 + TypeScript, Vite, Tailwind CSS 4 |
| Database | SQLite for local dev, PostgreSQL via docker-compose and in CI |
| Uploads | Local filesystem in dev, S3-compatible via config switch |
| Matching | spaCy `en_core_web_md`, with a scikit-learn TF-IDF fallback |

## Run it locally

Two terminals, no Docker, no database setup:

```bash
# 1. Backend  ->  http://127.0.0.1:8000
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver

# 2. Frontend ->  http://localhost:5173
cd frontend && npm install && npm run dev
```

The root page shows a live backend status panel; it is green when the API,
database, storage, and matching engine all answer.

### Optional: the spaCy semantic backend

The engine falls back to TF-IDF cosine similarity when spaCy is absent, so
nothing is blocked on this. For the PRD's semantic matching:

```bash
.venv/bin/pip install -r backend/requirements-nlp.txt
.venv/bin/python -m spacy download en_core_web_md
```

`/api/health` reports which backend is live.

## Run it with Docker

```bash
cp .env.example .env
docker compose up --build
```

Brings up Postgres, the backend (migrations applied on start), and the
frontend dev server. Add `INSTALL_NLP=true` to `.env` before building to bake
the spaCy model into the backend image.

## Tests

```bash
cd backend  && ../.venv/bin/python -m pytest -q
cd frontend && npm test && npm run typecheck
```

CI runs both suites against PostgreSQL on every push.

## Documents

| File | What it is |
| --- | --- |
| [`CONTEXT.md`](CONTEXT.md) | Shared context every agent reads first |
| [`agents/`](agents/) | One charter per feature agent; QA's is at [`backend/checkpoints/QA-GATE.md`](backend/checkpoints/QA-GATE.md) |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Phases, agent split, the gap register |
| [`NEXT_PHASES.md`](NEXT_PHASES.md) | Phases B–D outline: models, endpoints, tests to write first |
| [`open-items/`](open-items/) | Every decision, question and known problem waiting on a person |
| [`DECISIONS.md`](DECISIONS.md) | Every decision, its reasoning, and what was rejected |
| [`LEFTTODO.md`](LEFTTODO.md) | **Resuming? Start here** |
| [`PLAN_PHASE_A_AND_ADDENDUM.md`](PLAN_PHASE_A_AND_ADDENDUM.md) | Approved step-by-step for finishing Phase A + R1–R5 |
| [`TODO.md`](TODO.md) | Open work and the bug record |
| [`REQUIREMENTS-ADDENDUM.md`](REQUIREMENTS-ADDENDUM.md) | R1–R5 — career outcomes, onboarding, transcripts |
| [`SMOKE_TESTS.md`](SMOKE_TESTS.md) | Real captured output from every smoke test run |
| [`PROGRESS.md`](PROGRESS.md) | Phase-by-phase status |

## Layout

```
backend/
  config/          Django project: settings, root URLconf, WSGI
  core/            health endpoint, upload storage boundary, audit log
  accounts/        User model (student / admin / company), OTP, JWT login
  roster/          student master list, CSV upload, flagged signups
  profiles/        experience, projects, skills, resume upload, visibility
  matching/        resume parsing + semantic matching engine (shared service)
  opportunities/   postings, ranking, applications        (Phase 4, not built)
  certifications/  catalog, suggestions, proof verification (Phase 5, not built)
frontend/
  src/api/         typed fetch client, one module per backend area
  src/auth/        session context and route guards
  src/pages/       one file per screen, grouped by role
  src/components/  shared UI
```

## Environment

Everything is environment-driven with working defaults — see
[`.env.example`](.env.example). No `.env` is needed for a local run.
