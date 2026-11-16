# Phase gates

Format: `- [ ] ID: what. **Pass when:** ... **Evidence:** _(the verifier fills this in)_`

## Before Friday (owner: user)

- [ ] U1: Netlify account (or Vercel). **owner: user**
- [ ] U2: ngrok account and static domain, or a Cloudflare tunnel. **owner: user**
- [ ] U3: Docker Desktop running. **owner: user** *Without it, V runs on the local vector store (V1-local).*
- [ ] U4: About 10 GB free disk. **owner: user** *Measured 9.0 GB free on 2026-11-16.* *Verifier, 2026-11-16: not met, and worse than it reads. Free disk fell to 0.26-0.75 GB three times (12:00, 20:01, 20:39) and came back to 6.3 GB at 20:44 with nothing deleted: the space goes to swap (20.5 of 20.5 GB used at 20:39) when several agent sessions and test runs overlap. While it was full, pytest runs lost output and reported spurious errors. Free real space, and keep to one heavy job at a time (see M4).*
- [ ] U5: Demo date, room, projector and network confirmed. **owner: user**

## Friday: de-risk

- [x] F1: `nomic-embed-text` pulled. **Evidence:** `ollama pull nomic-embed-text` exit 0, 2026-11-16. *Verifier, 2026-11-16:* `ollama list` shows `nomic-embed-text:latest 0a109f422b47 274 MB` and `gemma4:e4b dc35e8d9c606 6.6 GB`.
- [ ] F2: Gemma speed measured. **Session's measurement (not the verifier's):** backend_engineer sample with `gemma4:e4b` on CPU: 185.6 s with thinking on (1027 completion tokens), 88.7 s with `reasoning_effort: "none"` (349 tokens). *Verifier, 2026-11-16: unticked.* The saved reply (`gemma_raw.json`) confirms only the thinking-on run's model and token count (`gemma4:e4b`, 613 prompt + 1027 completion, `finish_reason: stop`). It holds no timings, and nothing from the `none` run was saved. Two tiny verifier calls both timed out at 280 s behind a busy Ollama lane, so no timing is reproduced. **Re-tick when** G2 or G4 records a timed run the verifier can read (the reply with `usage`, plus wall time).
- [x] F3: JSON check. **Evidence:** `response_format: json_object` honoured, `content` is valid JSON in both modes, and reasoning arrives in a separate `reasoning` field. `think: false` does **not** disable thinking on the OpenAI-compatible API; `reasoning_effort: "none"` does. *Verifier, 2026-11-16:* confirmed from `gemma_raw.json` for the thinking-on mode: `content` parses as JSON with the 12 expected keys, and `message.reasoning` is a separate 2460-character field. **Not verified by the verifier:** the `none`-mode JSON and the `think: false` / `reasoning_effort` claim (no saved reply; both verifier calls timed out). G0 and G3a depend on it, so it is re-checked from G's recorded `none`-mode fixture.
- [ ] F4: MongoDB up. **owner: user (needs U3)**
- [ ] F5: Proxy check, Netlify to tunnel to Mac. **owner: user (needs U1, U2)**
- [ ] F6: Gate. **Pass when:** F1-F5 are green, or each red item has a recorded fallback.
  - F4 fallback (recorded): the local vector store with real nomic embeddings, V1-local.
  - F5 fallback (recorded): present from `localhost`; the public link is shown only if U1 and U2 land.

**Found on Friday:** with thinking off, Gemma invented `date_of_birth: 2002-09-01` for a resume that states none. G3 must guard against this.

## Saturday gate

- [ ] S1: The full backend suite is green with the AI off. **Pass when:** `python -m pytest` exits 0 from `backend/`, with the counts recorded. *Not ticked yet: the verifier has no clean full run of its own. Its one full run (on a moving tree, load 200-550, disk full) gave 1036 passed, 1 skipped, 3 errors in 76 min and is discarded. The orchestrating session reports 1088 passed, 1 skipped on `7a0178b` with `LLM_ENABLED=true` pointed at a dead port. The `_offline_ai` guard (`2a7da8d`) was checked by the verifier on the AI test files: 107 passed with the LLM on at a dead port; `VECTOR_STORE_BACKEND=mongo` 114 passed, 1 skipped. Known limit: a `MONGO_URI` in the environment or `.env` still runs `test_real_mongo_round_trip`, which fails if MongoDB is down.*
- [ ] S2: G2-V5 results recorded in `SMOKE_TESTS.md`.
- [ ] S3: Resume-intelligence open items 1.1-1.3 ticked, or each item's remaining part noted as owner: user.

## Sunday gate

- [ ] N1: P1-P6 and H1-H5 verified by the verifier.
- [ ] N2: The full backend and frontend suites are green, including the frontend typecheck and build.
- [ ] N3: The E2E demo suite passes against a local server.
- [ ] N4: R1, demo script rehearsed twice. **owner: user**
- [ ] N5: R2, backup video recorded. **owner: user**
- [ ] N6: R3, clean demo database snapshot taken (SQLite file, plus the MongoDB volume if used).

## Monday readiness

- [ ] M1: Demo-ready state on `weekend-demo`:
  - P merged
  - seeded
  - persona student pre-analysed with Gemma
  - JD search returns ranked students
- [ ] M2: The morning-of checklist in `WEEKEND_DEMO_PLAN.md` can be followed as written; commands checked.
- [ ] M3: The merge freeze is respected. No merges in the last hour before the demo.
- [ ] M4: The Mac is quiet before the Gemma warm-up. **Pass when:** no agent sessions or test runs are active, `uptime` load is below the core count, swap is not growing, and at least 5 GB of disk is free. *Added by the verifier: at 12:00 on 2026-11-16, with the builders running, load was 554, swap 20.2 of 20.7 GB and free disk 0.5 GB; a full backend run took 76 minutes and a pytest run lost its output to a full disk. F2's timings do not hold in that state.*
