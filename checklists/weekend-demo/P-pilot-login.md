# P: pilot login

Owner: P builder. QA: QA-1 (backend) and QA-3 (frontend).

- [ ] P1: `GET /api/auth/admin/users`. Placement admin only. It lists every account with these columns:
  - name, role, human key (PRN / `ADM-` / `CMP-`)
  - email, company, status, verified, onboarding, last sign-in

  It takes the filters `role`, `status`, `prn`, `prns` (reporting `unmatched_prns`), `admin_id`, `company_id`, `school`, `batch` and `search`. An unknown parameter returns 400. Each call writes one `identity_accessed` audit row. **Pass when:** tests cover every filter, a 403 for students and recruiters, the 400, and the audit row.
- [ ] P2: `GET /api/auth/admin/users/summary`. Counts by role and by status. **Pass when:** tests cover the counts and the permission.
- [ ] P3: `/admin/users` page. It has role counts, filters, search, the table and pagination. Student rows link to the student detail page, and recruiter rows to the company. It's in the admin nav and on the admin home page. **Pass when:** frontend tests pass, and the typecheck and build are green.
- [ ] P4: A pilot officer account in `seed_demo`, with its own `ADM-` id, added to `DEMO_LOGINS.md` (gitignored, never committed). **Pass when:** a test proves seeding is idempotent and that the account can sign in.
- [ ] P5: One-click demo sign-in. `DEMO_MODE` is forced off when `DEBUG` is off. The endpoints answer 404 when it's off, and they serve only seeded personas. The login page shows the persona buttons only when they're served. **Pass when:** there are tests for the off case, the DEBUG-off-with-env-on case, each persona, and a refused non-seeded account.
- [ ] P6: Richer synthetic data. Run `seed_demo --with-students` plus `seed_outcomes_demo`, then pre-analyse the persona student and the profiles the demo script opens, using Gemma with no time budget. **Pass when:** those profiles show `extraction_source == "llm"`, and the counts are recorded. *Runs in the Gemma lane, after G3a.*
