# Requirements Addendum — Career Outcomes, Onboarding & Transcripts

2026-09-24 · Extends [`placement-cell-portal-prd.md`](placement-cell-portal-prd.md)

## Why this addendum

The original PRD assumes every student is heading for placement. In practice a
final-year cohort splits several ways — higher studies, a family business, UPSC
preparation — and the placement cell needs those numbers as much as the
placement ones. A student who is not job-hunting is not a gap in the data; they
are a different outcome, and today the portal has nowhere to record it.

Three further gaps follow from that:

- the placement cell cannot open a student's profile or resume from the admin
  UI, only verify it from a list;
- nothing collects a student's details when they first register, so profiles
  start empty and stay that way;
- CGPA comes from the roster or is inferred from a resume, rather than from the
  document that actually carries it — the transcript.

Five requirements below. Each states what is being asked for, what already
exists in the codebase, what "done" means, and what still needs a decision.

---

## R1 — Placement admin can view a student's full profile and resume

**Requirement.** From the admin area, open any student and see their complete
profile — experience, projects, skills, links — and open or download their
uploaded resume.

**What already exists.** The API is done. `AdminProfileSerializer` already
returns every field the student sees, including `resume_url`, and
`GET /api/profiles/admin/<prn>` already works and ignores the student's
visibility setting, as it should for the placement cell.

**What is missing.** The admin UI. [`ProfilesPage.tsx`](frontend/src/pages/admin/ProfilesPage.tsx)
renders a list with a verify button and nothing else — there is no detail
route, and the resume link is never surfaced. The data is one fetch away.

**Acceptance criteria.**

- [x] An admin can click a student in the profile list and reach a detail page
- [x] That page shows experience, projects, skills, summary, links, and the
      roster facts (department, batch, CGPA)
- [x] The resume opens in a new tab or downloads, with the original filename
- [x] The transcript (R5) is reachable the same way
- [x] Verification can be applied or revoked from the detail page, not only
      from the list
- [x] A hidden profile is still fully visible here — the placement cell is
      never subject to the student's visibility setting
- [x] Opening a resume is written to the audit log, alongside the existing
      verification entries

**Open question.** Should viewing a resume be audit-logged, or only
verification actions? Logging every view is more defensible for a privacy
review but adds noise to the log.

---

## R2 — Career path on the student profile

**Requirement.** Every student declares what they are pursuing after
graduation. One selection from a fixed list, with a free-text field when they
choose "Other".

**Options, as specified.**

| Value | Label |
| --- | --- |
| `placement` | Placement / campus recruitment |
| `business` | Business |
| `higher_studies` | Higher studies |
| `entrepreneurship` | Entrepreneurship |
| `research` | Research |
| `family_business` | Taking over family business |
| `competitive_exams` | Preparation for competitive exams / UPSC |
| `other` | Other — free text, required when selected |
| `undecided` | Not decided yet |

`placement` and `undecided` are not in the original list but are needed: without
`placement` there is nothing to compare the other outcomes against, and without
`undecided` every student who has not yet chosen is silently miscounted as
whatever the default is. Both should be confirmed.

**Acceptance criteria.**

- [x] A `career_path` field on `StudentProfile`, with the values above
- [x] A `career_path_detail` text field, required and only meaningful when
      `career_path` is `other`; the API rejects a blank detail with `other`
      selected
- [x] The student sets it on their own profile and can change it at any time
- [x] It appears in the admin profile list and detail view
- [x] It counts towards profile completion
- [x] Companies do **not** see it — a recruiter learning a student is preparing
      for UPSC changes how that student is treated, and this field exists for
      the placement cell's planning, not for screening
- [x] Students who choose a non-placement path keep full access to the portal;
      nothing is hidden or disabled on the basis of this field

**Open questions.**

1. **Is one selection enough?** A student preparing for UPSC *and* attending
   placements is common. Single-select keeps the dashboard arithmetic clean;
   multi-select is more honest. Recommend single-select as the primary answer
   plus a separate `also_attending_placements` boolean, which keeps the
   headline numbers unambiguous.
