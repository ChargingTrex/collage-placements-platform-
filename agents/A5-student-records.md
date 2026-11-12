# A5 — Student Records

Read [`CONTEXT.md`](../CONTEXT.md) first.

## You own

`profiles/` · `components/ui/` (the shared design kit — others request changes,
you make them) · all of `REQUIREMENTS-ADDENDUM.md` R1–R5.

## Phase A — stream A-5

Fixtures and the frontend auth surface:

- Regenerate every fixture to **nine-digit PRNs** (`220200921`) and the real
  Sai University schools. The current `PRN2022CS001` shape is invented and will
  fail the new validator.
- Migrate the frontend to `roles[]` and `display_name`.
- Update all 43 frontend tests.

**G2 changes every frontend URL** — PRN leaves path parameters and becomes a
filter. The API and the client move in **one commit**, not two. Coordinate with
whoever lands the API side.

## Phase E — your lead phase

R1–R5 in the addendum's own order: R1 (admin profile/resume view — API already
exists, UI only) → R2 (career path) → R4 (onboarding) → R3 (outcomes
dashboard) → R5 (transcript CGPA).

### Three things not to get wrong

1. **`parsed_experience_years` is what the engine read; `experience_years` is
   what the student confirmed.** Never collapse them — re-uploading a resume
   must not undo a correction. Same pattern applies to transcript CGPA.
2. **CGPA is never parsed from a resume.** R5 is a *new* extractor module. Do
   not wire it into the resume path.
3. **The transcript's PRN is checked against the signed-in student's own.**
   Without it, a student uploads somebody else's transcript and inherits their
   CGPA. A mismatch is refused and logged, never stored.

### R3 is blocked

The outcomes dashboard groups on school and programme codes that the registrar
has not yet confirmed. Build R1, R2, R4, R5 first.
