# Implementation Plan — Placement Cell Portal

2026-09-30 · Six agents · Five phases · One QA gate

Governs all work from here. Supersedes the phase plan in [`agents.md`](agents.md)
for sequencing, and keeps its checkpoint-and-smoke-test discipline unchanged.

| Document | Role here |
| --- | --- |
| [`placement-cell-portal-prd.md`](placement-cell-portal-prd.md) | What the product is |
| [`REQUIREMENTS-ADDENDUM.md`](REQUIREMENTS-ADDENDUM.md) | R1–R5, the later additions |
| [`agents.md`](agents.md) | Phase definitions and checkpoint discipline |
| `shared/Identity_Login_Shared_Data.docx` | **Binding** — identity and auth |
| `shared/API_Standards_Integration_Contract.docx` | Partially binding — see §2 |
| [`CONTEXT.md`](CONTEXT.md) · [`agents/`](agents/) | Shared context and the per-agent charters |
| [`DECISIONS.md`](DECISIONS.md) · [`LEFTTODO.md`](LEFTTODO.md) | Decisions, and where to resume |
| [`PROGRESS.md`](PROGRESS.md) · [`SMOKE_TESTS.md`](SMOKE_TESTS.md) · [`TODO.md`](TODO.md) | Running state |

---

## 1. Decisions this plan is built on

Settled 2026-09-30. An agent that finds one of these wrong stops and raises it
rather than working around it.

| # | Decision |
| --- | --- |
| D1 | The portal is a **separate application** that shares the institutional SSO. It is not a module of the student-management-platform. |
| D2 | **Identity and auth are retrofitted first**, before any new feature work. |
| D3 | Build order: retrofit → **agents.md Phases 4–6** → **REQUIREMENTS-ADDENDUM R1–R5**. |
| D4 | **PRN is nine digits** (`220200921`). The transcript is a real issued document and beats the spec's illustrative `21CS1042`. |
| D5 | **Standalone token mode.** The portal issues its own RS256 tokens carrying the exact platform claim contract. Switching to platform SSO later is a key-source configuration change. |
| D6 | **Five feature agents and one QA gate agent.** |
| D7 | Department and programme codes come from the real Sai University list, pending registrar confirmation. |
| D8 | **PRN is the human key; UUID carries every join.** PRN stays unique and immutable, is the login identifier, appears on every screen, export and log line, and every list endpoint filters on it. No foreign key references it. Driven by a stated need to reconcile portal data against registrar exports and spreadsheets — see §3.5. |
| D9 | **Every role has a human key.** Students have a PRN; admins get `ADM-0001`, companies get `CMP-0001` — portal-issued, sequential, unique, immutable, never reused. A **`Company` is its own entity** (id, name, email) with many recruiter logins belonging to it. See §3.7. |

---

## 2. What is binding, and what is not

D1 changes which contracts apply. A separate application that shares a login
must agree on *who the user is*; it does not have to agree on how it shapes its
own URLs.

### Binding — no deviation without raising it

From `Identity_Login_Shared_Data.docx`:

- §2 Identifiers — UUID is the only key; PRN is the human key; email is never a key
- §3 Shared identity record — field list, name rules, email rules, PRN rules, status lifecycle
- §4 Shared reference data — department and programme codes, never invented
- §5 Authentication — login flows, token lifetimes, **§5.4 the claim contract**, MFA, revocation
- §6 Caching and propagation — what may be cached, snapshotting grouping fields
- §7 Who can see what

From `API_Standards_Integration_Contract.docx`:

- §4.1–4.4 Token, claims, role naming, and **authorisation is always local**

### Not binding, but adopted where cheap

Namespace reservations, exposing participation aggregates upward, the full
adapter suite (`StudentDirectory`, `NotificationSender`, `FileStore`,
`AuditSink`), and the consumer-driven contract suite. The portal is not a
module, so it owes the platform nothing.

`IdentityProvider` **is** built as an adapter regardless — it is the seam D5
depends on.