2. **Should companies really not see it?** Stated above as a firm no. If the
   placement cell wants it visible, that needs to be a deliberate decision, not
   a default.
3. **Resolved — all three stay as separate options.** Confirmed 2026-09-24.
   They are distinct outcomes and the dashboard counts them separately:

   | Option | Means |
   | --- | --- |
   | Business | Joining an existing business that is not the family's |
   | Entrepreneurship | Founding a new venture |
   | Taking over family business | Joining or succeeding in the family's business |

   Because the three read similarly, the UI must carry that one-line
   explanation beside each option rather than the label alone — otherwise
   students self-select inconsistently and the dashboard splits on noise.

---

## R3 — Placement admin dashboard, career outcomes by school

**Requirement.** A dashboard showing how many students fall into each career
path, broken down by school, with counts.

**Acceptance criteria.**

- [x] A total count per career path across the whole cohort
- [x] The same counts broken down by school, as a table: schools down the side,
      career paths across the top, counts in the cells, totals on both margins
- [x] Filterable by batch / graduating year, so one year's cohort can be read
      on its own
- [x] Students who have not yet chosen appear as `undecided` rather than being
      dropped from the totals — a dashboard whose columns do not sum to the
      cohort size is worse than no dashboard
- [x] Counts reflect all students with an account, not only verified profiles
      (with verified shown separately if useful)
- [x] Exportable as CSV, since these numbers end up in a report to the college
- [x] Reuses the existing `/api/profiles/admin/stats` endpoint or sits beside it

