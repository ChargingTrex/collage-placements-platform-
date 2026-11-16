# Q: the code-quality bar

QA-3 applies this to every module, and the verifier enforces it before merging.

- [ ] Q1: Tests first. Every behaviour change has a test that fails without it.
- [ ] Q2: Existing helpers are reused rather than reinvented:
  - `core/filters.py`
  - `AuditLog.record`
  - existing permissions
  - the frontend API client and components
- [ ] Q3: House rules hold:
  - D12: an unknown parameter returns 400
  - G15: identity reads are audited
  - no new JWT claims
  - synthetic data only
- [ ] Q4: No secrets, `.env`, `db.sqlite3`, `media/` or `DEMO_LOGINS.md` in any commit.
- [ ] Q5: The full backend suite is green with the AI off, and the frontend tests, typecheck and build are green after every merge.
- [ ] Q6: Commits are small, with the checklist ID in each message.
- [ ] Q7: No dead code, debug prints or commented-out blocks. Names and comments match the surrounding style.
