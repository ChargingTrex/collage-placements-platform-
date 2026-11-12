# Open items: decisions, questions and known problems

Everything that needs a person to act on it. It covers decisions only you can make,
questions for the registrar, IT and the placement cell, known problems, and
housekeeping. Updated 2026-10-21.

**Where things stand:** Phase A (identity retrofit) and the requirements addendum
(R1–R5) are built, verified by an independent reviewer, and committed on local
`main`. Nothing is pushed. Phases B–D (opportunities, certifications, company
self-service) are outlined in [`NEXT_PHASES.md`](../NEXT_PHASES.md), not built.

The resume-intelligence feature (LLM reading, vector search, role categories)
has its own list: [`RESUME_INTELLIGENCE_OPEN_ITEMS.md`](RESUME_INTELLIGENCE_OPEN_ITEMS.md).
See §6 below for which of its items have changed since it was written.

Each item gives a **recommendation** and, under **Today**, what the code does if you change nothing.

---

## 1. Decide before the demo or before publishing

### 1.1 How to publish to GitHub

- **The problem:** the repo `ChargingTrex/collage-placements-platform-` is
  **public**, and early commits in local history contain a real student's PRN,
  from the sample transcript. The current files are clean; only the history
  holds it. A normal `git push` would publish that history.
- **Options:**
  1. **Push a history-free snapshot.** This is one commit with today's files, and your local history stays as it is. The commands are in [`docs/HANDOFF.md`](../docs/HANDOFF.md) §5.
  2. **Make the repo private first,** then push normally.
  3. **Rewrite the history** to remove the PRN from every commit, then push.
- **Recommendation:** option 1, or option 2 if you want the full history on GitHub.
- **Today:** nothing is pushed. The agent was not allowed to run 1 or 3.

### 1.2 Reset your local database once

This is not a decision, but it blocks the demo. The UUID migrations **refuse**
to run on a database created before them (DECISIONS D11). This is deliberate:
otherwise they would silently corrupt it. The commands are at the top of
`DEMO_LOGINS.md`:

```bash
cd backend && rm db.sqlite3
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py seed_demo --with-students
```

### 1.3 The importer warning for a PRN's entry year

- **The proposal:** the roster importer would **warn**, without rejecting, when a
  PRN's first two digits (the entry year) don't fit the batch, for example a
  `22…` PRN in batch 2030. The registrar's data would still win; the warning
  only surfaces likely typos.
- **Decide:** build it or drop it.
- **Today:** not built. The helper `prn_entry_year()` exists in `roster/reference.py` and nothing uses it.

---

## 2. Questions for other people

### Registrar

| Ref | Question | Why it matters | Today |
| --- | --- | --- | --- |
| ID-01 | Is the PRN always nine digits, `YY0200NNN`? What do the middle `0200` digits mean? | The PRN rule is a single setting (`PRN_REGEX`), so a different answer means one edit there | Nine digits enforced. The template comes from one real transcript |
| ID-05 | The authoritative list of programmes, both current and historical | R3 groups the outcomes dashboard by school. The list in `roster/reference.py` comes from the university website, which lists more specialisations on school pages than on the home page | Website-derived list. Unknown codes are stored as given and reported, never remapped |
| — | Should the portal cover MBA, M.Sc. and Ph.D. cohorts, or undergraduates only? | It decides R3's scope. Also, "Ph.D." appears under several schools, so its school can't be inferred | All cohorts |
| ID-06 | How long does a graduated student keep access? | The `graduated` status | Access is not cut off automatically |
| — | A real `year_of_study` in the roster export | Every row of the sample roster says 4, including students who would have graduated by now | 4 for everyone in the sample |

### IT

| Ref | Question | Why it matters |
| --- | --- | --- |
| ID-03 | Which SSO provider will the college use? | Only for the eventual switch from the portal's own tokens to the college SSO. That is a configuration change by design (D5) |
| ID-04 | The institutional email domain and the alumni email policy | Whether `personal_email` becomes the contact address after graduation |
| ID-07 | Can the chosen SSO provider do MFA today? | It shapes the post-demo admin MFA (§3.1) |

