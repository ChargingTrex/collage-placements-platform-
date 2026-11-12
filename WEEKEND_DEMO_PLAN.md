# Weekend plan: live AI, vector search, hosting, pilot login, and the demo

Written 2026-11-12 (Thursday). The build runs Friday evening through Sunday
(14–15 Nov). The demo to the placement officer is on **Monday 16 Nov**; that
date is an assumption, so move it if your meeting is on another day.

## What "done" means on Monday

1. **Resume reading runs on Gemma**, which is local Ollama `gemma4:e4b`. It must run against real
   model output, not the fake model the tests use, and the results must be measured
   against the regex reader.
2. **Vector search runs on MongoDB.** A recruiter pastes a job description
   and gets ranked students, with role categories learned from that JD.
3. **There is a public link.** The frontend is on Netlify (or Vercel), and the API is
   served from your Mac.
4. **The pilot login works.** The placement officer signs in and sees **every user account**:
   students, admins and recruiters.
5. **The demo is rehearsed.** There's a 15-minute script, a backup recording, and a
   morning-of checklist.

The demo uses **synthetic data only**. No real student data goes near the public link.

**Out of scope this weekend:** Addendum-2 stages 2–4 (job postings and apply,
suggestions, recruiter exports), Phases B–D, admin MFA, and real-browser
(Playwright) tests.

---

## Decisions in this plan

These are my recommendations. Change any of them before Friday.

### D-W1 · Who serves the API behind the hosted frontend

Netlify and Vercel host static sites. They cannot run Django, Ollama or MongoDB.
Every frontend call goes to `/api/...` on its own address, so the hosted site
can **forward `/api/*` to a backend somewhere else**, with no frontend code
change and no CORS setup.