### Deferred by D2 — recorded, not done now

RFC 9457 error format · `/api/v1/<namespace>/…` paths · drf-spectacular with
CI-checked schema · `Idempotency-Key` · error code registry.

These are good practice and the portal should adopt them, but D2 scopes this
retrofit to identity and auth. They land in **Phase E**, and every new endpoint
written before then should be shaped so the later move is mechanical: plural
nouns, snake_case bodies, verb sub-resources for non-CRUD.

---

## 3. Where the code stands

Phases 0–3 are complete: 249 backend tests, 43 frontend tests, a halfway E2E at
30/30 checks. Full detail in [`PROGRESS.md`](PROGRESS.md).

### Already compliant

| Rule | Where |
| --- | --- |
| `full_name` is one field, no first/last split | `accounts.User.full_name` |
| PRN trimmed and upper-cased on input, stored canonically | `roster.normalise_prn`, `User.save` |
| snake_case on the wire | DRF default throughout |
| 404 not 403 where existence is a disclosure | `OwnedEntryViewSet`, `visible_to` |
| Authorisation enforced server-side, never in the UI | `StudentProfile.objects.visible_to` |
| Historical records retained, never deleted | no destructive paths on roster or profile |

### The gap register

Each row is a task with an owner in §5. "Breaks SSO" means the portal cannot
accept a platform token until it is fixed.

| # | Gap | Current | Required | Breaks SSO |
| --- | --- | --- | --- | --- |
| G1 | Primary key | `BigAutoField` integer | UUID v4 on `User` and the student record | Yes |
| G2 | Path parameters | `/profiles/students/<prn>` | UUID in every path parameter; **PRN becomes a first-class filter, not a casualty** — see §3.5 | Yes |
| G3 | Claims | `user_id`, `role`, `prn` | The full §5.4 contract, all keys present, optional as `null` | Yes |
| G4 | Roles | `role`, a single string | `roles`, an array, `lower_snake_case`, `:<uuid>` scope suffix | Yes |
| G5 | Access token lifetime | 60 minutes | 15 minutes | No |
| G6 | Refresh reuse | rotation on, `BLACKLIST_AFTER_ROTATION=False` | reuse of a consumed token revokes the family | No |
| G7 | Signing | HS256 shared secret | RS256 with a published JWKS | Yes |
| G8 | PRN regex | hard-coded in `roster/models.py` | shared configuration | No |
| G9 | Status | `is_active` + `is_placement_eligible` | the six-value lifecycle enum | Yes |
| G10 | Department / programme | free text | codes from the shared list; unknown surfaces as unknown and logs | No |
| G11 | `display_name` | absent | present, defaults to `full_name`, student-settable | Yes |
| G12 | `personal_email` | absent | present, never used for login | No |
| G13 | MFA | none | mandatory for admin roles; `mfa` claim present | No |
| G14 | Revocation | none | status change to suspended or withdrawn kills all sessions | No |
| G15 | Identity access logging | verification only | every access to identity data beyond own record | No |
| G16 | Grouping snapshots | joined live | department, programme and year snapshotted onto records | No |
| G17 | Company modelling | a `User` row with the company name in `full_name` | a `Company` entity with recruiter users belonging to it — see §3.7 | No |
| G18 | Admin / company human key | none — only students have one | `ADM-0001` / `CMP-0001`, portal-issued, immutable | No |

G16 matters more than it reads. Placement reporting by school (R3) joins to the
current student record; a student who changes programme retroactively rewrites
last year's outcome figures.

### 3.5 Reconciliation — the cross-cutting requirement

The placement cell needs to match portal data against registrar exports, the
platform, and its own spreadsheets. That is what PRN exists for — the shared
spec lists its uses as "reconciling across systems, desk lookup, printed on ID
cards, report labels" — and it is the reason D8 keeps PRN prominent while
moving joins to UUID.

Reconciliation is a **feature with its own acceptance criteria**, not a side
effect of having a PRN column. Every agent building an endpoint or an export
owes these.