### Placement cell

| Question | Why it matters | Today |
| --- | --- | --- |
| **3–5 more real transcripts**, read locally and never committed | The transcript parser was built from one real transcript plus synthetic copies. A layout where a line wraps differently could break the name or degree reading | A transcript the parser can't read is not lost: it opens a CGPA review, and the student types the value for an admin to check |
| Is there a scanned-document fallback beyond manual entry? | Scanned transcripts have no text to read | The student types the CGPA and an admin reviews it |

---

## 3. Product decisions

### 3.1 Admin MFA (after the demo)

- **Decided:** an emailed one-time code as the second factor for admins (DECISIONS D23).
- **Still open:** the code length, how long it stays valid, and whether a device is remembered and for how long.
- **Today:** admins sign in with a password only. The `mfa` claim is `false`. The test
  that will enforce MFA is marked as an expected failure, and it starts failing
  the day MFA is built, which reminds whoever builds it to remove the marker.

### 3.2 CGPA check tolerances (R5)

When a transcript is uploaded, a review opens for an admin if any of these hold:
- the printed CGPA differs from the roster by more than **0.05**;
- the printed CGPA differs from the CGPA recomputed from the semester table by more than **0.02**;
- no CGPA could be read.

**Confirm these thresholds.** The roster CGPA is never overwritten (D24).

Separately, resume intelligence compares a **resume's** CGPA with the roster
at a tolerance of **0.1**, as an admin-only flag. See its doc, item 2.13.

### 3.3 The wording of the R5 rule

The addendum originally said "CGPA is never parsed from a resume". Resume
intelligence does read it, but only to flag a mismatch for admins (D19). The
acceptance line now reads: "A resume never supplies the CGPA: no resume upload
writes any CGPA field, and nothing in the profile flow pre-fills one from it."
**Confirm this wording, or ask for the stricter rule.** The stricter rule would
mean removing the resume-CGPA flag from resume intelligence.

### 3.4 Should verification flags compare against the transcript CGPA?

Resume verification compares a resume's CGPA with the roster only. Now that
transcripts are parsed, it could compare all three. This is resume-intelligence
code, so **decide whether to wire it in.**

### 3.5 Phase B questions, to answer before it starts

From [`NEXT_PHASES.md`](../NEXT_PHASES.md):
- **Can a student withdraw an application?** Recommendation: yes, as a status, never a deletion.
- **Should there be one resume per application, or can a student attach a different one per opportunity?**
- **How much should a verified certification count** in opportunity ranking (Phase C into B)? The PRD says it should count, but gives no weight.

### 3.6 Building ahead of the phase order

Resume intelligence and the addendum (R1–R5) were built before Phases B–D,
while `agents.md` says to work phase by phase. **Accept this as a recorded deviation,
or schedule a review** before Phase B builds on them.

### 3.7 When to adopt the API conventions

These were deferred by D2:
- the RFC 9457 error format;
- `/api/v1/` paths;
- a schema that CI checks.

New endpoints are shaped so that the move is a rename. **Decide when:**
before Phase B, so B is written once, or after Phase D.

---

## 4. Known problems

Each one is also in [`TODO.md`](../TODO.md).

### Before any real deployment

| Problem | Effect | Fix |
| --- | --- | --- |
| **The frontend never refreshes the access token** | Everyone is signed out after 15 minutes. That includes opening a resume after a quiet spell | Retry once through `/api/auth/refresh` on a 401 |
| **No browser test drives the real app** | The frontend tests run in a simulated browser and against mocked APIs. Nothing clicks through the built app in a real browser | Add Playwright: signup, then profile, then resume upload, then company search |
| **`docker compose up` has never been run end to end** | The Postgres path is only exercised in CI | Run it once from a clean clone |
| **`EXPOSE_OTP_IN_RESPONSE` must be off in any deployment** | It returns the login code in the API response. That's convenient for the demo and unsafe anywhere real | Add a deploy-time check |
| **`DEMO_LOGINS.md` holds plain-text passwords** | It is gitignored and local-only | Never copy it anywhere shared |

### Worth fixing, not urgent

