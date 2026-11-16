# Q: the code-quality bar

QA-3 applies this to every module, and the verifier enforces it before merging.

- [x] Q1: Tests first. Every behaviour change has a test that fails without it. **Evidence:** every module's diff carries tests for its behaviour (read by the verifier and by QA-1, QA-2, QA-3). Proved by removal for the grounding guard only (8 tests fail without it); for the rest this rests on reading the tests, and on three env-dependent tests that did fail when the demo `.env` changed the behaviour.
- [x] Q2: Existing helpers are reused rather than reinvented:
  - `core/filters.py`
  - `AuditLog.record`
  - existing permissions
  - the frontend API client and components

  *Ticked:* P reuses `core.filters`, `IsPlacementAdmin`, `AuditLog.record` and the admin page components; V and H extend existing settings blocks and commands (verifier's read of each diff).
- [x] Q3: House rules hold:
  - D12: an unknown parameter returns 400
  - G15: identity reads are audited
  - no new JWT claims
  - synthetic data only

  *Ticked:* P tests cover the 400 and the audit row; demo tokens carry the same claims as a password login (`test_demo_login.py`); fixtures and seed data are synthetic.
- [x] Q4: No secrets, `.env`, `db.sqlite3`, `media/` or `DEMO_LOGINS.md` in any commit. **Evidence:** `git log --name-only f941947..004ff6f` lists none of them, nor `backend/.cache/`; all are gitignored.
- [x] Q5: The full backend suite is green with the AI off, and the frontend tests, typecheck and build are green after every merge. **Evidence:** green on the final tree `004ff6f` by the verifier's own runs (S1, N2). The per-merge runs were the orchestrating session's; two of them were disturbed by the full disk and re-run.
- [x] Q6: Commits are small, with the checklist ID in each message. **Evidence:** 67 non-merge commits since `f941947`; all but four name their item, and those four are small G and V commits whose subject says what they do.
- [x] Q7: No dead code, debug prints or commented-out blocks. Names and comments match the surrounding style. **Evidence:** a search of the product diff for `print(`, `console.log`, `debugger`, `TODO` and `FIXME` finds nothing; the one commented block is the documented Netlify fallback in `netlify.toml`.
