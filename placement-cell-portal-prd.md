# Placement Cell Portal — PRD

2026-09-17 · @Someone

## Overview & Problem Statement

Today, placement activity at the college runs on scattered spreadsheets, WhatsApp groups, and email threads. Students have no single place to showcase their internships, projects, and skills to visiting companies, and the placement cell has no structured way to match student profiles against incoming job postings or to tell students which certifications would improve their shortlisting odds.

The Placement Cell Portal is a web platform where students log in with their PRN and college email, build a profile of their experience and projects, and see certifications and opportunities suggested specifically to them. Companies get a filterable, standardized view of student profiles instead of static resume PDFs.

## Goals & Success Metrics

- Give every student a single verified profile of experience and projects that companies can browse and filter
- Raise certification completion among students by surfacing relevant certifications tied to each student's gaps
- Increase the number of students who apply to at least one posted opportunity
- Cut the placement cell's manual matching and shortlisting time

| Metric | Target |
| --- | --- |
| Student profile completion rate | 80% of eligible students within first semester of rollout |
| Certification click-through / start rate | 40% of suggested certifications viewed |
| Opportunities applied to per active student | 3+ per placement season |
| Placement cell manual shortlisting time | Reduced by 50% |

## User Roles & Personas

| Role | Who | Key needs |
| --- | --- | --- |
| Student | Any enrolled student, identified by PRN | Log in easily, build a profile once and keep it current, know what to learn next, see opportunities worth applying to |
| Placement Cell Admin | College placement staff | Verify student profiles, upload opportunities, curate the certification catalog, track applications and shortlists |
| Company / Recruiter | Visiting company representative | Browse and filter student profiles by skills, projects, experience, and academic year; post openings; shortlist candidates |
| Faculty Coordinator (optional, later phase) | Department placement coordinator | View department-level placement readiness and student progress |

## Core Feature: Authentication

Students log in with their PRN (Permanent Registration Number) plus their college-issued email address, so identity is anchored to a record the college already controls rather than a self-declared name.

- On first login, the student enters PRN + college email; the system checks both against the student master list uploaded by the placement cell (from the existing student database or an admin-uploaded roster)
- A one-time password or verification link is sent to the college email to confirm ownership before the account activates
- Password/OTP-based login for subsequent sessions; PRN acts as the unique student identifier across the system
- Company and admin accounts are created separately by the placement cell, with email + password login and no PRN
- Failed match against the roster (wrong PRN/email pair) blocks account creation and flags it for admin review

Open question: should this reuse the login/auth service from the existing student management portal (Django + DRF) rather than build a separate one, so a student has one identity across both systems?

## Core Feature: Student Profile (Experience & Projects)

This is the student-facing equivalent of a resume, but structured so companies can filter and compare across students.

- Basic details: name, PRN, department, batch/year, CGPA, contact info (pulled from roster, editable within limits)
- Experience entries: internships, part-time work, volunteering — role, organization, duration, description, skills used
- Project entries: title, description, tech stack/tools, role, links (GitHub, live demo, video), team size
- Skills list, tagged by category (technical, soft skills, tools)
- Resume upload (PDF or DOCX): text is auto-extracted and parsed to pre-fill years of experience and education level (UG/Masters/PG), which the student reviews and corrects before saving
- Profile visibility toggle: student controls whether their profile is visible to all companies, only shortlisted ones, or hidden
- Admin verification badge on profiles the placement cell has checked, so companies can trust the data
- Company-facing view: searchable/filterable by department, skills, CGPA range, project keywords, certifications held

## Core Feature: Resume Parsing & Semantic Matching Engine

Ported from an existing resume-matcher prototype (Flask + spaCy) into a shared backend service both the Student Profile and Opportunities Board draw on.

- Text extraction: pulls plain text out of uploaded PDF and DOCX resumes
- Hard-fact extraction: regex-based detection of total years/months of experience and education level (UG, Masters, PG/Doctorate) from resume text, used to pre-fill profile fields and to power eligibility filters
- Semantic similarity: an NLP model compares a resume's or a student profile's full text against an opportunity's job description and produces a similarity score, rather than relying on keyword or skill-tag overlap alone
- Adjustable similarity threshold: admins and companies can raise or lower the bar for what counts as a match when screening a batch of applicants for a specific opportunity
- Optional hard filters on top of the similarity score: minimum years of experience, required education level, applicants failing these are excluded before ranking
- Bulk screening workflow for admin or company use: upload or select a pool of resumes against one job description, get back a ranked, scored shortlist with each candidate's extracted experience and education shown beside the match score
- This engine backs the Opportunities Board's relevance ranking below, and can also run ad hoc for one-off hiring drives