| Requirement | Why |
| --- | --- |
| `?prn=` filter on **every** list endpoint, and `?company_id=` / `?admin_id=` where the role applies | The single most common lookup; without it, finding one record means paging |
| Batch filter `?prns=a,b,c`, capped at 200 | Reconciling a 400-row spreadsheet one request at a time is unusable. Mirrors the platform's batch contract |
| PRN as the **first column** of every CSV export | A VLOOKUP against a registrar export needs the key where a human expects it |
| PRN in every audit entry and every log line | A cross-system trace is only traceable if both sides name the same student |
| Deterministic exports — fixed column order, explicit `ordering` | Diffing two exports of the same query should show data changes, not row-order noise |
| Exports state the query that produced them | A spreadsheet with no provenance gets reconciled against the wrong cohort |

#### The silent-ignore bug — demonstrated, not hypothetical

`?prn=` does not exist as a filter today, and **django-filter silently ignores
a query parameter it has not declared**. Measured against a three-row roster on
2026-09-30:

```text
  ?prn=220200921            -> 3 results   (expected 1)
  ?prn=999999999            -> 3 results   (expected 0)   <-- no such student
  ?prns=220200921,220200922 -> 3 results   (expected 2)
```

This is the worst available failure mode for reconciliation. A script asking
"is this PRN on the roster?" reads `count > 0` as **found**, and reconciles
against the wrong person — for a PRN that does not exist at all. It fails
open, it fails silently, and the output looks plausible.

Two obligations follow, and they apply to **every** list endpoint in every
module, not just the roster:

- **Declare every filter a caller might reasonably send.** `prn`, `prns`, and
  the module's own fields.
- **Reject unknown query parameters rather than ignoring them.** A typo'd
  `?pm=220200921` must be a 400, not a full-table return. This is a global DRF
  setting, not a per-view fix, and it is A1's to make in Phase A.

#### Input normalisation

`normalise_prn` runs on model save, so stored values are canonical — but a
filter value is never saved. A PRN pasted from a spreadsheet arrives as
`"220200921 "` or `"220200921\n"` or lower case. `search` happens to tolerate
this today; an exact `?prn=` filter will not. **Filter input is trimmed and
upper-cased on the same path as write input.**

#### Unknown PRNs are reported, never dropped

A batch lookup for 400 PRNs that returns 380 rows must name the 20 it could not
find. Silently returning fewer rows than were asked for is how a reconciliation
run quietly under-reports — the same fail-open shape as the bug above.

Owner: **A1** builds the filter and normalisation surface in Phase A. Every
other agent implements the export requirements for their own module, and QA
tests reconciliation per module (§8).

### 3.6 PRN as the document identifier

Confirmed by the registrar 2026-09-30: **PRN is issued once, is unique to each
student, is never reused, and is the identifier printed on their transcript and
other college documents.**

That closes ID-02, and it does more than unblock a regex. It makes PRN the
binding between a student and any official document they upload, which the
portal must actually enforce:

- **Every uploaded document records the PRN it claims**, extracted from the
  document itself where the format carries one. The transcript prints
  `PRN: 220200921` in its header (see
  [`REQUIREMENTS-ADDENDUM.md`](REQUIREMENTS-ADDENDUM.md) § Reference: transcript
  format).
- **The claimed PRN is checked against the signed-in student's own.** A
  mismatch is refused and logged, never stored. Without this a student uploads
  somebody else's transcript and inherits their CGPA — already an R5
  acceptance criterion, now load-bearing rather than defensive.
- **A PRN that appears on a document but matches no roster row is flagged**, not
  dropped. `FlaggedSignup` already models exactly this shape for signups.
- Document storage paths stay keyed on PRN — `core/storage.py` already writes
  `resumes/<prn>/…` and `proofs/<prn>/…`, which is correct and stays.

#### Why this does not make PRN a foreign key

