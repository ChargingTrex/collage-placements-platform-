# Decisions

Every decision taken on the Placement Cell Portal, with the reasoning and what
was rejected. A decision recorded without its alternative is just an assertion;
the point of this file is that a later reader can tell whether the reason still
holds.

Current state and remaining work: [`LEFTTODO.md`](LEFTTODO.md).
Phase plan and agent split: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

---

## Approach

### Phases, checkpoints, and smoke tests that are actually run

The build follows [`agents.md`](agents.md): phases in order, each ending in a
checkpoint, each checkpoint ending in a smoke test that is **run for real with
its output recorded** in [`SMOKE_TESTS.md`](SMOKE_TESTS.md). A failing smoke
test blocks the next phase.

This is not ceremony. It found six real bugs in Phases 0–3 — a flagged-signup
queue that was always empty, half the API answering 301, a regex that read the
English word "be" as a bachelor's degree, a similarity threshold with no useful
range. None were found by reading code. All were found by running something and
looking at the output.

### Tests are written before the checkbox, and must fail first

Added 2026-10-01 at the user's direction, and it is the strongest rule here.

> The smoke test for a checkbox is written **before** the work that ticks it,
> and it must fail first.

A test written after the code tends to assert what the code does. A test
written before it asserts what the checkbox *claims*, which is the thing being
verified. When a test written first passes immediately, that is information:
either the work was already done, or the test is not testing what you think.

It paid for itself within the hour — see §D11.

### One QA agent owns every gate

An agent that builds a feature cannot impartially decide the feature works. QA
owns every smoke test, every E2E run, and is the only role that can mark a
checkpoint passed. It may not write feature code, and it may not fix a failure
it finds — fixing it destroys the evidence it was ever broken.

### Agents own a domain end to end, not a layer

Five feature agents, each owning backend, frontend, migrations and tests for
one domain. Splitting by layer would put an API seam between two agents on
every single feature, and that seam is where coordination cost lives.

---

## The decisions

### D1 · The portal is a separate application sharing the SSO

**Not** a thirteenth module of the student-management-platform.

Nothing in the ecosystem docs mentions placements — every "placement" hit in
`MASTER_SPEC.md` is the word "re**placement**". So its status was undecided and
had to be chosen.

**Consequence:** the identity and auth contracts are binding; the API
conventions, namespace reservations, upward aggregates and full adapter suite
are not. A separate application that shares a login must agree on *who the user
is*; it does not have to agree on how it shapes its own URLs.

**Rejected:** full module status (more work than the relationship warrants),
and ignoring the contracts entirely (guarantees the integration rewrite they
exist to prevent).

### D2 · Identity and auth are retrofitted before any feature work

Phase B adds applications, shortlisting and notifications — a large volume of
new code written against the auth surface, every piece carrying user identity.
Retrofitting after means writing it twice.

**Cost accepted:** roughly one phase of delay before anything visible ships.

**Rejected:** retrofit in parallel (two agents collide on permissions,
serializers and every fixture), and retrofit last (largest rework, SSO seam
unproven longest).

### D3 · Build order: retrofit → agents.md Phases 4–6 → R1–R5

The unbuilt half of the original PRD comes before the later additions.

### D4 · PRN is nine digits

`220200921`, not the shared spec's illustrative `21CS1042`.

A real issued transcript beats an example in a document. The spec itself
insists the regex live in shared configuration precisely so this can change
without touching code.

### D5 · Standalone tokens carrying the exact platform claim contract

The portal issues its own RS256 tokens with the §5.4 claim set. Switching to
platform SSO later changes the key source and nothing else.

This is the spec's own §5.2: keep the claim structure identical from day one,
and integration becomes a configuration change rather than a rewrite of every
piece of code that reads a token.

### D6 · Five feature agents, one QA gate

### D7 · Department and programme codes from the real Sai University list

Eight schools, ~45 programmes, taken from the institution's own site. Pending
registrar confirmation — the school pages list more specialisations than the
homepage, so the marketing site is not authoritative.

### D8 · PRN is the human key; UUID carries every join

PRN stays unique, immutable, the login identifier, on every screen, export and
log line, and a filter on every list endpoint. **No foreign key references it.**

Driven by a real need: reconciling portal data against registrar exports and
spreadsheets. That is what the spec says PRN is for — "reconciling across
systems, desk lookup, printed on ID cards, report labels".

**Rejected: `email + PRN` as a compound key.** Strictly worse than either field
alone. Email is mutable, so every address change would rewrite every child row —
the exact failure the spec describes — and PRN is already unique, so email adds
no integrity, only fragility.

