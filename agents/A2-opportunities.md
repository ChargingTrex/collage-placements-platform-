# A2 — Opportunities Board

Read [`CONTEXT.md`](../CONTEXT.md) first. Your phase is **B**, after Checkpoint A.

## You own

`opportunities/` (empty scaffolding today) and the `matching/` engine's public
boundary. Build to `agents.md` Phase 4.

## Beyond that checklist — four obligations

1. **Applications must create the `CompanyShortlist` relationship.** A company
   can shortlist only a profile it can already see, so a student on
   "shortlisted only" visibility is unreachable by any *new* company. The
   application flow is the only legitimate route in. Pinned by
   `profiles/tests/test_authorization.py::TestShortlisting::test_narrowing_to_shortlisted_keeps_the_companies_already_interested`.
2. **Snapshot department, programme and year onto the application row** at apply
   time (G16). Never join at report time — a student who changes programme would
   otherwise retroactively rewrite last year's figures.
3. **Attach opportunities and applications to the `Company` entity**, not to a
   recruiter `User`. See `IMPLEMENTATION_PLAN.md` §3.7 for the bug this avoids.
4. **Authorisation is local.** A token carrying `company_recruiter:<uuid>`
   authorises nothing by itself — check that this recruiter's company owns the
   opportunity.

## The matching engine

`get_engine()` is the boundary. Do not reach past it.

Two backends with **different numeric scales** — spaCy content-word cosine sits
around 0.85, TF-IDF around 0.10. **Never hardcode a threshold.** Read
`engine.default_threshold` or the backend's `suggested_threshold`.

`screen()` returns three groups — ranked, below-threshold, and hard-filter
excluded with a reason — because an admin looking at an empty shortlist needs
to know *why* it is empty.

### Match score and role categories (Resume Intelligence Tasks 6 and 7)

An `Opportunity` ranks students with
`get_engine().match_score(profile_payload, opportunity.description, job_facts=…)`,
not with its own scorer. It returns a 0–100 score, its breakdown (semantic,
skills, experience, education, each with the weight used), matched and missing
skills, and the hard-filter failures, so the relevance rank and the
eligible/not-eligible flag both come from one place. Build the payload with
`profiles.match.profile_payload(profile)` and the JD reading with
`profiles.match.read_job(text)`, which works with the LLM off. Calibration and
weights live in `settings.MATCH_SCORE`; do not hardcode either. Each
Opportunity's description should also feed role categories: once the LLM has
read it (`JobFacts` with a `canonical_role`), call
`matching.categories.record_job_description(job_facts, jd_vector, model=…)`,
the same hook the `/api/matching/*` endpoints use, so categories reflect what
recruiters actually post.