Immutability was the argument against it, and the registrar has now answered
that. Two concrete reasons remain, both visible in the code today:

1. **Admin and company accounts have no PRN.** `accounts.User.prn` is
   `null=True` — "Students only; null for admin/company". The user table holds
   all three roles, so a key on PRN cannot address two of them. The shared spec
   says the same thing in its field table: `student_id` is "null for staff".
2. **`FlaggedSignup` deliberately stores PRNs that match no student.** That is
   the entire point of the roster-matching queue — recording the PRN somebody
   *claimed*. As a foreign key that row could not exist, and the feature would
   have to be deleted.

The shared spec forbids PRN as a foreign key **unconditionally**, and its own
§3.4 already states PRN is assigned once and survives every status change — so
immutability was never the reason it gave. D8 stands.

### 3.7 Identifiers for every role

Reason 1 above — that two of the three roles had no human key at all — is now
fixed rather than merely noted. Every role gets one, on the same terms as PRN:
**unique, immutable, never reused.**

| Role | Human key | Issued by | Example |
| --- | --- | --- | --- |
| Student | `prn` | Registrar | `220200921` |
| Placement admin | `admin_id` | The portal, sequentially | `ADM-0001` |
| Company | `company_id` | The portal, sequentially | `CMP-0001` |

The prefix is the point. An identifier in a log line, an export column or an
audit entry should say what kind of thing it names without a lookup — which a
bare sequence would not.

UUID still carries every join. Three separate human-key spaces make that more
true, not less: one foreign key column cannot reference three of them.

#### `Company` becomes an entity

Currently a company is a `User` row with the company name in `full_name`, a
person field. It becomes a record of its own:

| Field | Notes |
| --- | --- |
| `id` | UUID — what every foreign key references |
| `company_id` | `CMP-0001`, the human key |
| `name` | The organisation, not a person |
| `email` | Organisation contact — careers@, not a recruiter's address |

Recruiter `User` rows gain a foreign key to `Company`. One company, many
logins.

#### The bug this fixes

`CompanyShortlist.company` is currently a foreign key to **`User`**, so a
shortlist belongs to a recruiter rather than to a company. Two recruiters at
the same company therefore hold two separate shortlists — and because
"shortlisted only" visibility is computed from that table, **a student is
visible to one recruiter at a company and returns 404 for their colleague.**

Nothing in the UI would predict that, and it is invisible until a company has a
second account. Repointing `CompanyShortlist.company` at `Company` fixes it.
Phase B must attach opportunities and applications to the `Company` for the same
reason.

#### Authorisation scope — no new claim needed

A recruiter's token has to say *which* company they act for. The shared spec
already has the pattern: §4.3 defines `<role>:<scope_uuid>` for a role scoped
to one object, as in `club_president:9f1c…`.

So a recruiter carries `company_recruiter:<company_uuid>` in the `roles` array,
and the fixed claim contract is untouched. `admin_id` and `company_id` stay out
of the token — they are for display, export and audit, not authorisation, and
the platform has no concept of a placement-portal company.

Per §4.4, the scope is still checked server-side: a token carrying
`company_recruiter:<uuid>` authorises nothing by itself. The portal checks that
this recruiter's company owns the opportunity being edited.

---

## 4. The agents

Five feature agents, each owning a domain end to end — backend, frontend,
migrations, tests — plus one QA agent who owns every gate.

Owning a domain end to end is deliberate. The alternative, splitting by layer,
puts an API seam between two agents on every single feature, and that seam is
where the coordination cost lives.

