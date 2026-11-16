# E: end-to-end demo-script suite

Owner: E2E builder. QA: QA-3.

- [x] E1: An API-level suite (`backend/checkpoints/e2e_demo.py` or similar) walks the demo script against a running server:
  - the officer's all-users page and its filters
  - the outcomes dashboard data and the CSV export
  - a student profile, the verification checks and the resume access log
  - the transcript refusal and acceptance
  - a recruiter's JD search with match breakdowns
  - Nimbus's visibility limits

  **Pass when:** it runs green against a local dev server seeded with `seed_demo`. **Evidence:** verifier run on `cb6944f`, 2026-11-16 21:00 IST: `e2e_demo.py` against a throwaway DB (`seed_demo --with-students` + `seed_outcomes_demo`) and `runserver`, LLM off: 111/111 passed, 1 skipped (the `--live-ai` check only), exit 0, no 5xx in the server log. Beats 1 and 1b ran and passed with no SKIP.
- [x] E2: The suite is deterministic with the LLM off by default. A flag enables live AI assertions. **Pass when:** two consecutive runs give identical results. **Evidence:** verifier run on `cb6944f`, 2026-11-16 21:00 IST: `--repeat 2` reports 111/111 and 1 skipped in both runs, "output identical across 2 runs: yes". The live flag exists (`--live-ai`); not run, since the verifier may not call Gemma.
- [ ] E3: The suite also runs against `serve_demo` (DEBUG off) and asserts the public-link security rules from H5. **Pass when:** it's green. *Not ticked: `serve_demo` is not merged yet.* Stand-in, verifier run on `cb6944f`, 2026-11-16 21:00 IST: `--public` against `runserver` with `DJANGO_DEBUG=false DEMO_MODE=true` gave 20/20 twice, identical; against a DEBUG-on server 9/20 and exit 1, so it bites. **Tick when** the same passes against H's `serve_demo`.
- [x] E4: How to run it is documented in `SMOKE_TESTS.md`.

## Required before E1 or E3 is ticked (from QA-3; added by the verifier, 2026-11-16)

- [x] E5: The suite cannot pass by not running. **Pass when:** a missing seed is a FAIL with a non-zero exit (`e2e_demo.py:566-580`); the all-users beats FAIL on 404 now that P is merged, with no SKIP; the verification-checks beat asserts on a student that has at least one check (`:330-335`); `:455` fails with a message, not an IndexError; and a server that is down gives one clear line and a non-zero exit. **Evidence:** `SMOKE_TESTS.md` "Demo-script E2E" read on `cb6944f`; the verifier's runs followed its commands as written (with a scratch DB path) and they worked. **Evidence:** verifier run on `cb6944f`, 2026-11-16 21:00 IST: empty migrated DB gives 4 FAILs naming the missing seed, 1/7, exit 1; a dead port gives one FAIL line ("Is it running at ...?"), exit 1; beats 1 and 1b pass with no SKIP; beat 3 passes "at least one verification check is raised".
- [x] E6: `--public` checks the real demo sign-in routes, `GET /api/auth/demo/personas` and `POST /api/auth/demo/login`, each expecting 404, and its sign-in-code scan reads the whole response body, not only JSON keys.
- [x] E7: `SMOKE_TESTS.md` (E4) warns that the suite writes to its target: `--public` creates a real signup and sends a sign-in email, and the default run changes the persona student's transcript and CGPA review. **Pass when:** the document says to run it on a throwaway database, never on the demo snapshot (N6). **Evidence:** verifier run on `cb6944f`, 2026-11-16 21:00 IST: against a DEBUG-on server `--public` fails `GET /api/auth/demo/personas`, `POST /api/auth/demo/login` for all four personas, and the code scan (it names `debug_otp` and body text in `/api/auth/otp/request` and `/api/auth/signup`). **Evidence:** the warning block in `SMOKE_TESTS.md` ("both modes write to their target ... Never run either against the demo DB snapshot ... Use a throwaway database").
