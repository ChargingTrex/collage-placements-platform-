"""
Synthetic transcript PDFs for the R5 gate.

Laid out the way `REQUIREMENTS-ADDENDUM.md` § "Reference: transcript format"
describes the real document, but every name, PRN and number here is invented.
Nothing is copied from a real student's transcript.

The numbers are chosen so the recomputed CGPA, sum(credits x SGPA) / sum(credits),
is exact: three semesters of 20 credits at 8.00, 8.50 and 9.00 give 8.50.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

#: (semester credits, semester GPA). 20*8.0 + 20*8.5 + 20*9.0 = 510 / 60 = 8.50.
STANDARD_SEMESTERS = ((20, "8.00"), (20, "8.50"), (20, "9.00"))
RECOMPUTED = Decimal("8.50")

SCHOOL = "School of Computing and Data Science"
DEGREE = "BTech"

_COURSES = (
    ("CS101", "Programming Fundamentals", "4.0", "A"),
    ("CS102", "Discrete Mathematics", "4.0", "A+"),
    ("CS103", "Digital Logic", "4.0", "B+"),
    ("HS101", "Communication Skills", "4.0", "O"),
    ("MA101", "Calculus", "4.0", "A"),
)


def recompute(semesters) -> Decimal:
    """sum(credits x SGPA) / sum(credits), the cross-check R5 asks for."""
    total = sum(Decimal(str(c)) for c, _ in semesters)
    weighted = sum(Decimal(str(c)) * Decimal(str(g)) for c, g in semesters)
    return (weighted / total).quantize(Decimal("0.01"))


def render_transcript(
    path,
    *,
    prn,
    name,
    school=SCHOOL,
    degree=DEGREE,
    semesters=STANDARD_SEMESTERS,
    cgpa="8.50",
    total_credits="60.0",
    split_page=False,
    text=True,
):
    """Draw a transcript PDF at `path` and return the path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = Path(path)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    if not text:
        # Image-only page: shapes and no text objects, as a scan would be.
        pdf.setFillGray(0.85)
        for row in range(12):
            pdf.rect(50, height - 90 - row * 40, width - 100, 22, fill=1, stroke=0)
        pdf.showPage()
        pdf.save()
        return path

    state = {"y": height - 50}

    def line(content, size=10, gap=16):
        pdf.setFont("Helvetica", size)
        pdf.drawString(50, state["y"], content)
        state["y"] -= gap

    def new_page():
        pdf.showPage()
        state["y"] = height - 50

    line("Transcript Issue Date: 05-Jul-26", 11)
    line(f"Name: {name} PRN: {prn}", 11)
    line(school, 11)
    line(f"{degree} Total Credits: {total_credits} Cumulative GPA: {cgpa}", 11, 26)

    split_at = 1 if split_page else None  # split the middle semester
    for index, (credits, sgpa) in enumerate(semesters):
        year_start = 2022 + index // 2
        heading = (
            f"Academic Year {year_start}-{str(year_start + 1)[-2:]} "
            f"Semester {float(index + 1):.1f}"
        )
        line(heading, 11)
        rows = list(_COURSES)
        if index == split_at:
            for code, title, cr, grade in rows[:2]:
                line(f"{code} {title} {cr} {grade}")
            new_page()
            line(f"{heading} (contd.)", 11)
            rows = rows[2:]
        for code, title, cr, grade in rows:
            line(f"{code} {title} {cr} {grade}")
        line(f"Semester Credits: {float(credits):.1f} Semester GPA: {sgpa}", 10, 24)

    line("Note: CGPA is the credit-weighted average of semester GPAs.", 8)
    pdf.showPage()
    pdf.save()
    return path


@dataclass(frozen=True)
class Case:
    """One ready-made transcript and what the gate expects of it."""

    kind: str
    roster_cgpa: str
    printed: str | None
    recomputed: str | None
    status: str  # expected cgpa_review_status


CASES = {
    "clean": Case("clean", "8.50", "8.50", "8.50", "not_needed"),
    # Printed 9.40 against a recomputed 8.50: the figure was altered.
    "tampered": Case("tampered", "9.40", "9.40", "8.50", "open"),
    # Printed == recomputed (8.50) but the roster says 7.90.
    "roster_mismatch": Case("roster_mismatch", "7.90", "8.50", "8.50", "open"),
    "wrong_prn": Case("wrong_prn", "8.50", None, None, "n/a"),
    "image_only": Case("image_only", "8.50", None, None, "open"),
    "contd_split": Case("contd_split", "8.50", "8.50", "8.50", "not_needed"),
}


def make_case(kind, directory, *, prn, name="Test Student", other_prn="999999999"):
    """Write the transcript for `kind` into `directory` and return its path."""
    case = CASES[kind]
    path = Path(directory) / f"transcript_{kind}.pdf"
    if kind == "image_only":
        return render_transcript(path, prn=prn, name=name, text=False)
    if kind == "wrong_prn":
        return render_transcript(path, prn=other_prn, name=name)
    printed = case.printed
    return render_transcript(
        path,
        prn=prn,
        name=name,
        cgpa=printed,
        split_page=(kind == "contd_split"),
    )
