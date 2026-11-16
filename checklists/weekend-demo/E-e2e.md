# E: end-to-end demo-script suite

Owner: E2E builder. QA: QA-3.

- [ ] E1: An API-level suite (`backend/checkpoints/e2e_demo.py` or similar) walks the demo script against a running server:
  - the officer's all-users page and its filters
  - the outcomes dashboard data and the CSV export
  - a student profile, the verification checks and the resume access log
  - the transcript refusal and acceptance
  - a recruiter's JD search with match breakdowns
  - Nimbus's visibility limits

  **Pass when:** it runs green against a local dev server seeded with `seed_demo`.
- [ ] E2: The suite is deterministic with the LLM off by default. A flag enables live AI assertions. **Pass when:** two consecutive runs give identical results.
- [ ] E3: The suite also runs against `serve_demo` (DEBUG off) and asserts the public-link security rules from H5. **Pass when:** it's green.
- [ ] E4: How to run it is documented in `SMOKE_TESTS.md`.

## Required before E1 or E3 is ticked (from QA-3; added by the verifier, 2026-11-16)

- [ ] E5: The suite cannot pass by not running. **Pass when:** a missing seed is a FAIL with a non-zero exit (`e2e_demo.py:566-580`); the all-users beats FAIL on 404 now that P is merged, with no SKIP; the verification-checks beat asserts on a student that has at least one check (`:330-335`); `:455` fails with a message, not an IndexError; and a server that is down gives one clear line and a non-zero exit.
- [ ] E6: `--public` checks the real demo sign-in routes, `GET /api/auth/demo/personas` and `POST /api/auth/demo/login`, each expecting 404, and its sign-in-code scan reads the whole response body, not only JSON keys.
- [ ] E7: `SMOKE_TESTS.md` (E4) warns that the suite writes to its target: `--public` creates a real signup and sends a sign-in email, and the default run changes the persona student's transcript and CGPA review. **Pass when:** the document says to run it on a throwaway database, never on the demo snapshot (N6).
