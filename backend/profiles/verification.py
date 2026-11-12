"""
Preliminary verification of a profile, for the placement cell only.

`matching.verification.compare` is pure; this module feeds it a profile's
stored readings, its current form and its roster row. The flags are never
stored: they are recomputed on every admin read, so an edit to the form or
the roster shows at once and nothing goes stale.

Only `AdminProfileSerializer` calls this. The student's own payload, the
company views and the resume endpoints never do (RESUME_INTELLIGENCE_PLAN.md
§2: flags, age, DOB and the resume's CGPA are admin-only).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from matching import verification
from profiles.models import ResumeAnalysis, StudentProfile


def _analysis(profile: StudentProfile) -> ResumeAnalysis | None:
    """The finished reading, read from the select_related cache when there is one."""
    try:
        analysis = profile.analysis
    except ObjectDoesNotExist:
        return None
    return analysis if analysis.status == ResumeAnalysis.Status.DONE else None


def verification_inputs(profile: StudentProfile) -> tuple[dict, dict]:
    """(form, roster) as the plain dicts `compare` takes. Uses prefetched children."""
    student = profile.student
    form = {
        "experience_years": float(profile.experience_years),
        "education_level": profile.education_level or None,
        "experience": [
            {
                "role": entry.role,
                "organization": entry.organization,
                "start_date": entry.start_date.isoformat(),
                "end_date": entry.end_date.isoformat() if entry.end_date else None,
                "duration_months": entry.duration_months,
            }
            for entry in profile.experience_entries.all()
        ],
        "projects": [project.title for project in profile.projects.all()],
        "skills": [skill.name for skill in profile.skills.all()],
    }
    roster = {
        "full_name": student.full_name,
        "email": student.email,
        "phone": student.phone,
        "cgpa": float(student.cgpa) if student.cgpa is not None else None,
        "batch": student.batch,
        "programme": student.programme,
        "department": student.department,
    }
    return form, roster


def verification_checks(profile: StudentProfile) -> list[verification.Flag]:
    """The profile's flags, computed now from its reading, form and roster row."""
    analysis = _analysis(profile)
    if analysis is None:
        return []
    form, roster = verification_inputs(profile)
    # The transcript's printed CGPA, now that the extractor exists. The
    # student's own figure rides alongside it: `compare` treats both as two
    # more sources to disagree with, not as the answer.
    return verification.compare(
        analysis.facts,
        analysis.regex_facts,
        form,
        roster,
        transcript_cgpa=_as_float(profile.parsed_cgpa),
        student_cgpa=_as_float(profile.confirmed_cgpa),
    )


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


#: Where a CGPA can come from, worst-to-best known. Order is display order.
CGPA_SOURCES = (
    ("roster", "Roster"),
    ("transcript_printed", "Printed on transcript"),
    ("transcript_recomputed", "Recomputed from semesters"),
    ("student", "Stated by the student"),
)


def cgpa_sources(profile: StudentProfile) -> dict:
    """
    Every CGPA on record for this profile, and which pairs disagree.

    Separate from `verification_checks` on purpose: that one returns nothing
    until a resume has been read, so a student who has stated a CGPA but
    uploaded no resume would otherwise have their disagreement go unseen.
    """
    from itertools import combinations

    tolerance = getattr(settings, "VERIFICATION", {}).get(
        "CGPA_TOLERANCE", verification.DEFAULT_CGPA_TOLERANCE
    )
    values = {
        "roster": _as_float(profile.student.cgpa),
        "transcript_printed": _as_float(profile.parsed_cgpa),
        "transcript_recomputed": _as_float(profile.recomputed_cgpa),
        "student": _as_float(profile.confirmed_cgpa),
    }
    present = [(key, value) for key, value in values.items() if value is not None]
    disagreements = [
        {
            "sources": [first, second],
            "values": {first: a, second: b},
            "message": (
                f"{dict(CGPA_SOURCES)[first]} ({a:g}) and "
                f"{dict(CGPA_SOURCES)[second]} ({b:g}) differ by more than {tolerance:g}."
            ),
        }
        for (first, a), (second, b) in combinations(present, 2)
        if round(abs(a - b), 4) > tolerance
    ]
    return {
        "values": values,
        "labels": dict(CGPA_SOURCES),
        "tolerance": float(tolerance),
        "disagreements": disagreements,
    }


def warning_count(flags: list[verification.Flag]) -> int:
    return sum(flag.severity == verification.WARNING for flag in flags)


def resume_facts_admin(profile: StudentProfile) -> dict | None:
    """
    What the resume says about the student's age, DOB, CGPA and contacts.

    For the admin reviewing the flags, never for anyone else. The model's
    reading first, regex behind it; None until the resume has been read.
    """
    analysis = _analysis(profile)
    if analysis is None:
        return None
    facts, regex = analysis.facts or {}, analysis.regex_facts or {}

    def first(key):
        return facts.get(key) if facts.get(key) is not None else regex.get(key)

    emails = [*(facts.get("emails") or []), *(regex.get("emails") or [])]
    phones = [p for raw in [*(facts.get("phones") or []), *(regex.get("phones") or [])] for p in verification.normalise_phones(raw)]
    return {
        "age": first("age"),
        "date_of_birth": first("date_of_birth"),
        "cgpa": first("cgpa"),
        "phones": list(dict.fromkeys(phones)),
        "emails": list(dict.fromkeys(email.strip().lower() for email in emails if email)),
        "source": analysis.source or None,
    }