| Agent | Domain | Owns |
| --- | --- | --- |
| **A1 — Identity** | Auth, users, roster, the platform seam | `accounts/`, `roster/`, `core/`, shared config, the `IdentityProvider` adapter, the frontend auth surface |
| **A2 — Opportunities** | agents.md Phase 4 | `opportunities/`, matching integration for ranking, applications, bulk screening |
| **A3 — Certifications** | agents.md Phase 5 | `certifications/`, catalog, gap-based suggestions, proof verification |
| **A4 — Company & Notifications** | agents.md Phase 6 | Company self-service, notification delivery, analytics dashboard |
| **A5 — Student Records** | REQUIREMENTS-ADDENDUM R1–R5 | Admin profile and resume view, career paths, outcomes dashboard, onboarding form, transcript CGPA |
| **QA — Gate** | Every module | All smoke tests, every E2E run, `SMOKE_TESTS.md`, sole authority to pass a checkpoint |

### Shared surfaces, and who owns them

Everything below is touched by more than one agent. Each has exactly one owner;
everyone else raises a request.

| Surface | Owner | Rule |
| --- | --- | --- |
| `components/ui/` design kit | A5 | Others request a component; nobody edits it in a feature branch |
| `matching/` engine | A2 | Public boundary is `get_engine()`; A5 adds the transcript extractor as a **new** module, never inside the resume path |
| `accounts/permissions.py` | A1 | New role gates are requested, not added |
| `core/storage.py` | A1 | New upload types are requested |
| `conftest.py` fixtures | QA | Agents add module fixtures in their own `tests/conftest.py` |
| `config/settings.py` | A1 | Others append a namespaced dict, never edit existing keys |

### Rules every agent follows

1. **Announce the phase and task before touching code**, as `agents.md` requires.
2. **Commit per completed task**, message naming phase and task.
3. **Never mark a checkpoint or smoke test passed.** Only QA does that.
4. A failing test in another agent's module is **raised, not fixed**.
5. **Never work around a §2 binding rule.** Stop and raise it.
6. Update [`PROGRESS.md`](PROGRESS.md) at the end of each task so a cold session can resume.

---

## 5. Phase A — Identity & Auth Retrofit

**Goal.** Close every SSO-breaking gap in §3, so a platform-issued token would
validate and authorise correctly the day the platform exists.

**Why first (D2).** Phase 4 adds applications, shortlisting and notifications —
a large volume of new code written against the auth surface, every piece of it
carrying user identity. Retrofitting after means writing it twice.

### The five-way split

A1 leads, but the work genuinely divides. Each stream below is a branch.

| Stream | Agent | Work |
| --- | --- | --- |
| **A-1 Keys & status** | A1 | G1, G2, G9 — UUID primary keys, UUID path parameters, **the §3.5 reconciliation surface** (`?prn=`, `?prns=`, filter-input normalisation), the six-value status lifecycle replacing `is_active`/`is_placement_eligible` |
| **A-2 Tokens & claims** | A2 | G3, G4, G5, G6, G7 — the §5.4 claim contract, `roles` as an array, 15-minute access tokens, refresh-reuse family revocation, RS256 with a JWKS endpoint |
| **A-3 Shared config & codes** | A3 | G8, G10 — PRN regex to shared config as `^[0-9]{9}$`, the eight schools and ~45 programmes as a code list, unknown codes surfacing as unknown and logging |
| **A-4 Identity fields & MFA** | A4 | G11, G12, G13, G14, G15 — `display_name`, `personal_email`, MFA for admin roles, revocation on status change, identity access logging |
| **A-6 Company entity & role keys** | A4 | G17, G18 — the `Company` record, recruiter users belonging to it, `admin_id`/`company_id` issuance, repointing `CompanyShortlist.company` at `Company`, `company_recruiter:<uuid>` role scoping |
| **A-5 Fixtures & frontend** | A5 | Regenerate every fixture to nine-digit PRNs and real schools, migrate the frontend auth surface to `roles[]` and `display_name`, update all 43 frontend tests |

A-1 lands first; A-2 through A-5 rebase onto it. The UUID migration touches
every foreign key, so serialising it is cheaper than merging five branches that
each moved the same columns.

### Migration hazards

- **G1 is a destructive migration.** Changing a primary key type rewrites every
  foreign key. Write it as add-column → backfill → repoint → drop, never as a
  single `AlterField`, and prove it on a copy of the demo database first.
