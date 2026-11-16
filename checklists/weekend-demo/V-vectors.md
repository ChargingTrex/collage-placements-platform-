# V: vector search and role categories

Owner: V builder. QA: QA-2. Uses only `nomic-embed-text`, never Gemma, and never runs while G2 or P6 are running.

- [ ] V1: The `pymongo` pin installs, and `manage.py init_vector_index` runs. **owner: user (needs U3)**
- [ ] V1-local: Without MongoDB, the local vector store is used with real nomic embeddings. **Pass when:** `reindex_vectors` stores vectors whose length equals the nomic output (768) and are tagged with the model name.
- [ ] V2: The skipped MongoDB test passes with `MONGO_URI=... pytest matching/tests/test_vectorstore.py`. **owner: user (needs U3)**
- [ ] V3: `manage.py reindex_vectors` (full), then `manage.py recategorise`. **Pass when:** both exit 0 on the demo database, and no vectors from another model or dimension remain.
- [ ] V4: JD search check on real embeddings. **Pass when:** the sample backend JD ranks both backend resumes above the other three, and a "Backend Engineer" category exists afterwards.
- [ ] V5: The four provisional numbers are re-measured on real nomic embeddings:
  - embedding floor and ceiling
  - `CATEGORY_MERGE_THRESHOLD`
  - `SKILL_ALIAS_SUGGESTION_THRESHOLD`
  - `CATEGORY_MIN_FIT`

  **Pass when:** the measurements and the chosen values are in `SMOKE_TESTS.md`, and the values are in `.env.example` and the settings defaults.
