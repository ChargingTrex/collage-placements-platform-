# Opportunities, applications, suggestions, exports — API contract

The shapes for **Phase B** (`agents.md` Phase 4) and **Addendum 2 stages 2–4**
(plan: `~/.claude/plans/addendem-2-1-add-a-sharded-quokka.md`). Tests in
`backend/checkpoints/test_checkpoint_b.py` assert exactly this. If a shape has
to change, change it here first, then the tests, then the code.

Decisions behind it: DECISIONS **D26** (notifications), **D27** (what
"shortlist" means), **D28** (apply and eligibility rules).

## Ground rules (inherited, binding)

- **UUID in every path**, and PRN only as a filter or column. Every list declares `?prn=` and `?prns=`, and
  reports `unmatched_prns` (`core.filters` mixins). **An unknown query parameter is a 400.**
- **Every opportunity belongs to a `Company`, never to a recruiter `User`.** A recruiter acts for
  `request.user.company`. A recruiter with no company gets **403** on every
  company action.
- **Authorisation lives in querysets and permission classes**, never in the UI. An object
  outside the caller's scope is a **404**, not a 403.
- **Weights and thresholds come from settings** (`MATCH_SCORE`, `SUGGESTIONS`,
  `OPPORTUNITIES`), never from literals.
- **Everything works with `LLM_ENABLED=false`**, using regex and TF-IDF.
- **The CGPA is the roster's `Student.cgpa` only**, for eligibility and for
  `cgpa_at_apply`. Never `confirmed_cgpa` or a transcript value.
- **Company payloads are allow-lists.** They never contain marksheets,
  `confirmed_cgpa`, `parsed_cgpa`, `recomputed_cgpa`, `career_path*`,
  `transcript*`, `personal_email`, `also_attending_placements` or the full
  `completion_percent`. **Contact details (email, phone) appear only when the
  profile `is_verified`.** Otherwise they are `null`, and `contact_available` is `false`.
- **Documents leave only through audited API views** (D25). No `/media/` URLs.

## Models

### `opportunities.Opportunity`
| Field | Notes |
| --- | --- |
| `id` | UUID |
| `company` | FK `accounts.Company`, required |
| `title`, `description` | the description is the JD that the engine scores against |
| `role_type` | `internship` · `full_time` |
| `location` | string, may be blank |
| `openings` | positive int, default 1 |
| `required_skills` | list of strings, stored slugged (`profiles.models.slugify_skill`) |
| `eligible_departments` | list of programme names (`roster.reference`). **Empty means all** |
| `min_cgpa` | decimal 0–10 or null |
| `min_experience_years` | decimal or null. A **screening** filter, not an apply block |
| `required_education_levels` | list of `UG` · `Masters` · `PG`. A **screening** filter |
| `salary_disclosed` | bool. When false, the salary fields are null |
| `salary_min`, `salary_max` | int or null, with `salary_max >= salary_min` |
| `salary_period` | `month` · `year` |
| `salary_currency` | default `INR` |
| `deadline` | date, required |
| `similarity_threshold` | 0–100 or null. Null means `settings.SUGGESTIONS["MIN_SCORE"]` |
| `status` | `draft` → `pending_review` → `open` → `closed`, and `rejected` |
| `submitted_at`, `approved_by`, `approved_at`, `rejection_reason`, `created_by` | |

`Opportunity.objects.visible_to(user)`:
- An **admin** sees every opportunity.
- A **recruiter** sees all of their company's, in any status.
- A **student** sees `open` ones only.

Students can still read the opportunity behind each of their own applications
through the application payload.

### `opportunities.Application`
| Field | Notes |
| --- | --- |
| `id` | UUID |
| `opportunity`, `profile` | FKs. Unique together |
| `status` | `applied` → `shortlisted` → `interview` → `offer`, and `rejected`. `withdrawn` is set by the student |
| `department`, `programme`, `school`, `batch`, `year_of_study`, `cgpa_at_apply` | **Frozen at apply time** from the roster. A later programme change never rewrites them |
| `full_name`, `prn` | also frozen, for exports |
| `resume_snapshot`, `resume_snapshot_filename` | a **copy** of the resume at apply time |
| `score` | int 0–100, the calibrated match score at apply time |
| `similarity` | float, the raw semantic part |
| `eligible`, `eligibility_reasons` | the result of the eligibility check (always `true` at apply, because ineligible students are refused) |

Applications are **never deleted**.

### `opportunities.ApplicationEvent`
Records `application`, `actor`, `from_status`, `to_status`, `note` and `created_at`.
An event is written on create (`""` → `applied`), on every status change, and on withdraw.

### `notifications.Notification` (D26: a minimal slice)
Records a UUID, `recipient` (FK User), `kind` (`new_opportunity` · `deadline_soon`),
`opportunity` (FK), `created_at` and `read_at`. It is **unique on
(`recipient`, `kind`, `opportunity`)**, which is what makes both triggers idempotent.
In-app only: email, status-change notifications and the 422 channel rule are Phase D.

## Shortlist semantics (D27)

A `CompanyShortlist` row grants a company visibility of a "shortlisted only"
profile. It now carries `source`:

| Event | Effect on the row |
| --- | --- |
| A student applies | `get_or_create(source="application")`. An existing `manual` row is left as is |
| A student withdraws | The row is deleted **only if** `source == "application"` and the student has no other non-withdrawn application to that company |
| A recruiter shortlists (`POST students/<id>/shortlist`) | `update_or_create(source="manual")`. An application row is upgraded |
| A recruiter un-shortlists (`DELETE`) | If the student has a non-withdrawn application to that company, the row becomes `source="application"`, because the applicant stays visible. Otherwise the row is deleted |

**"The company's shortlist"** is what the Shortlist page, `?shortlisted=true`
and both Stage 4 exports read. It is defined as:

> profiles `visible_to(company)` **∩** (manual rows **∪** profiles with an application to one of the company's opportunities at status `shortlisted`, `interview` or `offer`)

An application row alone is **not** a pick. `is_shortlisted` on the company profile
payload follows this same definition.

**Hidden students may apply (D28).** The owning company sees that student's
**application** (snapshot plus resume snapshot) through the applications endpoints.
It does **not** see the profile through browse, search or the Stage 4 exports, because
those follow `visible_to`, which excludes hidden profiles.

## Endpoints — Stage 2 (Phase B)

All of these are under `/api/opportunities/`. An anonymous caller gets 401.

| Method + path | URL name | Who | Notes |
| --- | --- | --- | --- |
| `GET` `` (list) | `opportunity-list` | all, scoped by `visible_to` | filters `?status= ?role_type= ?company_id= ?search=` |
| `POST` `` | `opportunity-list` | recruiter, admin | recruiter: created as `draft` for their company. **Admin: must send `company` (UUID) and is created `open`**, with `approved_by` = admin (D28) |
| `GET/PATCH` `<id>` | `opportunity-detail` | owner company, admin | a recruiter may PATCH only in `draft` or `rejected`; an admin, any status but `closed` |
| `DELETE` `<id>` | `opportunity-detail` | owner company, admin | `draft` only, otherwise 400 |
| `POST` `<id>/submit` | `opportunity-submit` | owner recruiter | `draft`/`rejected` → `pending_review` |
| `POST` `<id>/approve` | `opportunity-approve` | admin | `pending_review` → `open`. Records the JD for role categories (`record_job_description`, which is `None` with the LLM off) and fires **notification trigger 1** |
| `POST` `<id>/reject` | `opportunity-reject` | admin | body `{"reason": "…"}`, which is required. Moves to `rejected` |
| `POST` `<id>/close` | `opportunity-close` | owner company, admin | `open` → `closed` |
| `GET` `feed` | `opportunity-feed` | student | `open` postings, deadline today or later, ordered by `score` desc. Each row is the opportunity plus `score`, `components`, `matched_skills`, `missing_skills`, `eligible`, `eligibility_reasons`, `has_applied` and `application_status` |
| `POST` `<id>/apply` | `opportunity-apply` | student | **201** with the application payload. **400** `{"detail", "reason"}`, where `reason` is one of `not_open` · `deadline_passed` · `already_applied` · `no_resume` · `not_eligible`. A `draft`, `pending_review` or `rejected` posting is not visible to a student, so applying to it is a **404**; a `closed` one is `not_open` |
| `GET` `<id>/applicants/export` | `opportunity-applicants-export` | owner company, admin | `text/csv`. **PRN is the first column.** Columns: `prn,full_name,department,programme,school,batch,cgpa_at_apply,status,score,applied_at,email,phone,contact_available`. Sorted by score desc, then PRN. Audited as `applications_exported` |
| `POST` `<id>/screen` | `opportunity-screen` | owner company, admin | body `{"threshold"?, "min_experience_years"?, "required_education_levels"?}`. The request value wins over the posting's, which wins over settings. Runs `engine.screen` over the applicants' **resume snapshots**. Returns `{"shortlisted": [...], "below_threshold": [...], "filtered_out": [...]}`, each row `{application_id, prn, full_name, score, experience_years, education_levels, reasons}`. `score` is the snapshot's **calibrated similarity (0-100)**, the same number the `threshold` cut is made on, so a shortlisted row never shows a score under the cut; it can differ from the application's full match score. `MatchingThrottle` |
| `GET` `stats` | `opportunity-stats` | admin | `{"opportunities_by_status": {...}, "applications_by_status": {...}, "per_opportunity": [{"id", "title", "company", "applicants", "by_status": {...}}], "median_hours_to_shortlist": float or null}` |

| Method + path | URL name | Who | Notes |
| --- | --- | --- | --- |
| `GET` `applications` | `application-list` | admin: all · recruiter: their company's · student: their own | filters `?opportunity= ?status= ?prn= ?prns=` |
| `GET` `applications/<id>` | `application-detail` | as above | |
| `POST` `applications/<id>/withdraw` | `application-withdraw` | the student who applied | from `applied`, `shortlisted` or `interview` → `withdrawn`. 400 from a final status |
| `POST` `applications/<id>/status` | `application-status` | owner company, admin | body `{"status", "note"?}`. Allowed transitions: `applied`→`shortlisted`/`rejected`, `shortlisted`→`interview`/`rejected`, `interview`→`offer`/`rejected`. Anything else is 400. Writes an `ApplicationEvent` and an audit row |
| `GET` `applications/<id>/resume` | `application-resume` | owner company, admin, the student | the **snapshot** file. Company and admin opens are audited as `document_accessed` |

**Company application payload:**
- `id`, `status`, `applied_at`, `score`, `similarity`, `eligible`,
  `eligibility_reasons`, `opportunity` (`{id, title}`);
- the frozen facts: `prn`, `full_name`, `department`, `programme`, `school`,
  `batch`, `year_of_study`, `cgpa_at_apply`;
- `skills` (names);
- `resume_url` (the API route above);
- `contact` (`{email, phone}`, or `null` when the profile is unverified) and `contact_available`.

**Nothing else.** The student's own payload adds `events`, and the admin's adds
`profile_student_id`.

### Eligibility (D28)

`eligible` is true when both of these hold:
- the roster `department` is in `eligible_departments` (an empty list means all);
- the roster `cgpa >= min_cgpa`. A null `min_cgpa` passes; a null roster CGPA fails a non-null cutoff.

`eligibility_reasons` names each failure in plain words.

- **Department and CGPA failures block applying** (`not_eligible`). These are registrar facts.
- **Experience and education are screening filters only.** They appear in the
  score's `hard_filter_failures` and in `screen`, never as an apply block.
- The **score is computed and shown either way.** Eligibility is a flag, not part of
  the score.
- Ranking uses `profiles.match.read_job`, `profile_payload` and `score_profile`.
  **Do not write a second scorer.**

### Notification triggers (D26)

1. **On an opportunity reaching `open`,** whether by admin approval or admin creation, a
   `new_opportunity` notification goes to every student who:
   - has an account and `status = active`;
   - has `is_placement_eligible` on the roster;
   - **passes eligibility**.

   No scoring happens inside the request.
2. **`manage.py notify_deadlines`** sends `deadline_soon` for `open` postings whose
   deadline falls within `OPPORTUNITIES["DEADLINE_NOTICE_DAYS"]`, to eligible students
   who **have not applied**. Running it twice sends nothing new.

| Method + path | URL name | Notes |
| --- | --- | --- |
| `GET /api/notifications/` | `notification-list` | own only. `?unread=true`. Each row `{id, kind, opportunity: {id, title}, created_at, read_at}` |
| `POST /api/notifications/<id>/read` | `notification-read` | own only, 204 |
| `POST /api/notifications/read-all` | `notification-read-all` | 204 |

## Endpoints — Stage 3 (suggestions)

`GET /api/opportunities/suggestions`, URL name `opportunity-suggestions`. Student only, with `MatchingThrottle`.

- Returns `open` postings, deadline today or later, with `score >= (posting.similarity_threshold or SUGGESTIONS["MIN_SCORE"])`.
- They are sorted by score desc and capped at `SUGGESTIONS["MAX_RESULTS"]`. The row shape is the same as `feed`.
- The response is `{"results": [...], "open_count": int, "reason": "no_open_postings" | "none_match" | null}`.
  This lets the empty state tell "nothing posted yet" apart from "nothing fits you well".
- Scores are cached per `(resume_digest, opportunity.id, opportunity.updated_at)`.
  The feed uses the same cache.
- **The page never says "probability".** The score is a guide, not a prediction.

## Endpoints — Stage 4 (recruiter exports)

These live under `/api/profiles/`. The routes are company-only, and every list is built on **the company's shortlist** as defined in D27.

| Method + path | URL name | Notes |
| --- | --- | --- |
| `GET students?shortlisted=true` | `company-profile-list` | a new `CompanyProfileFilter(StudentProfileFilter)` with `shortlisted`. `is_shortlisted` is annotated on the page query, with no per-row EXISTS |
| `GET students/shortlist/resumes` | `company-shortlist-resumes` | a ZIP of the **current** resumes, named `<PRN>-<full name>.<ext>`. Students with no resume are skipped, counted in the `X-Skipped-Without-Resume` header, and listed in a `SKIPPED.txt` inside the zip. Audited as `documents_bulk_downloaded`, with `{count, skipped, company}`. Uses the `export` throttle |
| `POST students/shortlist/contacts` | `company-shortlist-contacts` | **200 JSON** `{"password", "filename", "zip_base64", "row_count"}`. The zip is **AES-256** (`pyzipper`) and holds `contacts.csv` with columns `prn,full_name,department,programme,batch,cgpa,email,phone,contact_available,shortlisted_on`. The password is random, at least 16 characters, returned once and **never written inside the archive**. Unverified students get a row with blank email and phone and `contact_available=false`. More than `OPPORTUNITIES["EXPORT_MAX_ROWS"]` rows is a 400. Audited as `shortlist_exported`, with `{count, company}`. Uses the `export` throttle |

## Demo data

`seed_demo` gains:
- opportunities in **every status** for Acme and Nimbus, with salaries;
- applications from the populated students across the application statuses, with events;
- at least one notification.

`DEMO_LOGINS.md` gets a section describing them.