- **G9 is not a rename.** `is_placement_eligible` is a placement-cell decision;
  `status` is a registrar fact. They are different concepts and both survive.
  Do not collapse one into the other.
- **G2 changes every frontend URL.** A5 coordinates; the API and the client
  move in one commit, not two.

### Checkpoint A — QA gates

- [ ] Migrations apply cleanly from an empty database **and** from a populated
      Phase 3 database
- [ ] A token carrying the full §5.4 claim set validates and authorises
- [ ] Every claim present; optional values `null`, never omitted
- [ ] `roles` is an array everywhere; no code reads a single `role` string
- [ ] Access token expires at 15 minutes; a replayed refresh token revokes the family
- [ ] A token signed by a second key pair validates against the JWKS endpoint
- [ ] No API path parameter contains a PRN
- [ ] No foreign key references PRN or email
- [ ] PRN regex read from shared config; `220200921` accepted, `PRN2022CS001` rejected
- [ ] **Reconciliation (§3.5):** every list endpoint filters on `?prn=`; batch
      `?prns=` returns matches **and names the PRNs it could not find**
- [ ] **Filter input normalised** — `" 220200921 "`, `"220200921\n"` and lower
      case all match the stored row
- [ ] Every admin has an `ADM-` id and every company a `CMP-` id; both unique,
      immutable, and filterable the same way PRN is
- [ ] **Two recruiters at one company share one shortlist** — the bug in §3.7
      cannot reproduce
- [ ] A recruiter's token carries `company_recruiter:<company_uuid>`, and the
      scope is checked server-side rather than trusted
- [ ] An unknown department code surfaces as unknown and logs — it is never mapped
- [ ] Status change to suspended or withdrawn revokes all sessions immediately
- [ ] MFA required for admin; a non-MFA admin token is refused on admin endpoints
- [ ] Identity access beyond own record appears in the audit log
- [ ] All 249 backend and 43 frontend tests still pass
- [ ] **Full Phase 0–3 E2E re-run, 30/30**, proving the retrofit broke nothing

---

## 6. Phases B–D — the unbuilt PRD (agents.md 4–6)

Built on the retrofitted foundation, in `agents.md` order. Each phase keeps its
own checklist and smoke test from that document; this plan adds only the agent
split and the compliance obligations.

### Phase B — Opportunities Board · A2 leads

Per `agents.md` Phase 4. Beyond that checklist:

- [ ] **Applications create the `CompanyShortlist` relationship.** Without it, a
      student on "shortlisted only" visibility is unreachable by any new
      company — the finding from the halfway E2E, pinned by
      `test_narrowing_to_shortlisted_keeps_the_companies_already_interested`
- [ ] Department, programme and year **snapshotted onto the application row** at
      apply time (G16), never joined at report time
- [ ] Ranking blends skills, eligibility and the Phase 2 engine's similarity
      score; the threshold is read from config, never hardcoded
- [ ] Authorisation local: a company token does not by itself authorise access
      to an opportunity — the portal checks the company owns it

**Support.** A5 builds the student feed and application UI. A4 builds admin
applicant views.

### Phase C — Certification Suggestions · A3 leads

Per `agents.md` Phase 5.

- [ ] Suggestions recompute as skills or open opportunities change
- [ ] Each suggestion carries a reason string naming the skill and the count
- [ ] Proof uploads go through `core/storage.py`, same boundary as resumes
- [ ] Verified completions reach the company-facing profile

### Phase D — Company Self-Service & Notifications · A4 leads

Per `agents.md` Phase 6.

- [ ] Notification channels limited to **in-app and email only**, enforced
      server-side — the platform rejects anything else with 422, and the portal
      matches that policy rather than trusting callers
- [ ] Analytics reflect the PRD's success metrics
- [ ] A company account, unaided, posts an opportunity, screens and shortlists

---

## 7. Phase E — the requirements addendum (R1–R5) · A5 leads

