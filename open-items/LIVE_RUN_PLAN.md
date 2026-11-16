# Live run: Gemma + MongoDB, locally

## Context

The resume-intelligence plan is signed off **offline only** (LLM off, local vector store). Its last open gate is the live run in plan §5.4. That run was impossible before because there was no network, no Ollama and no MongoDB. This Mac now has all three:

- **Ollama:** running at `localhost:11434` with `gemma4:e4b` and `nomic-embed-text` pulled.
- **`pymongo`:** 4.10.1 is installed in `.venv`; the pin in `requirements.txt` is confirmed.
- **Docker Desktop:** installed and launched, but its daemon had not answered yet.

What has been tried so far:

**Gemma extraction** (`eval_extraction --llm`, 10 hand-checked sample resumes):

| Field | Regex | Gemma |
| --- | --- | --- |
| experience | 10/10 | 4/10 |
| education | 10/10 | 7/10 |
| age | 1/1 | 1/1 |
| cgpa | 2/2 | 2/2 |

- On 4 samples Gemma came back **"unavailable"**: `LLMUnavailable`, so either a timeout or invalid JSON twice. The cause is not yet known.
- On 3 samples it reported **0 experience**. Two of them (`backend_engineer`, `data_engineer`) *state* their experience but give no dates, so 0 is the intended reading for the model alone: the engine's blend uses the regex claim instead. The third, `biotech_masters` (expected 0.5), needs a look.
- Where Gemma did answer, education, age and CGPA were all correct.
- **Speed:** about 176 s per resume on this Intel i7 CPU. The analyse endpoint's budget is 25 s, so live analysis would always fall back to regex.

**Embeddings** (`nomic-embed-text`, 768 dimensions, about 1.5 s each):
- The two relevant samples rank top: 0.836 and 0.733. The rest run from 0.630 down to 0.509.
- The provisional calibration (floor 0.40, ceiling 0.85) is too low at the floor; about 0.50 fits.

The goal is to finish §5.4 on this Mac:
- MongoDB running, with a real round trip
- Gemma wired into the app flow
- the "unavailable" cause understood
- calibration set from measured numbers
- results recorded, then verified by an Opus agent (the process used so far)

## Plan

### 1. Get Docker and MongoDB up