## Core Feature: Certification Suggestions

The system recommends certifications based on gaps between a student's current profile (skills, department, project stack) and what's in demand — either from active opportunity postings or a curated skill-to-certification map.

- Certification catalog: admin-maintained list of certifications (name, provider, skill tags, level, link)
- Matching logic (v1, rule-based): compare a student's tagged skills against skill tags on open opportunities and the catalog; recommend certifications covering the largest gaps, weighted toward skills that appear most often in current postings
- Each suggestion shows why it's suggested (e.g. "3 open opportunities in your department ask for AWS")
- Students can mark a certification as in-progress or completed, with proof upload (certificate PDF/link) for admin verification
- Completed, verified certifications automatically show up on the student's company-facing profile
- v2 (later phase): move matching to a lightweight recommendation model once enough application/hiring outcome data exists

## Core Feature: Opportunities Board

Placement cell admins (or invited companies) upload job/internship openings; students see a personalized, ranked feed rather than one flat list.

- Opportunity fields: title, company, role type (internship/full-time), required skills, eligible departments/CGPA cutoff, deadline, description
- Admin (and later company) can create/edit/close opportunities
- Matching score: skills overlap + department + CGPA eligibility + certifications held, blended with the semantic similarity score from the Resume Parsing & Matching Engine, into a relevance rank and an eligible/not-eligible flag
- Student feed shows ranked opportunities, independently filterable/searchable
- In-app apply using profile + resume; application status states (applied → shortlisted → interview → offer/rejected)
- Admin dashboard: applicants per opportunity, exportable shortlist, aggregate stats
- Bulk screening for a single opportunity: admin/company runs the matching engine's ranked-shortlist workflow directly against that opportunity's applicant pool, with the similarity threshold and hard filters (experience, education) set per opportunity
- Notifications (email/in-app) when a new opportunity matches a student's profile or a deadline is near

## Non-Functional Requirements

- Scale: support the full student body at rollout, with headroom to grow alongside the college's broader student systems
- Data privacy: student CGPA, contact details, and resumes are visible only to the student, verified admins, and companies the student has opted to share with; no public/anonymous access to raw profile data
- Data integrity: PRN + email pairs validated against the official student roster on signup to prevent fake or duplicate accounts
- Auditability: admin actions (verifying a profile, uploading an opportunity, editing a certification) are logged
- Availability: uptime matters most during active placement drives (peak application/interview windows)
- Accessibility: usable on mobile browsers, since many students will apply from phones
- Single sign-on potential: architecture should not block a future shared login with other college systems (e.g. the student management portal)

## Tech Stack & Architecture

Proposed to mirror the stack already chosen for the college's student management portal, so both can eventually share auth and student data instead of duplicating it:

- Backend: Django + Django REST Framework — student profile, opportunity, and certification models as separate Django apps
- Frontend: React (TypeScript) — student portal, company-facing browse/filter view, and admin dashboard as separate views within one app or as a shared component library
- Database: PostgreSQL, with the student roster (PRN, email, department, batch) as the source of truth other modules read from
- File storage: object storage (e.g. S3-compatible) for resumes and certification proof uploads
- Auth: JWT or session-based auth on top of Django, with the roster-matching step described in Authentication
- Resume parsing & matching: PyPDF2 and python-docx for text extraction, regex-based extractors for experience/education, spaCy (en\_core\_web\_md) for semantic similarity — packaged as a standalone Django app/service so both the profile upload flow and the opportunities matching flow call the same engine, ported from the existing resume-matcher prototype
- Architecture reference: same shared auth/API/infrastructure pattern as IIT Bombay DevCom's open-source ecosystem (InstiApp, ResoBin, UniPortal), so this can plug in as another module alongside the student management portal rather than a standalone silo

## Roadmap / Phasing

| Phase | Scope |
| --- | --- |
| Phase 1 | PRN + email login, student roster upload/matching, core student profile (experience + projects), admin dashboard to verify profiles |
| Phase 2 | Resume Parsing & Semantic Matching Engine (text extraction, experience/education extraction, spaCy similarity) — wired into profile upload first |
| Phase 3 | Opportunities board with admin-uploaded postings, in-app apply, application status tracking, matching engine wired in for ranking and bulk screening |
| Phase 4 | Certification catalog + rule-based suggestion matching, proof upload and verification |
| Phase 5 | Company self-service portal (post openings, browse/filter profiles directly), notifications, analytics dashboard |
| Phase 6 | Smarter matching (recommendation model for certifications and opportunities, replacing/augmenting the rule-based and similarity-threshold approach) once enough usage data exists; shared SSO with the student management portal |