**Rejected: PRN as a foreign key.** Immutability was the first objection and the
registrar answered it (§D10), but two reasons remain, both visible in the code:
admin and company accounts have no PRN at all (`User.prn` is `null=True`), so a
key on PRN cannot address two of the three roles; and `FlaggedSignup`
deliberately stores PRNs matching no student, which is the entire point of the
roster-matching queue — as a foreign key that row could not exist. The spec
forbids it unconditionally, and its own §3.4 already assumed immutability, so
immutability was never its reason either.

### D9 · Every role has a human key, and `Company` is an entity

Students have a PRN; admins get `ADM-0001`, companies `CMP-0001` — portal-issued,
sequential, unique, immutable, never reused. The prefix is the point: an
identifier in a log line or an export column should say what kind of thing it
names without a lookup.

`Company` becomes a record of its own — `id` (UUID), `company_id`, `name`,
`email` — with recruiter users belonging to it.

**This fixes a live bug.** `CompanyShortlist.company` is a foreign key to
`User`, so a shortlist belongs to a *recruiter*. Two recruiters at one company
hold separate shortlists — and since "shortlisted only" visibility is computed
from that table, a student is visible to one recruiter and returns 404 for
their colleague. Invisible until a company has a second account.

**No new claim was needed.** The spec's §4.3 already defines
`<role>:<scope_uuid>`, so a recruiter carries `company_recruiter:<company_uuid>`
in `roles` and the fixed claim contract is untouched. `admin_id` and
`company_id` stay out of the token — they are for display, export and audit,
not authorisation.

### D10 · PRN is issued once and never reused

Confirmed by the registrar 2026-09-30, closing `ID-02`, which both shared specs
listed as blocking.

More than a regex unblock: PRN is the identifier on a student's transcript and
other college documents, which makes it the **binding between a student and any
official document they upload**. Every upload records the PRN it claims, that
PRN is checked against the signed-in student's own, and a mismatch is refused
and logged rather than stored. Without that check, a student uploads somebody
else's transcript and inherits their CGPA.

### D11 · The UUID migration refuses on a populated database

Taken 2026-10-01 during stream A-1. **Confirmed 2026-10-20** by the product owner:
refuse loudly; Checkpoint A's first checkbox is re-scoped to match.

Django reports the integer→UUID primary key change as `OK` on a populated
database and silently leaves the integer `1` sitting in a UUID column. Every
subsequent read then raises `badly formed hexadecimal UUID string` — including
the reads Django does to log you in.

Checkpoint A's first checkbox — *"migrations apply cleanly from a populated
Phase 3 database"* — would have been ticked on that green output. This is the
test-first rule earning its keep: the checkbox was about to be satisfied by
something that had destroyed the database.

A full backfill would have to rewrite ten columns, three of them in Django's
own tables (`auth_user_groups`, `auth_user_user_permissions`,
`django_admin_log`). The portal is pre-production and its only data is
synthetic, regenerated by `seed_demo`, so the migration now **refuses loudly**
and names the reset path.

If a database with data worth keeping ever exists, the full backfill has to be
written; the migration's docstring describes its shape. Until then the gate is
`TestMigrations::test_the_uuid_migration_refuses_loudly_on_a_populated_phase_3_database`:
migrate exits non-zero, the message names the reset path, and no row changes.
`roster/0004` and `profiles/0005` carry the same guard.

### D12 · Unknown query parameters are a 400, not an ignored filter

Taken 2026-09-30 after measuring it.

django-filter silently ignores a parameter it has not declared. Against a
three-row roster, `?prn=220200921` returned **all three**, and so did
`?prn=999999999` for a PRN belonging to nobody. A reconciliation script reading
`count > 0` as "found" matches the wrong student, for a student who is not
there. It fails open, silently, and the output looks plausible.

`RejectUnknownQueryParams` is installed globally, ahead of the other backends.
A typo'd `?pm=` is now a 400.

### D13 · Status and placement eligibility are different things

`status` is a registrar fact about enrolment — the spec's six-value lifecycle.
`is_placement_eligible` is a placement-cell decision about participation. Both
exist, and neither implies the other. Collapsing them would mean the placement
cell could not bar a student from a drive without appearing to withdraw them
from the college.

### D14 · Profiles are addressed by the student's UUID

Not the profile row's. `student_id` is what a platform token carries, so a
caller holding a token can build the URL without a lookup.

### D15 · Resume intelligence runs on a Llama the college hosts

Ollama on a laptop in development, a private Ollama server in production —
never a third-party API. The PRD's privacy rule says resumes are seen by the
student, admins and opted-in companies; a hosted model provider is none of
those. The client speaks the OpenAI-compatible `/v1` API, so the model is a
setting, not a rewrite. See `RESUME_INTELLIGENCE_PLAN.md`.

### D16 · Every new service is optional