Per [`REQUIREMENTS-ADDENDUM.md`](REQUIREMENTS-ADDENDUM.md), in its own
recommended order. A5 owns all five; other agents support where a module is
touched.

| Task | Notes |
| --- | --- |
| **R1** Admin profile & resume view | API already returns it. UI only. Add identity-access logging (G15) on every resume and transcript open |
| **R2** Career path | Business / Entrepreneurship / Family business stay as three distinct options, each with a one-line explanation beside it |
| **R4** Onboarding form | Collects `personal_email` and `display_name`, both added in Phase A |
| **R3** Outcomes dashboard by school | Groups on **snapshotted** school and programme codes (G16), not live joins. Blocked on registrar confirmation of the programme list |
| **R5** Transcript CGPA | A **new** extractor module. Never inside the resume path — CGPA is never parsed from a resume. Must verify the extracted PRN against the signed-in student's own |

Also in this phase, the deferred API-convention work from §2: RFC 9457 errors,
`/api/v1` namespacing, drf-spectacular with a CI-checked schema, and the error
code registry.

---

## 8. The QA agent

The single most important role in this plan, and the reason it exists as a
separate agent: **an agent that builds a feature cannot impartially decide the
feature works.** Every phase in `agents.md` ends with a smoke test, and the
discipline only holds if someone other than the author runs it.

### Charter

**Owns**

- Every smoke test, one per module, written to the `agents.md` shape
- The comprehensive E2E run at every checkpoint
- [`SMOKE_TESTS.md`](SMOKE_TESTS.md) — real output, never a summary
- The shared `conftest.py` and the fixture set
- The cross-module regression run before every merge to the mainline
- `auth_claims` contract tests — the claim shape D5 depends on

**May not**

- Write feature code. Independence is the whole point.
- Fix a failure it finds. It reports; the owning agent fixes; QA re-runs.

**Sole authority**

- To mark a checkpoint passed. No feature agent may.
- To block a phase transition. A failing smoke test stops the next phase,
  per `agents.md`.

### Per-module smoke tests

One per module, each following the existing pattern — run it for real, record
the actual output, never claim a pass without it.

| Module | Smoke test proves |
| --- | --- |
| Identity | Signup → verify → login → claim contract → revocation → MFA refusal |
| Roster | CSV upload with row errors, nine-digit PRN validation, unknown code surfacing |
| Matching | Extraction against the hand-checked reference; ranking; hard filters; threshold |
| Profiles | Build, resume pre-fill, visibility across all three settings, verification |
| Opportunities | Post → rank → apply → status → bulk screen → export |
| Certifications | Gap → suggestion with reason → proof → verify → appears on profile |
| Company | Self-service post → screen → shortlist → student notified |
| Outcomes | Career path → dashboard counts by school → CSV export |
| Transcripts | CGPA extracted, PRN cross-checked, mismatch flagged, roster stays authoritative |
| **Reconciliation** | Per module: `?prn=` filter, `?prns=` batch reporting misses, PRN first column of every export, whitespace and case tolerated on filter input |

### E2E runs

Three, each a full-lifecycle pass on a fresh database, not a smoke test.

1. **Checkpoint A** — re-run the existing Phase 0–3 E2E unchanged, proving the
   retrofit broke nothing. 30/30 or the phase does not close.
2. **Checkpoint D** — the `agents.md` final comprehensive E2E: every role, every
   lifecycle, the security pass, the performance check.
3. **Checkpoint E** — the same, extended with career outcomes, onboarding and
   transcripts.

### Standing gates on every run

- No 5xx and no tracebacks in the server log
- No console errors in the browser suite
- Every non-2xx is a deliberate refusal asserted by a check
- Identity access beyond own record appears in the audit log
- Latency recorded, not asserted, except search and filter under 500ms

---

## 9. Sequencing

