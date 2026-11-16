# Phase gates

Format: `- [ ] ID: what. **Pass when:** ... **Evidence:** _(the verifier fills this in)_`

## Before Friday (owner: user)

- [ ] U1: Netlify account (or Vercel). **owner: user**
- [ ] U2: ngrok account and static domain, or a Cloudflare tunnel. **owner: user**
- [ ] U3: Docker Desktop running. **owner: user** *Without it, V runs on the local vector store (V1-local).*
- [ ] U4: About 10 GB free disk. **owner: user** *Measured 9.0 GB free on 2026-11-16.*
- [ ] U5: Demo date, room, projector and network confirmed. **owner: user**

## Friday: de-risk

- [x] F1: `nomic-embed-text` pulled. **Evidence:** `ollama pull nomic-embed-text` exit 0, 2026-11-16.
- [x] F2: Gemma speed measured. **Evidence:** backend_engineer sample with `gemma4:e4b` on CPU: 185.6 s with thinking on (1027 completion tokens), 88.7 s with `reasoning_effort: "none"` (349 tokens).
- [x] F3: JSON check. **Evidence:** `response_format: json_object` honoured, `content` is valid JSON in both modes, and reasoning arrives in a separate `reasoning` field. `think: false` does **not** disable thinking on the OpenAI-compatible API; `reasoning_effort: "none"` does.
- [ ] F4: MongoDB up. **owner: user (needs U3)**
- [ ] F5: Proxy check, Netlify to tunnel to Mac. **owner: user (needs U1, U2)**
- [ ] F6: Gate. **Pass when:** F1-F5 are green, or each red item has a recorded fallback.

**Found on Friday:** with thinking off, Gemma invented `date_of_birth: 2002-09-01` for a resume that states none. G3 must guard against this.

## Saturday gate

- [ ] S1: The full backend suite is green with the AI off. **Pass when:** `python -m pytest` exits 0 from `backend/`, with the counts recorded.
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