| Option | How it works | Trade-off |
| --- | --- | --- |
| **A. Your Mac, through a tunnel (recommended)** | Netlify forwards `/api/*` to a stable tunnel address (ngrok's free static domain, or a Cloudflare named tunnel if you own a domain), and the tunnel reaches Django on your Mac | The AI and vector search work through the link. Nothing to pay for. It works **only while the Mac is on and awake**, which suits a demo you present yourself |
| B. A free cloud backend with AI off | Django on Render or Railway, with regex reading, TF-IDF matching and the built-in vector store | The link works around the clock, but without Gemma or MongoDB. A second deployment to keep in sync, and free tiers lose uploaded files on restart |

**Recommendation: A.** The demo runs locally anyway, and the link shows it's deployable.
Choose B later if the officer wants a link that's always up.

### D-W2 · Gemma on this Mac's CPU will be slow, so demo resumes are analysed in advance

This Mac has an Intel i7, 16 GB of RAM and no GPU that Ollama can use, so Gemma
runs on the CPU. **Expect 30–90 seconds per resume.** That is longer than the app's
25-second limit, after which it falls back to regex.

- **Before the demo:** run every demo resume through Gemma with
  `manage.py analyze_resumes`, with no time limit. The demo then shows real Gemma
  readings instantly.
- **During the demo:** one live upload, with the time limit raised to about 120 s.
  The page already polls while analysis runs, so it shows the result when it lands.
  If it is too slow on the day, the regex result appears and you say so.
- **Measure first, on Friday.** If one resume takes more than about 2 minutes, try a
  smaller Gemma variant, if Ollama has one, before Saturday.

### D-W3 · What the pilot login is

**My interpretation:** "a pilot login so the placement officer can see all the
users".

- **A pilot officer account.** A placement admin with its own `ADM-` id, which you
  give to the officer.
- **A new "All users" page.** One table of **every account**:
  - Columns: name, role (student, placement admin, recruiter), human key (PRN /
    `ADM-` / `CMP-`), email, company, status, verified, onboarding done, and last
    sign-in.
  - Counts per role at the top.
  - Filters by role, status, school and batch, plus search.
  - Click a student to open their full profile; click a recruiter to see their company.
  - Read-only. Each listing writes an audit row, because it is identity data
    beyond the officer's own record (G15).
- **One-click demo sign-in, local only.** On your laptop, with demo mode on, the
  login page shows a button per demo persona (student, officer, Acme recruiter,
  Nimbus recruiter), so you can switch views during the demo without typing
  passwords. It is **off on the public link**, which keeps passwords.

**Not included:** "view as this user", meaning acting as someone else. That would
need a new token claim, and the shared identity contract forbids one. Tell me if
you want it and I'll design it separately.

### D-W4 · What the public link runs

- **`DEBUG` off.** Debug pages leak code, and with debug on the API returns sign-in codes.
- **gunicorn instead of Django's development server**, with a 120 s timeout.
- **The Netlify production build of the frontend**, not the Vite dev server.
- **Only the synthetic seed**, reset on Sunday night.

---

## Before Friday: things only you can do

- [ ] Create or confirm a **Netlify** account (or Vercel; the plan uses Netlify's `_redirects`).
- [ ] Create an **ngrok** account and claim its free static domain, or use a Cloudflare
      account if you have a domain on it.
- [ ] Start **Docker Desktop** (it's installed; the CLI is at `/usr/local/bin/docker`).
- [ ] **Free about 10 GB of disk.** 12 GB is free now. MongoDB's image, the embedding
      model, Docker's VM and a production build need room.
- [ ] Confirm the **demo date and room**: will there be a projector, and Wi-Fi or a phone hotspot?

---

## Friday evening (about 2 h): de-risk

Find the slow or broken parts before the weekend depends on them.

- [ ] Start Ollama (`ollama serve`) and pull the embedding model: `ollama pull nomic-embed-text`
      (about 270 MB). Gemma is already pulled.
- [ ] **Speed check.** Time one Gemma resume reading on the CPU, and decide D-W2
      (keep `gemma4:e4b`, or try a smaller variant).
- [ ] **JSON check.** Confirm Gemma honours `response_format: json_object` through
      Ollama's OpenAI-compatible API (`matching/llm.py` `chat_json`). If it
      doesn't, Saturday morning starts with the prompt.
- [ ] Start MongoDB: `docker compose --profile vectors up -d mongo`, then confirm it answers.
- [ ] **Proxy check.** Put a dummy backend behind the tunnel and make sure Netlify's
      `/api/*` forwarding reaches it.
  - Check ngrok's free-tier browser warning page. It can intercept proxied requests,
    and needs the `ngrok-skip-browser-warning` header or a Cloudflare tunnel instead.
  - Check Netlify's time limit on proxied requests, which is roughly half a minute.
    Long AI calls must not run through it (see D-W2).

**Gate:** speed measured, JSON works, Mongo is up, and the proxy round-trips. Anything
red is Saturday morning's first job.

---

## Saturday: the AI goes live

Sonnet agents build, and an Opus verifier ticks each box from its own test run, as before.
Each item gets a failing test or check first.

### Morning: Gemma (stream G)

- [ ] **G1** `.env`: `LLM_ENABLED=true`, `LLM_BASE_URL=http://localhost:11434/v1`,
      `LLM_MODEL=gemma4:e4b`, `EMBED_MODEL=nomic-embed-text`. Ollama runs natively,
      not in Docker; Docker on an Intel Mac gets no GPU either, and native is simpler.
- [ ] **G2** Run `manage.py eval_extraction --llm` over the 10 sample resumes. Paste the
      Gemma and regex columns into `SMOKE_TESTS.md`.
- [ ] **G3** Fix what Gemma gets wrong: prompt wording, JSON shape, field names.
      Changes go in `matching/llm.py`, with a regression test per fix using the
      real reply recorded as a fixture. **Pass when** Gemma's experience and education
      readings match the hand-checked reference at least as well as regex does.
- [ ] **G4** Set `RESUME_ANALYSIS_TIME_BUDGET_SECONDS` and `LLM_TIMEOUT_SECONDS` from
      Friday's measurement, and confirm one live upload completes within it.

### Afternoon: vector search (stream V)

- [ ] **V1** Confirm the `pymongo` pin installs (open item 1.2), and run
      `manage.py init_vector_index`.
- [ ] **V2** Run the skipped MongoDB test with `MONGO_URI=... pytest matching/tests/test_vectorstore.py`.
- [ ] **V3** Run `manage.py reindex_vectors`, then `manage.py recategorise`.
- [ ] **V4** JD search check. The sample backend JD must rank the two backend
      resumes above the other three, and create a "Backend Engineer" category.
- [ ] **V5** Re-measure the four provisional thresholds (open item 1.3) on real
      embeddings: the embedding score floor and ceiling, the category merge
      threshold, the skill-alias threshold and the minimum category fit. Write
      the values into `.env.example`.

**Gate (Saturday night):** the full backend suite is green with the AI off, which is
the default. G2–V5 are recorded in `SMOKE_TESTS.md`, and the resume-intelligence open
items 1.1–1.3 are ticked.

---

## Sunday: the pilot login, hosting, and rehearsal

### Morning: pilot login (stream P), tests first

- [ ] **P1 Backend `GET /api/auth/admin/users`.** Placement admin only. It lists every
      user account with the columns in D-W3, paginated. It takes `?role=`, `?status=`,
      `?prn=`, `?prns=` (naming misses), `?admin_id=` and `?company_id=`. Unknown
      parameters return 400, as everywhere else (D12). Each call writes an
      `identity_accessed` audit row.
- [ ] **P2 Backend `GET /api/auth/admin/users/summary`.** Counts by role and by status.
- [ ] **P3 Frontend `pages/admin/UsersPage.tsx`** at `/admin/users`. It has the table,
      the role counts, the filters and the search, and links rows to the existing
      student detail page. It goes in the admin nav and on the admin home page.
- [ ] **P4 Pilot officer account** in `seed_demo`, added to `DEMO_LOGINS.md`.
- [ ] **P5 One-click demo sign-in.** Add a `DEMO_MODE` setting (an earlier half-built
      version was never committed). It is tied to `DEBUG` and is **off on the public link**. The backend gets a demo-only
      sign-in endpoint for seeded accounts, and the login page shows persona buttons.
      Tests prove it returns 404 when `DEMO_MODE` is off.
- [ ] **P6 Richer synthetic data.** Run `seed_demo --with-students` together with
      `seed_outcomes_demo`, so the users page and the outcomes dashboard look like a
      real cohort. Then run `analyze_resumes` with the D-W2 budget off, so every demo
      student has a Gemma reading.

### Afternoon: hosting (stream H)

- [ ] **H1** Add gunicorn to the requirements. A `serve_demo` script starts the backend with
      `DEBUG=false`, `--timeout 120`, the tunnel host in `DJANGO_ALLOWED_HOSTS` and
      `CSRF_TRUSTED_ORIGINS`, and the Netlify domain allowed.
- [ ] **H2** `frontend/public/_redirects`: forward `/api/*` to the tunnel's address
      (status 200), and send `/*` to `/index.html` (status 200) so React routes survive
      a page refresh. If you use Vercel, put the same in a `vercel.json`.
- [ ] **H3** Deploy to Netlify from the repo or with `netlify deploy --prod`. The build command is
      `npm run build` and the publish folder is `dist`.
- [ ] **H4** **Public-link smoke test:**
  - Run `checkpoints/e2e_phase_0_3.py` against the Netlify URL.
  - Then do a manual pass of the demo script on the public link from a phone.
  - **Pass when** you get 43/43 with no server errors, and nothing returns a sign-in code.
- [ ] **H5** Security pass on the public link:
  - `DEBUG` is off.
  - `/media/` returns 404.
  - `/django-admin/` either has a strong password or is disabled.
  - Demo sign-in returns 404.
  - Only synthetic data is in the database.

### Evening: rehearse

- [ ] **R1** Run the demo script below twice, timing it.
- [ ] **R2** **Record a backup video** of the full run. If Wi-Fi, the tunnel or the Mac
      fails on Monday, you play the video.
- [ ] **R3** Reset to the clean demo database (seed, then pre-analyse), and take a copy of the
      SQLite file and MongoDB volume, so Monday morning is a restore, not a rebuild.

**Gate (Sunday night):** P1–P6 and H1–H5 verified by Opus, the full backend and frontend
suites green, both rehearsals done, and the video recorded.

---

## Monday: the demo (about 15 minutes)

### Morning-of checklist

- [ ] Mac plugged in, and `caffeinate -dims` running so it never sleeps.
- [ ] `ollama serve` is up, `gemma4:e4b` and `nomic-embed-text` are loaded, and the warm-up call is done.
      The first call after a cold start is the slowest.
- [ ] MongoDB is up, the backend runs through `serve_demo`, and the tunnel is up.
- [ ] The Netlify link opens on your phone, and the backup video is ready to play.
- [ ] Browser tabs are open: the local app and the public link. Use one browser profile per
      persona, or the one-click persona buttons.

### Demo script

1. **The problem (1 min).** Placement data today is scattered across spreadsheets, WhatsApp and
   email. This is one verified place.
2. **Pilot login, "All users" (2 min).** Every student, admin and recruiter, with PRN, `ADM-` and
   `CMP-` ids, status and verification. Filter to one school.
3. **Outcomes dashboard (2 min).** Career paths by school, with the bar charts, the
   batch filter and the CSV export.
4. **A student's profile (3 min).**
   - As the officer, open **Profiles** and expand a student's **verification checks**.
     These are the flags raised by the Gemma reading.
   - Open the student's detail page, which shows the CGPA from the roster, the transcript
     and the student's own entry side by side, plus the marksheets.
   - Open the resume. The access is logged.
   - Switch to that student (persona button) and show the **Gemma reading** on their
     resume card, with the experience and education it pre-filled.
5. **Transcript check (2 min).** Upload someone else's transcript and show the refusal.
   Upload the student's own and show the CGPA review.
6. **Recruiter view (3 min).** Sign in as Acme:
   - In **Browse students**, paste a JD and show the **vector search ranking with match
     scores** and their breakdown.
   - Show the role category it created.
   - Switch to Nimbus. Hidden and shortlisted-only students don't appear,
     because visibility belongs to the student.
7. **Live upload (1 min).** Upload one resume and let Gemma read it, or say it's
   running on a laptop CPU and show the pre-analysed one.
8. **What's next (1 min).** Show the decisions you need from them, from
   [`open-items/OPEN_ITEMS.md`](open-items/OPEN_ITEMS.md): the transcript samples,
   the programme list, whether postgraduate cohorts are in scope, and job
   postings next (Phase B / Addendum-2 stage 2).

---

## Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Gemma is too slow on the CPU | Demo resumes are pre-analysed (D-W2). The live upload is optional |
| Gemma returns JSON the parser can't read | The reader falls back to regex, so nothing breaks. G3 exists to fix this on Saturday |
| The tunnel or Wi-Fi fails on Monday | Present from `localhost` directly, since the demo is local anyway. The video is the last resort |
| The disk fills up | Clear space on Friday, before pulling the MongoDB image |
| The proxy cuts off long requests | AI calls stay off the public link's critical path. The live upload is done on `localhost` |
| The public link is found by someone else | Synthetic data only, `DEBUG` off, demo sign-in off. Take the tunnel down after the demo |

## Afterwards

- Record the officer's answers in [`open-items/OPEN_ITEMS.md`](open-items/OPEN_ITEMS.md).
- Turn the tunnel off when the demo ends. Choose D-W1 option B if they want an always-up link.
- Next build: Addendum-2 stage 2 (job postings and apply), which is Phase B in
  [`NEXT_PHASES.md`](NEXT_PHASES.md).