```
Phase A  Identity & Auth Retrofit        A1 leads · all five agents · QA gates
         └─ A-1 keys & status  →  A-2 tokens ┐
                                  A-3 codes  ├─ rebase onto A-1
                                  A-4 fields ┤
                                  A-5 fixtures & frontend ┘
         ▼ Checkpoint A — Phase 0–3 E2E re-run, 30/30

Phase B  Opportunities Board             A2 leads · A5 frontend · A4 admin views
         ▼ Checkpoint B — agents.md Phase 4 smoke test

Phase C  Certification Suggestions       A3 leads · A5 frontend
         ▼ Checkpoint C — agents.md Phase 5 smoke test

Phase D  Company Self-Service            A4 leads · A3 analytics · A5 frontend
         ▼ Checkpoint D — FULL COMPREHENSIVE E2E, every role

Phase E  R1–R5 + deferred API conventions  A5 leads · A1 identity logging
         ▼ Checkpoint E — extended E2E, release gate
```

**During Phase A, agents 2–5 are not idle.** Each writes, for their own module:
the contract tests asserting the new claim shape, the fixtures they will need,
and the smoke test skeleton QA will own. This is real work that cannot be done
later without rewriting, and it means Phase B starts with its harness already
built.

---

## 10. Coordination

- **One branch per stream**, named `phase-<letter>/<agent>-<stream>`.
- **A migration is never written on a feature branch.** It is raised to A1, who
  owns migration ordering. Two agents generating migrations in parallel produces
  a conflict no rebase resolves.
- **The API seam is a contract.** An agent changing a serializer another agent
  reads announces it first. Where the change is breaking, the consumer moves in
  the same commit.
- **QA runs the regression suite before every merge to the mainline.** A merge
  that reddens another module is reverted, not patched forward.
- **`PROGRESS.md` is updated at the end of each task**, not each phase, so a cold
  session resumes without re-reading the history.

---

## 11. Open items that block work

Ordered by what stops first. All but the last are one conversation with the
registrar or IT.

| Ref | Question | Blocks | Owner |
| --- | --- | --- | --- |
| **ID-01 / D4** | Confirm PRN is nine digits | Phase A stream A-3 — one regex in shared config | Registrar |
| ~~ID-02~~ | ~~Is PRN genuinely never reused~~ | **Answered 2026-09-30: PRN is issued once, unique to each student, never reused.** It is the identifier on their transcript and other college documents. Unblocks stream A-3 and makes PRN a safe reconciliation key — see §3.6 | Registrar ✓ |
| **ID-05 / API-04** | The authoritative department and programme code list, current and historical | Phase A stream A-3; R3 cannot group without it | Registrar |
| ID-03 / API-03 | Which provider backs platform SSO | Only the eventual switch from D5's standalone mode, not Phase A | IT |
| ID-04 | Institutional email domain and alumni policy | `personal_email` fallback behaviour (G12) | IT |
| ID-06 | Graduated student access window before deactivation | The `graduated` status in G9 | Registrar |
| ID-07 | Is MFA available on the chosen provider today | G13's implementation, not its design | IT |
| — | Does the portal cover MBA / M.Sc. / Ph.D. cohorts, or undergraduates only | R3's dashboard shape | Registrar |
| — | 3–5 more sample transcripts, and the scanned-document fallback | R5 | Placement cell |

**D4 is a working assumption, not a confirmed fact.** The nine-digit format
comes from one real transcript. If the registrar says otherwise, stream A-3
changes a regex in shared config and nothing else — which is exactly why the
spec insists it lives there rather than in the codebase.

---

## 12. Definition of done

A phase is done when **QA says so**, and QA says so only when:

- Every checklist item in the phase is ticked, with evidence
- The phase's smoke test has been run for real, with output recorded in
  `SMOKE_TESTS.md`
- Every prior phase's smoke test still passes
- The full test suite is green on both similarity backends
- No 5xx and no tracebacks appear in the logs of the run
- `PROGRESS.md` reflects the state a cold session would need
- Every deviation from a §2 binding rule is either fixed or recorded as an
  agreed exception with a reason

A phase is **not** done because the code is written.