`LLM_ENABLED=false` means regex extraction; no MongoDB means a local vector
table with numpy cosine. A clean clone and CI need neither, exactly as the
engine already treats spaCy. Both services sit behind compose profiles
(`llm`, `vectors`), so the Phase 0 bring-up is unchanged.

### D17 · The model's arithmetic is never used

Resume text is untrusted: it can carry instructions aimed at the model. The
reply is validated field by field, levels are clamped to UG/Masters/PG, and
total experience is recomputed in Python from each entry's dates — and only
from entries whose start year is actually written on the resume. When the
model's dated entries exist they beat a stated claim; the claim stays in
`agreement` so a mismatch is flagged rather than believed.

### D18 · Age is read, and shown to admins only

Extracted for plausibility checks — 16–35, a stated age against the date of
birth, graduating age against the roster batch — and never a filter, a
ranking input, or anything a company sees. Anything more invites age
discrimination.

### D19 · A resume's CGPA is a flag, never a value

A narrowing of R5. The resume CGPA is compared with the roster's (and the
transcript's, once R5 lands) and a gap over `VERIFICATION["CGPA_TOLERANCE"]`
raises an admin flag naming both sources. It is never stored as a profile
value and never touches eligibility: the roster stays authoritative.

### D20 · Verification flags advise; a human decides

Computed on demand from the stored reading and the current form, never stored,
shown only to admins, and never blocking `mark_verified`. A `warning` is a
hard-fact mismatch; an `info` has innocent explanations. A resume is a claim,
not proof.

### D21 · MongoDB holds vectors, never resumes, and never decides visibility

A vector document is a student UUID, the vector, the model that made it, and
the six filter fields — no resume text, no contact details. Search returns
candidate ids that then pass through `StudentProfile.objects.visible_to`, so a
hidden profile cannot surface even when the store returns its id.

### D22 · Role categories come from recruiters' job descriptions

Not a fixed taxonomy. Each JD a company or admin scores is read into a
canonical role and its skills, merged by name and centroid similarity, and
students are placed in their best-fitting one to three roles. A student's own
"check my fit" JD never feeds a category. No JDs, no categories: the UI says so
rather than inventing them.

### D23 · Admin MFA waits until after the demo

Taken 2026-10-20 by the product owner. The shared spec makes MFA mandatory for
admin roles (G13). It will be an emailed one-time code as the second factor,
built after the demo. Until then the `mfa` claim is present and `false`, and
`TestAdminMfa::test_an_admin_token_without_mfa_is_refused_on_admin_endpoints`
is a **strict** xfail: the day MFA lands, that test passes and the xfail
fails, which is the reminder to remove it.

### D24 · The addendum's recommendations are accepted as written

Taken 2026-10-20. Every "Recommendation" in `REQUIREMENTS-ADDENDUM.md` stands:

- Career path is single-select, plus an `also_attending_placements` flag.
- `placement` and `undecided` are both options.
- Companies never see career path or transcripts.
- Onboarding is a dismissible prompt and banner, not a gate. Phone and career path are required.
- A CGPA mismatch is flagged for an admin. The roster CGPA stays authoritative.
- The outcomes dashboard covers every cohort, grouped by school and filterable by batch.
- Every resume or transcript an admin or company opens is audit-logged.

The shapes are pinned in `docs/ADDENDUM_API_CONTRACT.md`.

### D25 · Student documents are served only through authenticated endpoints

Taken 2026-10-20. Resumes used to be linked straight from `MEDIA_ROOT`, which
anyone with the URL could fetch. Resumes and transcripts are now served by API
views that check who is asking (own, admin, or a company the profile is
visible to). Each admin or company open writes a `document_accessed` audit row.
Companies never get a transcript.

---

## Deferred, deliberately

Recorded so nobody thinks they were missed. All land in Phase E.

| Thing | Why deferred |
| --- | --- |
| RFC 9457 error format | D2 scopes the retrofit to identity and auth |
| `/api/v1/<namespace>/…` paths | Same |
| drf-spectacular with a CI-checked schema | Same |
| `Idempotency-Key` | Same |
| Error code registry | Same |

Every endpoint written before Phase E should be shaped so the move is
mechanical: plural nouns, snake_case bodies, verb sub-resources for non-CRUD.

---

## Open questions that will become decisions

The career-path, onboarding, transcript-visibility and CGPA-mismatch questions
are answered by D24.

| Ref | Question | Blocks | Owner |
| --- | --- | --- | --- |
| ID-05 / API-04 | The registrar's authoritative department and programme code list | A-3, R3 | Registrar |
| — | Does the portal cover postgraduate cohorts, or undergraduates only | R3 | Registrar |
| ID-03/04/06/07 | SSO provider, email domain, graduate access window, MFA availability | The eventual switch out of standalone mode | IT / Registrar |
