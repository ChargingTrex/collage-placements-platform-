# AGENTS.md — Placement Cell Portal Build Plan

This file governs how a coding agent (Claude Code or similar) builds the Placement Cell Portal described in the PRD. Follow phases in order. Do not start a phase until the previous phase's checkpoint has passed. Do not skip a smoke test to save time — a failed smoke test blocks moving on.

## Reference
- Product spec: Placement Cell Portal PRD (login by PRN + college email; student experience/projects profile shown to companies; certification suggestions; opportunities board matched to student experience; a Resume Parsing & Semantic Matching Engine ported from an existing resume-matcher prototype)
- Stack: Django + DRF (backend), React + TypeScript (frontend), PostgreSQL, object storage for uploads, spaCy + PyPDF2 + python-docx for the matching engine
- Architecture reference: shared auth/API pattern, modeled on IIT Bombay DevCom's ecosystem (InstiApp/ResoBin/UniPortal style), so this can later share identity with the existing student management portal

## Ground rules for the agent
- Work phase by phase. Announce which phase/task you're starting before touching code.
- Every task ends with the task's own unit/integration tests passing locally before moving to the next task.
- Commit at the end of each completed task with a message naming the phase and task (e.g. `phase-1: PRN+email roster matching`).
- Never mark a checkpoint or smoke test "done" without actually running it and showing the output.
- If a smoke test fails, fix it before proceeding — do not move to the next phase with a known-broken smoke test.
- Keep a running `PROGRESS.md` (or update this file's checkboxes) so a new agent session can resume without re-reading all prior chat.

---

## Phase 0 — Scaffold & Environment
**Scope:** repo structure, Django project + apps, React app, database, CI skeleton, no real features yet.

Checklist:
- [ ] Django project created with apps: `roster`, `profiles`, `matching`, `opportunities`, `certifications`
- [ ] PostgreSQL configured locally and in CI; migrations run cleanly from empty DB
- [ ] React + TypeScript app scaffolded, talks to a `/api/health` endpoint
- [ ] Object storage config stubbed (local filesystem for dev, S3-compatible interface)
- [ ] Environment variables documented in `.env.example`
- [ ] CI runs backend + frontend test suites on push

**Checkpoint:** `docker-compose up` (or equivalent) brings up backend + frontend + DB from a clean clone with no manual steps beyond `.env` setup.

**Smoke test:**
1. Fresh clone, fresh `.env`, run the standard bring-up command
2. Hit `/api/health` → 200 OK
3. Load the frontend root page → renders without console errors

---

## Phase 1 — Roster & Authentication
**Scope:** PRN + college email login, roster upload/matching, OTP/email verification.

Checklist:
- [ ] `Student` roster model: PRN, college email, department, batch, CGPA
- [ ] Admin roster upload (CSV) with row-level validation errors reported back
- [ ] Signup flow: PRN + email submitted → matched against roster → OTP/verification link sent
- [ ] Login flow (post-verification): OTP or password, PRN as unique identifier
- [ ] Mismatched PRN/email pair → account creation blocked, flagged for admin review
- [ ] Company and admin account types created separately (email + password, no PRN)
- [ ] Rate limiting / basic abuse protection on OTP requests

**Checkpoint:** a seeded roster of test students can each sign up, verify, and log in; a non-roster PRN/email pair is correctly rejected and flagged.

**Smoke test:**
1. Upload a test roster CSV (5 students)
2. Sign up as one roster student with correct PRN+email → OTP sent → verify → login succeeds
3. Attempt signup with a PRN/email pair not on the roster → rejected, appears in admin's flagged list
4. Log in as a seeded admin account → reaches admin dashboard shell

---

## Phase 2 — Resume Parsing & Semantic Matching Engine
**Scope:** the shared backend service (ported from the existing Flask/spaCy resume-matcher prototype) that both Student Profile and Opportunities Board will call later. Build and test it standalone before wiring it into any UI.

Checklist:
- [ ] Text extraction utilities for PDF (PyPDF2) and DOCX (python-docx) resumes
- [ ] Regex-based extractor for total years/months of experience from free text
- [ ] Regex-based extractor for education level (UG, Masters, PG/Doctorate) from free text
- [ ] spaCy model (`en_core_web_md`) loaded as a service; semantic similarity function between two texts (resume vs. job description)
- [ ] Configurable similarity threshold parameter (not hardcoded)
- [ ] Hard-filter support: minimum experience years, required education level(s), applied before ranking
- [ ] Bulk-scoring function: given a pool of resumes and one job description, returns a ranked, scored list with each candidate's extracted experience/education attached
- [ ] Packaged as an internal Django app/service with a clean function/API boundary — no UI yet

**Checkpoint:** given a fixed set of sample resumes (PDF + DOCX) and a sample job description, the engine returns a ranked list with scores, extracted experience, and extracted education that match expected values from a hand-checked reference set.

**Smoke test:**
1. Feed 5 sample resumes (mix of PDF/DOCX, known experience/education content) + 1 job description into the engine
2. Verify extracted experience and education match the hand-checked reference for each resume
3. Verify similarity scores rank the two most relevant resumes above the three least relevant ones
4. Apply a hard filter (e.g. minimum 2 years experience) → confirm resumes below the cutoff are excluded from the ranked output regardless of similarity score
5. Change the similarity threshold → confirm the pass/fail count changes as expected

---

## Phase 3 — Student Profile
**Scope:** experience, projects, skills, resume upload (using the Phase 2 engine to pre-fill fields), visibility controls, admin verification.

Checklist:
- [ ] Profile model: experience entries, project entries (with tech stack, links), skills, resume upload
- [ ] Student can create/edit/delete their own experience and project entries
- [ ] Resume upload triggers the Phase 2 engine: extracted years of experience and education level pre-fill profile fields for the student to review and correct
- [ ] Visibility toggle (all companies / shortlisted only / hidden) enforced server-side, not just UI-hidden
- [ ] Admin can view and mark a profile "verified"; verified badge shows on the profile
- [ ] Company-facing read view: filter by department, skills, CGPA range, project keywords
- [ ] Authorization: a student can only edit their own profile; companies can only see profiles per the visibility rule

**Checkpoint:** a test student's completed profile is correctly hidden/shown to a test company account per the visibility setting, and a resume upload correctly pre-fills experience/education for the student to confirm.

**Smoke test:**
1. Log in as the seeded student, add 2 experience entries and 2 projects, upload a resume
2. Confirm experience/education fields are pre-filled from the resume and editable
3. Set visibility to "hidden" → log in as a company account → profile does not appear in search
4. Set visibility to "all companies" → same company search now finds the profile with correct data
5. Admin marks the profile verified → verified badge appears on the company-facing view

---

## HALFWAY CHECKPOINT — Full E2E Test (after Phase 3)
Run this before starting Phase 4. This is a comprehensive pass, not a smoke test — cover the full roster→login→profile→matching-engine lifecycle end to end.

- [ ] Fresh environment, fresh DB, roster of 10+ synthetic students uploaded
- [ ] All 10 students sign up, verify, and log in successfully; 2 deliberately-invalid PRN/email pairs are correctly rejected
- [ ] Each student builds a full profile (experience, projects, skills, resume); admin verifies at least half of them
- [ ] Resume-derived experience/education extraction spot-checked against hand-verified values for at least 5 of the 10 students
- [ ] 2 company accounts search/filter profiles by department, skill, and CGPA range; visibility rules hold for hidden/shortlisted/all-companies cases across all 10 students
- [ ] Edit and delete flows on experience/project entries checked for both success and failure (e.g. editing another student's entry is rejected)
- [ ] Load check: search/filter response time and matching-engine scoring time acceptable with the seeded roster size
- [ ] No console errors, no unhandled 500s in backend logs across the full run
- [ ] Record results (pass/fail per item) before proceeding to Phase 4

---

## Phase 4 — Opportunities Board
**Scope:** opportunity postings, relevance ranking (skills/eligibility blended with the Phase 2 engine's similarity score), in-app apply, application status tracking, bulk screening.

Checklist:
- [ ] Opportunity model: title, company, role type, required skills, eligibility (department/CGPA), deadline, description
- [ ] Admin (and later company) can create/edit/close opportunities
- [ ] Matching score: skills overlap + department + CGPA eligibility + certifications held, blended with the Phase 2 engine's semantic similarity score → relevance rank + eligible/not-eligible flag
- [ ] Student feed shows ranked opportunities, independently filterable/searchable
- [ ] In-app apply using profile + resume; application status states (applied → shortlisted → interview → offer/rejected)
- [ ] Admin dashboard: applicants per opportunity, exportable shortlist, aggregate stats
- [ ] Bulk screening: admin/company runs the Phase 2 engine's ranked-shortlist workflow against one opportunity's applicant pool, with per-opportunity similarity threshold and hard filters (experience, education)
- [ ] Notifications on new matching opportunity or approaching deadline

**Checkpoint:** a seeded opportunity correctly ranks higher for students whose skills and resume text match it, and the full apply → status change → bulk-screen flow works.

**Smoke test:**
1. Admin creates an opportunity requiring specific skills/department and a job description
2. Two students, one matching and one not, view the feed → matching student sees it ranked higher and marked eligible
3. Matching student applies in-app → status shows "applied"
4. Admin runs bulk screening against all applicants with a chosen similarity threshold and a minimum-experience filter → ranked shortlist returned, non-matching applicant correctly excluded
5. Admin moves an application to "shortlisted" → student sees updated status
6. Admin exports the shortlist → file contains the applicant

---

## Phase 5 — Certification Suggestions
**Scope:** certification catalog, gap-based matching, proof upload/verification, profile reflection.

Checklist:
- [ ] Certification catalog model: name, provider, skill tags, level, link (admin-managed)
- [ ] Rule-based matching: compare student's skill tags against open-opportunity skill tags + catalog → ranked suggestions with a stated reason
- [ ] Student can mark a certification in-progress/completed with proof upload
- [ ] Admin verifies certification proof; verified completions appear on the company-facing profile
- [ ] Suggestion list updates as the student's skills or open opportunities change

**Checkpoint:** a student missing a skill common across open opportunities is suggested the right certification with a correct reason string, and a verified completion shows on their profile.

**Smoke test:**
1. Create 3 open opportunities all requiring a skill the test student lacks
2. Load the student's certification suggestions → the matching certification appears with a reason referencing that skill
3. Student marks it in-progress → completed, uploads proof
4. Admin verifies → certification now appears on the student's company-facing profile

---

## Phase 6 — Company Self-Service & Notifications
**Scope:** company accounts can post/manage their own openings directly, including running bulk screening themselves; notification and analytics polish.

Checklist:
- [ ] Company account can create/edit/close its own opportunities without admin mediation
- [ ] Company account can browse/filter/shortlist profiles directly, respecting visibility rules
- [ ] Company account can run the Phase 2 engine's bulk screening workflow on its own opportunities
- [ ] Notification delivery (email/in-app) verified for: new matching opportunity, approaching deadline, application status change
- [ ] Basic analytics dashboard: applications per opportunity, profile completion rate, certification completion rate (ties back to PRD success metrics)

**Checkpoint:** a company account, unaided by admin, posts an opportunity, runs bulk screening, and shortlists a matching student; that student receives a notification.

**Smoke test:**
1. Company logs in, creates an opportunity with a job description, sees matching student profiles
2. Company runs bulk screening on its applicant pool and shortlists a matching student → student receives a notification and sees updated status
3. Analytics dashboard reflects the new opportunity and application counts

---

## FINAL CHECKPOINT — Full Comprehensive E2E Test (after Phase 6)
Run this as the release gate. Cover every role and the full lifecycle, not just individual features.

- [ ] Fresh environment, fresh DB, realistic-scale seeded roster
- [ ] Full student lifecycle: signup → verify → login → build profile (with resume-derived pre-fill) → get certification suggestions → complete a certification → apply to opportunities → track application through every status
- [ ] Full company lifecycle: account setup → post opportunity → search/filter profiles → run bulk screening with custom threshold/filters → shortlist → move applications through statuses → view analytics
- [ ] Full admin lifecycle: upload roster → verify profiles → verify certifications → manage catalog → run bulk screening → export shortlists → view aggregate analytics
- [ ] Matching engine accuracy: extracted experience/education and similarity rankings spot-checked against a hand-verified reference set across a larger, more varied resume sample
- [ ] Cross-role checks: visibility rules hold under every combination (hidden/shortlisted-only/all-companies × verified/unverified profile); rejected/invalid roster entries never produce a working login
- [ ] Notifications fire correctly for every trigger defined in Phase 6
- [ ] Security pass: a student cannot read/edit another student's profile or application; a company cannot see profiles outside its visibility scope; unauthenticated requests to protected endpoints are rejected
- [ ] Performance check under realistic-scale data (search/filter/apply/bulk-screening latency acceptable)
- [ ] No console errors, no unhandled server errors across the entire run
- [ ] Metrics instrumented match the PRD's Goals & Success Metrics section (profile completion rate, certification start rate, applications per student, admin shortlisting time)
- [ ] Sign-off: record pass/fail per section above; do not ship with an unresolved fail