| Problem | Effect |
| --- | --- |
| On the onboarding page, the optional transcript upload sits below "Save and continue" | Students may submit before they see it |
| `StudentProfile.transcript_text` is never filled | An empty column. Either fill it or drop it |
| Two seeded demo students have resumes that name another person | Rohan's resume is Kabir's sample, so a name-mismatch flag may show for him in a demo |
| `CASES["wrong_prn"]` in the test fixtures lists the CGPA as empty, but the PDF prints one | It only misleads a reader |
| Login takes about 1 s | This is password hashing doing its job. Revisit only if it becomes a bottleneck during a drive |
| Admin stats load every profile to compute completion | Fine at one college's size |
| Skills are free text per profile | Phase C's certification tags will want a catalogue |
| The spaCy matching backend serialises on a lock | Bulk screening of hundreds of resumes at once should move to a worker |

### Phase B must not repeat these

These come from bugs already found once, and [`NEXT_PHASES.md`](../NEXT_PHASES.md) lists them as binding:
- **An application must create the company shortlist link.** Without it, a student on "shortlisted only" visibility can never be reached by a new company.
- **Opportunities belong to a company, never to a recruiter.**
- **Department, programme and year are copied onto the application when the student applies.**

---

## 5. Housekeeping

1. **Leftover worktrees.** There are 14 agent worktrees under `.claude/worktrees/`, all locked. Their work is all on `main`, so they can be removed. Two were merged with small edits and so don't match by commit ID: the 1c/1d work is `83f512e` on `main`, and the resume-intelligence V-fixes are `454ca14`. Separately, `../collage-placements-phase-a` (branch `phase-a-addendum`) is stale and unused.
2. **The backup branch `backup/pre-scrub`.** It holds the history from before the real PRN was scrubbed. Keep it until the push decision (§1.1) is made. **Never push it.**
3. **After the next migrate on any database with resume intelligence on**, run `manage.py reindex_vectors` and then `manage.py recategorise`. See [`PROGRESS.md`](../PROGRESS.md).

---

## 6. Changes to the resume-intelligence list

[`RESUME_INTELLIGENCE_OPEN_ITEMS.md`](RESUME_INTELLIGENCE_OPEN_ITEMS.md) was
written on 2026-10-19. Since then:

- **Its §4.1, "another session's uncommitted edits", is resolved.** Those were
  this work's PRN changes. They were committed, and then remapped again to the
  entry-year form (`22…` for batch 2026).
- **Its §4.4 and §2.16 still stand.** A remote now exists but nothing is pushed (see §1.1). The repo's own QA gate has still not been run over the resume-intelligence work.
- **Its §2.13 is partly answered.** R5 is built, so a transcript CGPA now exists, but the verification flags don't use it yet (§3.4).
- **Its D-numbers are unchanged.** Phase A's new decisions are D23–D25, so they don't collide with resume intelligence's D15–D22.

---

## Quick list

- [ ] 1.1 Choose how to publish to GitHub
- [ ] 1.2 Reset the local database before the demo
- [ ] 1.3 Build or drop the PRN entry-year warning
- [ ] 2 Registrar: PRN format, programme list, cohort scope, graduate access, `year_of_study`
- [ ] 2 IT: SSO provider, email domain and alumni policy, MFA availability
- [ ] 2 Placement cell: 3–5 more real transcripts
- [ ] 3.1 Admin MFA details (code length, expiry, remembered devices)
- [ ] 3.2 Confirm the CGPA tolerances (0.05, 0.02)
- [ ] 3.3 Confirm the R5 wording, or ask for the stricter rule
- [ ] 3.4 Feed the transcript CGPA into the verification flags?
- [ ] 3.5 Phase B: withdrawals, one resume per application, certification weight
- [ ] 3.6 Accept or review building ahead of the phase order
- [ ] 3.7 When to adopt the API conventions
- [ ] 4 Before deployment: token refresh, Playwright, `docker compose`, the OTP exposure check
- [ ] 5 Remove the leftover worktrees; keep `backup/pre-scrub` private
- [ ] Resume intelligence: see its own quick list
