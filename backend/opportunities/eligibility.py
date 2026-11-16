"""
Who may apply (D28).

Only registrar facts decide it: the roster's department and CGPA. A CGPA the
student typed or a transcript printed is never used, so the figure a company
filters on cannot be self-reported. Experience and education are not here:
they are screening filters for recruiters, not reasons to refuse an apply.
"""

from __future__ import annotations

from decimal import Decimal


def _norm(value: str) -> str:
    return " ".join((value or "").lower().split())


def check_eligibility(opportunity, student) -> tuple[bool, list[str]]:
    """`(eligible, reasons)` for a roster `Student` against one posting."""
    reasons: list[str] = []

    departments = [_norm(d) for d in opportunity.eligible_departments or []]
    # The list holds programme names (roster.reference) but the roster's
    # department is free text, so either one may match.
    if departments and not ({_norm(student.department), _norm(student.programme)} & set(departments)):
        reasons.append(
            f"Open to {', '.join(opportunity.eligible_departments)} only; "
            f"your department is {student.department or 'not recorded'}."
        )

    minimum = opportunity.min_cgpa
    if minimum is not None:
        if student.cgpa is None:
            reasons.append(f"Needs a CGPA of {minimum:g}; the roster has none for you.")
        elif Decimal(student.cgpa) < Decimal(minimum):
            reasons.append(f"Needs a CGPA of {minimum:g}; the roster shows {student.cgpa:g}.")

    return (not reasons, reasons)