1. Confirm the Docker daemon answers: `docker info`. PATH needs `/usr/local/bin`. If it hangs, the user opens Docker Desktop once and accepts its first-run prompts. That is the only step needing the user.
2. Start the mongo service: `docker compose --profile vectors up -d mongo`. This is the `mongodb/mongodb-atlas-local` image, already in `docker-compose.yml`, which serves `$vectorSearch`.
3. Point the app at it: `MONGO_URI=mongodb://localhost:27017/?directConnection=true`. The backend runs on the host through `runserver`, not inside compose, so it is `localhost`, not `mongo`.
4. Create the index and run the real test:
   - `manage.py init_vector_index --dims 768`
   - run `matching/tests/test_vectorstore.py::test_real_mongo_round_trip` with `MONGO_URI` set (it is the suite's only skip)

### 2. Diagnose Gemma's 4 "unavailable" readings

Re-run `parse_resume_facts` on `frontend_intern`, `mechanical_designer` and `marketing_executive` with `httpx` debug logging, and record per sample:
- the elapsed time
- whether the reply was a timeout or invalid JSON
- the raw reply

Then fix whatever is found, inside `matching/llm.py`:
- **A timeout:** separate the read timeout from the analysis budget for batch use (`eval_extraction`, `analyze_resumes`), and have the client honour `LLM_TIMEOUT_SECONDS` fully.
- **Fenced JSON or text around the object:** strip it before `json.loads`; Gemma models often wrap output in markdown fences.
- **A validation failure:** relax or coerce the field the model gets wrong, in `_normalise_resume_reply`.

Also check `biotech_masters`: are its experience dates missing from the reply, or failing the grounding check?

Every fix gets a regression test using `FakeLLMClient` with the real failing reply.

### 3. Wire Gemma into the local flow

Create a local `.env` (none exists today; `.env.example` is the template):

```
LLM_ENABLED=true
LLM_MODEL=gemma4:e4b
EMBED_MODEL=nomic-embed-text
LLM_TIMEOUT_SECONDS=300
RESUME_ANALYSIS_TIME_BUDGET_SECONDS=300
VECTOR_STORE_BACKEND=mongo
MONGO_URI=mongodb://localhost:27017/?directConnection=true
```

- The 300 s budget is **dev only**, so CPU-speed analysis can finish. The production value stays a GPU decision (open item 2.2).
- `.env` stays out of git; check `.gitignore` covers it.
- Restart `runserver` so the new settings load.

### 4. Recalibrate embeddings from measured numbers

- Set `MATCH_SCORE["CALIBRATION"]["embedding"]` in `backend/config/settings.py` to floor **0.50**, ceiling **0.85**, measured above.
- Put the measurements in the comment, the same way the spaCy and TF-IDF constants were recorded.
- Re-check `CATEGORY_MERGE_THRESHOLD` (0.75) by recording the sample JD twice and a different-role JD once: same-role JDs should merge and different-role ones should not.

### 5. End-to-end through the API (plan §5.4)

With the settings from step 3, on the dev database:
1. Run `seed_demo --with-students` (admin, companies, students).
2. As a student, upload a sample resume. `POST me/resume/analyze` should return `source: llm`, take about 3 min, and show suggestions.
3. As a company, `POST /api/matching/search` with `SAMPLE_JOB_DESCRIPTION` should return `fallback: false`. The vectors come from MongoDB, and the backend resumes rank on top.
4. The sample JD should create a "Backend Engineer" category, and the backend students should land in it (via `recategorise`).
5. As an admin, the flags should show on a profile whose form disagrees with its resume.

Capture the request log and the statuses.

### 6. Record, verify, commit

- Append a "Live run (Gemma + MongoDB)" section to `SMOKE_TESTS.md` with real output: the eval table, timings, the MongoDB test, and the API log.
- Update `RESUME_INTELLIGENCE_CHECKLIST.md`:
  - §5.4 and the `pymongo` gap become `[~]`
  - the sign-off notes the live run was done with **Gemma** on CPU, not the plan's `llama3.1:8b`
- Update `open-items/RESUME_INTELLIGENCE_OPEN_ITEMS.md`:
  - close 1.1, 1.2 and the embedding part of 1.3
  - record the CPU speed finding under 2.2
- Run an **Opus 5.5 verifier agent** to re-run steps 1, 4 and 5 independently and tick the items `[x]`, or `[!]`.
- Commit by explicit path only.
  - The working tree has unrelated changes in `frontend/package.json` and `package-lock.json`; leave them alone.
  - Never commit `.env`.

## Files touched

- `backend/matching/llm.py`, plus tests in `backend/matching/tests/test_llm.py` (step 2 fixes, only if the diagnosis calls for them)
- `backend/config/settings.py`: the embedding calibration constants only
- `.env`, local and uncommitted
- `SMOKE_TESTS.md`, `RESUME_INTELLIGENCE_CHECKLIST.md`, `open-items/RESUME_INTELLIGENCE_OPEN_ITEMS.md`

## Verification

- `test_real_mongo_round_trip` passes, so the full backend suite has no skips when `MONGO_URI` is set.
- `eval_extraction --llm` shows no "unavailable" readings after the step 2 fixes. Experience misses remain only for claim-only resumes, which is by design.
- The search response has `fallback: false`, and the backend and data resumes are the top two.
- The full backend suite still passes with the LLM **off** (the default), so CI and a clean clone are unaffected.
- The Opus verifier re-runs the live steps independently and signs off §5.4.

## Risks

- **Run time.** Each Gemma call takes about 3 minutes on this CPU, so the eval plus the API run is roughly 45–60 minutes of model time. Long steps run in the background.
- **Docker resources.** The Atlas-local image needs about 2 GB of RAM alongside Ollama's ~6.5 GB on a 16 GB Mac. Stop the dev frontend or other heavy apps if memory is tight.
