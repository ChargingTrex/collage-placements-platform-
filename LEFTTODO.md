# Left to do — resume here

Updated 2026-10-20. Phase A (identity retrofit) and the requirements addendum
(R1–R5) are built and merged on local `main`. Phases B–D are outlined, not built.

## Check the state in two minutes

```bash
cd backend
../.venv/bin/python -m pytest checkpoints -q -p no:cacheprovider -o addopts="" -rfxX
```

The expected result is everything passing with **one strict xfail**: admin MFA, deferred by
[`DECISIONS.md`](DECISIONS.md) D23. Any other failure is a regression.

| Gate | Result | How it was checked |
| --- | --- | --- |
| Checkpoint A (identity retrofit) | 60 pass + 1 strict xfail | `checkpoints/test_checkpoint_a.py` |
| Checkpoint E (R1–R5) | 74 / 74 | `checkpoints/test_checkpoint_e.py` |
| Phase 0–3 E2E, live server | 43 / 43 | `checkpoints/e2e_phase_0_3.py` (see the header for the server flags it needs) |
| R1–R5 walk, live server | 25 / 25, zero 5xx | recorded in [`SMOKE_TESTS.md`](SMOKE_TESTS.md) |
| Frontend | 112 / 112, typecheck, build | `npm test`, `npm run typecheck`, `npm run build` |

[`PLAN_CHECKLIST.md`](PLAN_CHECKLIST.md) tracks the plan item by item, and only the verifier
ticks `[x]`.

## Your local database must be reset once

The UUID migrations **refuse** to run on a database created before them
(D11). This is by design, so they never corrupt it:

```bash
cd backend
rm db.sqlite3
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py seed_demo --with-students
```

The logins are in `DEMO_LOGINS.md`, which is gitignored and kept at the root.

## Not pushed to GitHub — your decision

Local history contains a real student's PRN in early commits, and the
GitHub repo is public. The working tree at HEAD is clean. These are the options:

1. **Push a history-free snapshot.** This is one commit with today's files and no old
   history; your local history is untouched. The commands are in
   [`docs/HANDOFF.md`](docs/HANDOFF.md).
2. **Make the repo private first**, then push normally.
3. **Rewrite history** to remove the PRN from every commit, then push.

The agent was not permitted to do 1 or 3, so it needs you to run the commands or allow them.

## Next build: Phase B

Follow [`NEXT_PHASES.md`](NEXT_PHASES.md). It gives the models, endpoints and screens, and the
checkpoint tests to write **first**. The carry-ins there are binding, because they come from bugs
already found once:

- An application creates the `CompanyShortlist` link.
- Opportunities belong to a `Company`, never to a recruiter.
- Department, programme and year are snapshotted at apply time.

## After the demo

- **Admin MFA** (D23): an emailed one-time code as the second factor. When it lands,
  the strict xfail turns into a failure, which tells you to remove it.
- **Token refresh in the frontend.** Everyone is signed out after 15 minutes
  (see [`TODO.md`](TODO.md)).
- **A browser E2E (Playwright).** Today nothing drives the built app in a real browser.

## Blocked on someone else

| Ref | Question | Blocks | Owner |
| --- | --- | --- | --- |
| ID-05 / API-04 | The authoritative programme list, so it can replace the website-derived one in `roster/reference.py` | Accuracy of R3's school grouping | Registrar |
| — | Does the portal cover MBA / M.Sc. / Ph.D. cohorts, or undergraduates only? | R3 scope (today it covers all) | Registrar |
| — | 3–5 more real transcripts, read locally and never committed | Confidence in the transcript parser | Placement cell |
| ID-04 | Institutional email domain and alumni policy | `personal_email` behaviour after graduation | IT |
| ID-06 | How long a graduated student keeps access | The `graduated` status | Registrar |
| ID-07 | Is MFA available on the chosen SSO provider? | The post-demo MFA design | IT |

ID-01 (PRN is nine digits, `YY0200NNN`, with YY the entry year) and ID-02 (never
reused) are answered.

## Where things are

- [`open-items/OPEN_ITEMS.md`](open-items/OPEN_ITEMS.md) lists every decision, question and known problem waiting on you. Resume intelligence's list is beside it.
- [`PLAN_PHASE_A_AND_ADDENDUM.md`](PLAN_PHASE_A_AND_ADDENDUM.md) is the plan that was just executed.
- [`docs/ADDENDUM_API_CONTRACT.md`](docs/ADDENDUM_API_CONTRACT.md) holds the R1–R5 shapes the tests assert.
- [`DECISIONS.md`](DECISIONS.md) records every decision. D11 and D23–D25 are the newest from this work.
- [`TODO.md`](TODO.md) lists open issues and fixed bugs, each with the test that pins it.
- [`CONTEXT.md`](CONTEXT.md) and [`agents/`](agents/) are what every agent reads first.
