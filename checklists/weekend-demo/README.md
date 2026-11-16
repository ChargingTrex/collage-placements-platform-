# Weekend-demo checklists

One file per module, plus the phase gates. They track [`WEEKEND_DEMO_PLAN.md`](../../WEEKEND_DEMO_PLAN.md); item IDs match the plan.

## How the boxes get ticked

- **Builders** do the work in their own worktree branch, tests first, and commit each item with its ID in the commit message (e.g. `P1: ...`).
- **Three QA agents** review the diffs, not the builders' summaries:
  - **QA-1:** backend and security (P, H)
  - **QA-2:** AI correctness (G, V)
  - **QA-3:** frontend, the end-to-end (E2E) suite, and code quality across all modules
- **The verifier (Fable)** is the only one who ticks boxes. A box is ticked only from the verifier's own test run or check, and the evidence goes on the line. QA findings go to the verifier, and fix requests go back to the owning builder.
- Items marked **owner: user** need your accounts or your hands. Agents never tick them.

## Rules every module follows

- **Tests:** written first. The backend suite runs offline: `backend/conftest.py` forces the LLM off and blanks MONGO_URI.
- **Gemma:** only one agent at a time may call it. All other runs use `LLM_ENABLED=false`.
- **Never committed:** `.env`, `db.sqlite3`, `media/`, `DEMO_LOGINS.md`, any token.
- **Synthetic data only.** The repo is public.
- **Settings:** each module keeps its settings in its own commented block in `config/settings.py`.
- **Merging and pushing:** only the orchestrating session merges into `weekend-demo`, with `--no-ff`, and runs the full suite after each merge. Nothing is pushed until you say so.

| File | Module |
|---|---|
| [00-phase-gates.md](00-phase-gates.md) | Friday, Saturday and Sunday gates, and Monday readiness |
| [G-gemma.md](G-gemma.md) | Resume reading on Gemma |
| [V-vectors.md](V-vectors.md) | Vector search and role categories |
| [P-pilot-login.md](P-pilot-login.md) | All-users page, pilot officer, one-click personas |
| [H-hosting.md](H-hosting.md) | gunicorn, serve_demo, Netlify forwarding, security |
| [E-e2e.md](E-e2e.md) | End-to-end demo-script suite |
| [Q-quality.md](Q-quality.md) | Code-quality bar the QA agents apply |
