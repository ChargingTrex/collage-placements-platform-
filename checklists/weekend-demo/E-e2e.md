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
