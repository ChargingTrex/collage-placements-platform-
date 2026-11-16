# Addendum 2 (stages 2–4) + Phase B: implementation checklist

The sources are the Addendum 2 plan (`~/.claude/plans/addendem-2-1-add-a-sharded-quokka.md`),
`agents.md` Phase 4, and the shapes in [`docs/OPPORTUNITIES_API_CONTRACT.md`](docs/OPPORTUNITIES_API_CONTRACT.md).
The decisions are D26–D28 in [`DECISIONS.md`](DECISIONS.md). Stage 1 (marksheets, CGPA entry) was done
2026-10-23 and is recorded in `PROGRESS.md`.

**Rules.**
- Each item gets a failing test before the code that ticks it.
- Sonnet agents build in worktrees, and the orchestrator merges.
- **Only an Opus verifier marks `[x]`**, from its own run.
- A verifier that finds a problem marks the item `[!]` and adds a note under **Findings**.

Legend: `[ ]` not started · `[~]` implemented, awaiting verification · `[x]` verified · `[!]` verification failed

## Progress

| Stream | Status |
| --- | --- |
| G0 Groundwork (orchestrator) | `[~]` |
| QB Checkpoint B tests, red first | `[ ]` |
| S2 Opportunities, applications, notifications (backend) | `[ ]` |
| S3 Suggestions (backend) | `[ ]` |
| S4 Recruiter exports (backend) | `[ ]` |
| FE Frontend for S2–S4 | `[ ]` |
| SEED Demo data | `[ ]` |
| GATE Final gate | `[ ]` |

## G0 · Groundwork (orchestrator)

- [~] `AuditLog.Action` gains every Stage 2–4 action, in one core migration (`0006_phase_b_audit_actions`)
- [~] `CompanyShortlist.source` (`manual` / `application`), with the default `manual` for existing rows (`profiles/0008`)
- [~] Settings: `SUGGESTIONS`, `OPPORTUNITIES`, the `export` throttle rate, and a 0 `certifications` weight slot
- [~] `pyzipper` and `pycryptodomex` pinned in `requirements.txt`
- [~] Contract doc, D26–D28, and the `NEXT_PHASES.md` notification note

## QB · Checkpoint B tests (`backend/checkpoints/test_checkpoint_b.py`), red first

- [ ] `agents.md` Phase 4's six smoke steps, as written
- [ ] `IMPLEMENTATION_PLAN.md` §6's four Phase B boxes
- [ ] `NEXT_PHASES.md` Phase B's eight tests
- [ ] The Addendum 2 Stage 2, 3 and 4 test lists
- [ ] The two notification triggers (D26)
- [ ] Run, and every test is red for a "not built yet" reason

## S2 · Opportunities, applications, notifications

- [ ] `Opportunity`, `Application`, `ApplicationEvent` models with UUID keys. Opportunities belong to a company
- [ ] The status flow `draft → pending_review → open → closed` and `rejected`. Admin-created postings open directly
- [ ] `Opportunity.objects.visible_to`: students see `open` only, recruiters their own company's, admins all
- [ ] Apply: snapshot of the facts and resume, the score stored, D27 shortlist row, and refusals (`not_open`, `deadline_passed`, `already_applied`, `no_resume`, `not_eligible`)
- [ ] Withdraw: status only, never a delete. Removes an application-sourced grant per D27
- [ ] Company shortlist/un-shortlist follow D27 (upgrade and downgrade, never hiding an applicant)
- [ ] Eligibility flag separate from the score. Roster CGPA only
- [ ] Feed ranked by the existing scorer (`profiles.match`), not a second one
- [ ] Status transitions with `ApplicationEvent` and audit; invalid transitions are 400
- [ ] Bulk `screen` over the resume snapshots, with threshold and hard filters
- [ ] Applicant CSV export with PRN first, deterministic order, contact gated, and audited
- [ ] Admin `stats`: by status, per opportunity, and median time to shortlist
- [ ] The company application payload is an allow-list (no marksheets, CGPA claims, career path or transcript; contact gated)
- [ ] Notifications: model, list, mark read, trigger on open, and an idempotent `notify_deadlines`
- [ ] Approval records the JD for role categories (a no-op with the LLM off)
- [ ] `?prn=`/`?prns=` with `unmatched_prns`; unknown parameters are 400; recruiters with no company get 403; out of scope is 404

## S3 · Suggestions

- [ ] `GET opportunities/suggestions`, throttled, with a settings-driven cut and cap
- [ ] The empty state tells `no_open_postings` apart from `none_match`
- [ ] Scores cached by resume digest and posting version, and shared with the feed
- [ ] Works with the LLM off. The page never says "probability"

## S4 · Recruiter exports

- [ ] `CompanyProfileFilter` with `?shortlisted=true` per D27, and `is_shortlisted` annotated (no N+1)
- [ ] CV zip, with the skipped students counted and listed, audited and throttled
- [ ] AES-256 contact zip: needs the password, which is never inside the archive; unverified students get blank contacts with a reason; row cap; audited and throttled
- [ ] **Leak test:** a student who goes hidden after being shortlisted is absent from both exports
- [ ] A company cannot export another company's shortlist

## FE · Frontend

- [ ] Company: an Opportunities page (list, create/edit, submit, close) and an Applicants page (status moves, screening, CSV export)
- [ ] Admin: an approval queue (approve/reject), the ability to create a posting for a company, and an opportunity stats view
- [ ] Student: a jobs board (ranked feed, eligibility, apply, withdraw), "My applications", and a notifications list with an unread badge
- [ ] Student: a Suggestions page, honest framing, with both empty states
- [ ] Company: a Shortlist page with the CV zip and a contact export showing the password once
- [ ] Reuses `MatchDisplay`, `DocumentButton`/`downloadFile`, and the existing UI kit; nav entries per role
- [ ] Tests for each page; `npm test`, typecheck and build clean

## SEED · Demo data

- [ ] `seed_demo` creates opportunities in every status, applications across statuses with events, and notifications; idempotent
- [ ] `DEMO_LOGINS.md` describes them

## GATE · Final gate

- [ ] Checkpoints A, E and B all pass (with the MFA xfail only)
- [ ] The backend suite passes on spaCy and TF-IDF; `makemigrations --check` is clean
- [ ] The frontend passes tests, typecheck and build
- [ ] The `agents.md` Phase 4 smoke test is run **live on `main`**, with its output in `SMOKE_TESTS.md`
- [ ] Docs: `PROGRESS.md`, `TODO.md`, `open-items/OPEN_ITEMS.md` and the Addendum 2 status
- [ ] The real-series grep is empty

## Findings

*(verifiers add notes here)*