**Resolved — schools are real and authoritative.** Sai University has eight
schools, and the school is printed on the transcript itself
(`School of Computing and Data Science`), which makes it an official fact
rather than something the portal has to infer. The full list is in
[Reference: schools and degrees](#reference-schools-and-degrees) below.

The roster carries `department` and `batch`, nothing above them. Add a `school`
column to the roster CSV, optional in `import_roster_csv` so existing files
stay valid, and cross-check it against the transcript when one is uploaded
(R5). Where a student's roster school and transcript school disagree, the
transcript wins and the mismatch is flagged — same rule as CGPA.

Note that at Sai University the school *is* effectively the department for
most students: the transcript shows no level between "School of Computing and
Data Science" and the degree. The existing `department` field should therefore
hold the **programme** (`B.Tech Computer Science`), and `school` the school.

---

## R4 — Post-registration details form

**Requirement.** After a student registers and verifies their account, they
complete a form capturing their details before reaching the rest of the portal.

**What already exists.** `StudentProfile` is created lazily on first access and
starts empty. Registration currently ends at the dashboard with a 0% complete
profile and no prompt.

**Acceptance criteria.**

- [x] After verification, the student is taken to the form rather than the
      dashboard
- [x] The form collects, at minimum: phone, personal email (distinct from the
      college address), career path (R2), headline and summary, and the
      transcript upload (R5)
- [x] Roster-owned facts — name, PRN, department, batch — are shown read-only,
      so the student can see what the college holds and report an error
- [x] The form can be skipped and resumed; a partially complete form does not
      block access to the portal, but the student is prompted until it is done
- [x] Completing it is recorded (`onboarding_completed_at`) so the admin can see
      who has and has not
- [x] The admin dashboard shows how many students have completed onboarding
- [x] Re-registering or logging in later does not show the form again once
      completed

**Open questions.**

1. **Hard gate or prompt?** Blocking the portal until the form is done
   guarantees data; it also guarantees abandoned registrations. Recommend a
   prompt plus a persistent banner, not a hard gate.
2. **Which fields are mandatory?** Suggest phone and career path required,
   everything else optional. Needs confirming — every required field costs
   completion rate.
3. **Is a personal email wanted?** Useful after graduation, when the college
   address stops working. It is also personal data the PRD's privacy section
   does not currently cover.

---

## R5 — CGPA from the transcript, not the resume

**Requirement.** Take CGPA from an uploaded transcript rather than from a
resume.

**Why this matters.** A resume is a document the student writes. A transcript
is a document the college issues. Reading CGPA from a resume means trusting a
self-reported number that recruiters then filter on. This requirement closes
that gap, and it should be stated plainly: **CGPA is never taken from a
resume.**

**What already exists.** The matching engine extracts years of experience and
education level from resumes — and deliberately does *not* extract CGPA today.
Resume text extraction (`matching/extraction.py`) already handles PDF and DOCX
and can be reused as-is. The roster already carries a `cgpa` column uploaded by
the placement cell.

**Acceptance criteria.**

- [x] A separate transcript upload on the profile, distinct from the resume,
      with its own storage path
- [x] Transcript text is extracted and CGPA parsed out of it
- [x] The parsed CGPA is shown to the student for confirmation, the same
      review-and-correct pattern the resume pre-fill already uses — parsed
      value and confirmed value stored separately
- [x] The parsed CGPA is compared against the roster CGPA; a mismatch beyond a
      small tolerance is flagged for admin review rather than silently
      overwriting either value
- [x] **The roster CGPA remains authoritative for eligibility filters.** The
      transcript corroborates it; it does not replace it. A student cannot
      raise their own CGPA by uploading a document.
- [x] Admins can view the transcript alongside the resume (R1)
- [x] A resume never supplies the CGPA: no resume upload writes any CGPA
      field, and nothing in the profile flow pre-fills one from it. *(Reworded
      2026-10-20. Resume intelligence reads a resume's CGPA only as an
      admin-only verification flag, never as a value — DECISIONS D19. Pinned by
      `test_resume_upload_never_sets_a_cgpa_field`.)*
- [x] Transcripts are subject to the same visibility rules as resumes, or
      stricter — decide below

**Open questions.**

1. **Who can see a transcript?** A resume is written to be shared; a transcript
   is an official record. Recommend: student and placement cell only, never
   companies, even on a verified profile. Needs confirming.
2. **What does a mismatch mean?** If the transcript says 8.9 and the roster says
   8.7, which is right? Recommend flagging for the placement cell rather than
   the system choosing.
3. **Resolved — the format is known.** A sample transcript has been supplied
   and the layout is specified in
   [Reference: transcript format](#reference-transcript-format) below. It is a
   text-based PDF with a labelled `Cumulative GPA:` field, so extraction is a
   regex over `matching/extraction.py` output rather than a table-parsing
   problem. A manual-entry fallback is still required for scanned or
   non-standard documents.

---

## Reference: schools and degrees

Taken from [saiuniversity.edu.in](https://www.saiuniversity.edu.in) on
2026-09-24. These should seed the roster's `school` and `department`
(programme) values rather than being free text, so the dashboard in R3 groups
on a fixed set.

### Schools

| Key | Name |
| --- | --- |
| `arts_sciences` | School of Arts and Sciences |
| `computing_data_science` | School of Computing and Data Science |
| `law` | School of Law |
| `artificial_intelligence` | School of Artificial Intelligence |
| `media` | School of Media |
| `technology` | School of Technology |
| `business` | School of Business |
| `allied_health` | School of Allied Health Sciences |

### Programmes by school

**Arts and Sciences** — B.Sc. (Hons.) Neuroscience · B.Sc. (Hons.) Biological
Sciences · B.Sc. (Hons.) Psychology · B.A. (Hons.) Economics · B.A. (Hons.)
Politics, Philosophy and Economics (PPE) · Ph.D.

**Computing and Data Science** — B.Tech Computer Science · B.Tech Data Science ·
B.Tech Computer Science (AI) · B.Tech Computing and Data Science · B.Tech
Computer Science (Cyber Security) · B.Tech Computer Science (Full Stack) ·
B.Tech Computer Science (AI and ML) · B.Tech Computer Science (AI & Data
Science), jointly with L&T · B.Tech Computer Science, jointly with Xebia ·
MCA · Ph.D.

**Law** — B.A. LL.B. (Hons.) · BBA LL.B. (Hons.) · LL.M. in Regulation and
Governance · Daksha Fellowship · Ph.D.

**Artificial Intelligence** — B.Tech Artificial Intelligence · BCA (Hons.) ·
Ph.D. in Artificial Intelligence

**Media** — B.A. (Hons.) Media Studies · B.Sc. (Hons.) Visual Communication ·
B.Sc. (Hons.) Film and Television · Ph.D.

**Technology** — B.Tech Biotechnology · B.Tech Environmental Engineering ·
B.Tech Biomedical Engineering · Ph.D.

**Business** — BBA (Hons.) · BBA (Hons.) Business Intelligence & Data
Analytics · BBA (Hons.) Digital Marketing · B.Com. (Hons.) with ACCA · MBA ·
MBA Artificial Intelligence and Business Analytics · MBA Operations and
Project Management · Ph.D.

**Allied Health Sciences** — B.Sc. Operation Theatre & Anaesthesia Technology ·
B.Sc. Dialysis Technology · B.Sc. Physician Assistant · B.Sc. Medical
Laboratory Technology · B.Sc. Respiratory Technology · B.Sc. Emergency Medical
Technology · B.Sc. Critical Care Technology · B.Sc. Cardiovascular Technology ·
Bachelor of Optometry · Bachelor of Physiotherapy · Bachelor of Occupational
Therapy · Bachelor in Radiology · M.Sc. Clinical Embryology · Diploma in Art
Counselling

Three things to settle before this is hardcoded:

1. **The site and the transcript disagree on spelling.** The website writes
   `B.Tech`; the transcript prints `BTech`. Matching must normalise punctuation
   and case, exactly as `slugify_skill` already does for skills.
2. **The school pages list more specialisations than the homepage does** — the
   Computing and Data Science page carries Cyber Security, Full Stack, AI and
   ML, and two industry-joint programmes that the homepage omits. This list
   merges both; it should be confirmed against the registrar's own list rather
   than the marketing site.
3. **Postgraduate and doctoral students change the placement question.** An MBA
   or Ph.D. cohort has different outcomes from a B.Tech one. Confirm whether
   the portal covers them or only undergraduates.

## Reference: transcript format

Derived from the sample supplied 2026-09-24 (Sai University, issued
05-Jul-2026). Text-based PDF, so `matching/extraction.py` reads it as-is.

### Fields to extract

| Field | Line in the document | Example |
| --- | --- | --- |
| Issue date | `Transcript Issue Date: <DD-Mon-YY>` | `05-Jul-26` |
| Name | `Name: <NAME>` | `SAMPLE STUDENT` |
| **PRN** | `PRN: <digits>` on the same line as Name | `220200921` |
| School | its own line, starts `School of` | `School of Computing and Data Science` |
| Degree | first token of the totals line | `BTech` |
| Total credits | `Total Credits: <n>` | `106.0` |
| **Cumulative GPA** | `Cumulative GPA: <n>` | `8.42` |
| Per semester | `Academic Year <YYYY-YY> Semester <n>` then a course table, closing with `Semester Credits: <n> Semester GPA: <n>` | `Semester GPA: 8.08` |

`Cumulative GPA` is the CGPA the portal wants. **Note the label is
"Cumulative GPA", not "CGPA"** — a regex looking for `CGPA` finds it only in
the explanatory notes on the last page, not in the header.

### Grade scale, for verification

| Grade | Points | | Grade | Points |
| --- | --- | --- | --- | --- |
| O | 10 | | P | 4 |
| A+ | 9 | | F | 0 |
| A | 8 | | I | 0 (incomplete) |
| B+ | 7 | | AU | 0 (audit — **excluded** from GPA) |
| B | 6 | | AB | 0 (absent) |
| C | 5 | | W | 0 (withdrawn) |

CGPA is the credit-weighted average of semester GPAs; audit courses are
excluded from both. Percentage equivalent is GPA × 10.

Recomputing CGPA from the course table is therefore possible and worth doing as
a **cross-check on the printed figure** — if the two disagree, the document has
been altered or misread, and it should be flagged rather than trusted.

### Parsing notes

- The PRN on the transcript (`220200921`, nine digits) does **not** match the
  format in the current demo fixtures (`PRN2022CS001`). The roster's
  `PRN_VALIDATOR` already accepts both, but the seed data should be regenerated
  to the real format before anyone demos this.
- The extracted PRN must be checked against the signed-in student's own PRN.
  Without that, a student can upload somebody else's transcript. **Confirmed
  2026-09-30:** PRN is issued once, never reused, and is the identifier on the
  transcript and other college documents — so this check is the binding between
  student and document, not merely a sanity test. A mismatch is refused and
  logged, never stored.
- Semester tables split across pages, with a `(contd.)` heading on the
  continuation. A parser that assumes one table per semester will drop rows.
- The page carries a heavy repeating watermark. It did not corrupt extraction
  in this sample, but it is a reason to test against the real file rather than
  a synthetic one.
- **Test fixtures must be synthetic.** The sample supplied is a real student's
  academic record; it should be used to validate the parser during development
  and must not be committed to the repository.

## Data model impact

| Model | Change |
| --- | --- |
| `roster.Student` | `school` (optional, from the CSV, one of the eight above); `department` now holds the **programme** name |
| `profiles.StudentProfile` | `career_path`, `career_path_detail`, `also_attending_placements` (R2); `onboarding_completed_at`, `personal_email` (R4); `transcript`, `transcript_text`, `parsed_cgpa`, `confirmed_cgpa`, `transcript_prn`, `transcript_school`, `cgpa_matches_roster` (R5) |
| `roster.Student` CSV importer | accept `school` as an optional column, keeping existing files valid |
| `core.AuditLog` | new actions: transcript parsed, CGPA mismatch flagged, PRN mismatch on transcript, resume viewed (R1) |
| `core.storage` | `transcript_upload_path`, and `validate_transcript` accepting PDF only |
| fixtures | regenerate `roster_sample.csv` with real-format PRNs (nine digits), the eight schools, and real programme names |

No changes to the matching engine's public boundary. Transcript parsing should
be a new extractor in `matching/`, reusing `extraction.py`, and must not be
wired into resume parsing.

---

## Where this fits

These requirements sit **between the current state and Phase 4** of
[`agents.md`](agents.md). Phases 0–3 are complete and the halfway checkpoint has
passed; the Opportunities Board has not been started.

Suggested order, cheapest and least blocked first:

1. **R1** — admin profile and resume view. The API exists; this is UI only.
2. **R2** — career path field. Small, self-contained, and R3 depends on it.
3. **R4** — onboarding form. Needs R2 to be worth filling in.
4. **R3** — outcomes dashboard. Blocked on the "school" decision and on R2
   having data to count.
5. **R5** — transcript CGPA. Largest, but no longer uncertain: the format is
   specified and the extraction is a regex over text the existing pipeline
   already produces.

R1, R2, R4 and R5 can all begin now. R3 is the only one still waiting on a
decision — whether the dashboard covers postgraduate cohorts, and a programme
list confirmed by the registrar rather than the website.

---

## Decisions needed before work starts

### Answered

| # | Question | Answer |
| --- | --- | --- |
| 1 | Does the college have schools above departments? | **Yes** — eight, printed on the transcript. Listed above |
| 3a | Are Business, Entrepreneurship and Family business distinct? | **Yes, all three stay** *(confirmed 2026-09-24)* |
| 8 | Sample transcript in the real format? | **Supplied** — format specified above |

### Still open

| # | Question | Blocks |
| --- | --- | --- |
| 2 | Is career path single-select, or can a student pick several? | R2, R3 |
| 3b | Are `placement` and `undecided` valid career-path options too? | R2, R3 |
| 4 | Can companies see a student's career path? *(recommended: no)* | R2 |
| 5 | Is the onboarding form a hard gate or a prompt? *(recommended: prompt)* | R4 |
| 6 | Can companies see a transcript? *(recommended: no)* | R5 |
| 7 | On a CGPA mismatch, which value wins? *(recommended: neither — flag it)* | R5 |
| 9 | Does the portal cover MBA / M.Sc. / Ph.D. cohorts, or undergraduates only? | R3 |
| 10 | Confirm the programme list against the registrar, not the marketing site | R3 |
