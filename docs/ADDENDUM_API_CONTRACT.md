# R1–R5 API contract

The shapes every agent builds and tests against for
[`REQUIREMENTS-ADDENDUM.md`](../REQUIREMENTS-ADDENDUM.md). Tests in
`backend/checkpoints/test_checkpoint_e.py` assert exactly this. If a shape has
to change, change it here first, then the tests, then the code.

All paths are under `/api/profiles/`. "Student id" means the roster
`Student.id` UUID (profiles are addressed by it, D14). Every endpoint answers
401 to an anonymous caller.

## Profile payload additions

**Own profile (`GET/PATCH me`) and admin profile (`GET admin/<student_id>`)** gain:

| Field | Type | Notes |
| --- | --- | --- |
| `career_path` | string | one of the 9 values below; default `"undecided"` |
| `career_path_detail` | string | required non-blank when `career_path == "other"`, else stored as `""` |
| `also_attending_placements` | bool | default `false` |
| `personal_email` | string | optional; must differ from the college email |
| `onboarding_completed` | bool | read-only; `onboarding_completed_at is not null` |
| `onboarding_completed_at` | datetime or null | read-only |
| `resume_url` | string or null | **API url** `/api/profiles/me/resume/file` (own) or `/api/profiles/admin/<id>/resume` (admin). Never a `/media/` url |
| `transcript_url` | string or null | `/api/profiles/me/transcript/file` (own) or `/api/profiles/admin/<id>/transcript` (admin) |
| `transcript_filename` | string | original filename |
| `transcript_prn`, `transcript_school`, `transcript_degree` | string | as read from the transcript |
| `parsed_cgpa` | decimal string or null | the printed `Cumulative GPA` |
| `recomputed_cgpa` | decimal string or null | Σ(credits × SGPA) / Σ credits |
| `confirmed_cgpa` | decimal string or null | what the student confirmed or typed |
| `cgpa_matches_roster` | bool or null | null until a transcript is read |
| `cgpa_review_status` | string | `not_needed` · `open` · `resolved` |

**Company profile (`GET students/…`) gains none of these.** In particular, no
`career_path*`, no `personal_email`, no `transcript*`, and none of the
`*_cgpa` fields. Roster CGPA stays visible as before, under `student.cgpa`.

### Career path values

`placement`, `business`, `higher_studies`, `entrepreneurship`, `research`,
`family_business`, `competitive_exams`, `other`, `undecided`.

Profile completion gains a `career_path` item. It is done when the value is
not `undecided`.

## Documents (R1, R5)

| Method + path | Who | Result |
| --- | --- | --- |
| `GET me/resume/file` | student | the file, or 404 if none |
| `GET me/transcript/file` | student | the file, or 404 if none |
| `GET admin/<student_id>/resume` | admin | the file; writes `AuditLog` `document_accessed` |
| `GET admin/<student_id>/transcript` | admin | the file; writes `document_accessed` |
| `GET students/<student_id>/resume` | company | the file if the profile is visible to that company, else 404; writes `document_accessed` |
| `GET students/<student_id>/transcript` | company | **always 404**, because companies never see transcripts |

Files are returned with `Content-Disposition` carrying the original filename.
URL names are `my-resume-file`, `my-transcript-file`, `admin-profile-resume`,
`admin-profile-transcript`, `company-profile-resume` and
`company-profile-transcript`.

## Transcript (R5)

`POST me/transcript` (multipart, field `file`, PDF only), URL name `my-transcript`:

- **The PRN read from the transcript differs from the student's:** 400 `{"detail": …, "reason": "prn_mismatch"}`. An `AuditLog` row `transcript_prn_mismatch` is written. **The file is not stored.**
- **Not a PDF, or over the size limit:** 400.
- **Otherwise:** 201 with the own-profile payload. The file is stored and the parsed fields are set. `cgpa_review_status` becomes `open`, with an `AuditLog` row `cgpa_mismatch_flagged`, when any of these hold:
  - the printed and roster CGPA differ by more than **0.05**;
  - the printed and recomputed CGPA differ by more than **0.02**;
  - no CGPA could be read.

  Otherwise `cgpa_review_status` is `not_needed`.
- **The roster's `Student.cgpa` is never written.**

| Method + path | Name | Body | Effect |
| --- | --- | --- | --- |
| `POST me/confirm-cgpa` | `my-confirm-cgpa` | `{"cgpa": "8.40"}`, 0–10 | sets `confirmed_cgpa` only |
| `POST admin/<student_id>/cgpa-review` | `admin-profile-cgpa-review` | `{"status": "resolved", "note": "…"}` | sets `cgpa_review_status = "resolved"`; `AuditLog` row `cgpa_review_resolved` |

Both answer **200** with the profile payload (own for `confirm-cgpa`, admin for
`cgpa-review`). `cgpa` outside 0–10, non-numeric or blank is 400.

**A resume upload never sets any `*_cgpa` field.**

## Onboarding (R4)

| Method + path | Name | Notes |
| --- | --- | --- |
| `GET me/onboarding` | `my-onboarding` | `{"completed": bool, "dismissed": bool, "student": {"prn", "full_name", "email", "department", "school", "batch", "year_of_study"} (read-only, same keys as the admin payload's `student`), "phone", "personal_email", "career_path", "career_path_detail", "also_attending_placements", "headline", "summary"}` |
| `POST me/onboarding` | `my-onboarding` | requires `phone` and `career_path`; `other` needs a non-blank `career_path_detail` here too. `personal_email` is optional, and 400 if it equals the college email. Sets `onboarding_completed_at`; 200 with the GET shape |
| `POST me/onboarding/dismiss` | `my-onboarding-dismiss` | sets `onboarding_dismissed_at`; 204 |

`GET admin/stats` gains `"onboarding_completed": <count>`.

## Outcomes (R3)

`GET admin/outcomes?batch=2026` (batch optional), URL name `admin-profile-outcomes`:

```json
{
  "batch": 2026,
  "paths": [{"value": "placement", "label": "Placement / campus recruitment"}],
  "rows": [
    {"school": "computing_data_science", "school_name": "School of Computing and Data Science",
     "counts": {"placement": 3, "undecided": 1}, "total": 4}
  ],
  "totals": {"placement": 3, "undecided": 1},
  "grand_total": 4,
  "also_attending_placements": 0,
  "verified": 2
}
```

- **Base set:** roster students who have a user account, filtered by `batch` when given.
- A student with no profile, a blank path, or `undecided` counts under `undecided`. `sum(totals.values()) == grand_total`.
- `counts` carries every path key, zeros included.
- A blank or unknown school goes in the row `"school": "unassigned"`.

`GET admin/outcomes/export?batch=2026`, URL name `admin-profile-outcomes-export`, returns `text/csv`:

- header row `school,<path>…,total`;
- one row per school;
- a final `total` row.

Admin only: 403 for students and companies.

## Settled while writing the tests (E0)

- Anonymous calls are 401 on every route, POST-only ones included: DRF
  authenticates before it checks the method.
- `contd-split` transcripts are judged by the result: `recomputed_cgpa` comes
  out right only if the continued semester was read whole.
- Roster `Student.school` holds the school **key** (`computing_data_science`);
  blank goes to the `unassigned` row.
