# G: resume reading on Gemma

Owner: G builder. QA: QA-2.

- [ ] G0: Settings for reasoning effort. `LLM_REASONING_EFFORT`, sent as `reasoning_effort` only when set. **Pass when:** there are unit tests for both cases, and the default sends nothing.
- [ ] G1: Demo `.env` values documented in `.env.example`:
  - `LLM_ENABLED=true`
  - `LLM_BASE_URL=http://localhost:11434/v1`
  - `LLM_MODEL=gemma4:e4b`
  - `EMBED_MODEL=nomic-embed-text`
  - `LLM_REASONING_EFFORT=none`

  **Pass when:** `.env.example` documents them, and the main tree's `.env` (untracked) has them.
- [ ] G2: `manage.py eval_extraction --llm` run over all sample resumes on real Gemma. **Pass when:** the Gemma and regex columns are pasted into `SMOKE_TESTS.md` with the date, model and reasoning setting.
- [ ] G3a: Guard against stated facts that aren't in the text. A model-stated date of birth, age, phone or email that does not appear in the resume text is dropped. **Pass when:** a regression test fails without the guard and passes with it, using a real recorded Gemma reply as its fixture.
- [ ] G3b: Every other Gemma mistake seen in G2 is fixed in `matching/llm.py`, each with a regression test on a recorded reply. **Pass when:** Gemma's experience and education readings match the hand-checked reference at least as often as regex does.
- [ ] G4: Time budgets set from measurement. `RESUME_ANALYSIS_TIME_BUDGET_SECONDS` and `LLM_TIMEOUT_SECONDS` must cover about 90 s per call, plus one retry, or the retry is skipped on the live path. **Pass when:** one live upload on localhost finishes with `extraction_source == "llm"` within the budget, with the measured time recorded.
