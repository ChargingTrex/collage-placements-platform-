"""
Read a Sai University transcript PDF (R5).

Transcripts only. CGPA is never taken from a resume, so the resume path
(`extractors.py`, `engine.py`) must not import this module.

The parser reports what the document says; it validates nothing. The caller
compares the PRN with the student's and the CGPA with the roster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .extraction import ResumeParseError, extract_text

#: Printed vs recomputed CGPA may differ by this much (rounding in the source).
AGREE_TOLERANCE = Decimal("0.02")

_NUM = r"(\d+(?:\.\d+)?)"

_ISSUE_DATE = re.compile(r"Transcript Issue Date:\s*(\S+)")
# Name and PRN share a line; the name is everything up to "PRN:".
_NAME = re.compile(r"Name:\s*(.+?)\s+PRN:")
_PRN = re.compile(r"PRN:\s*(\S+)")
_SCHOOL = re.compile(r"^\s*(School of .+?)\s*$", re.MULTILINE)
_TOTALS = re.compile(r"^\s*(\S+)\s+Total Credits:\s*" + _NUM, re.MULTILINE)
# The label is "Cumulative GPA:". "CGPA" appears only in the notes page, which
# is explanatory text and may carry any number, so it is deliberately not matched.
_CUMULATIVE = re.compile(r"Cumulative GPA:\s*" + _NUM)
_SEM_HEADING = re.compile(r"Academic Year\s+(\d{4}-\d{2})\s+Semester\s+(\d+(?:\.\d+)?)")
_SEM_TOTALS = re.compile(r"Semester Credits:\s*" + _NUM + r"\s+Semester GPA:\s*" + _NUM)


@dataclass
class TranscriptFacts:
    prn: str = ""
    name: str = ""
    school: str = ""
    degree: str = ""
    total_credits: Decimal | None = None
    printed_cgpa: Decimal | None = None
    issue_date: str = ""
    #: (label, credits, sgpa) per semester, in document order.
    semesters: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    recomputed_cgpa: Decimal | None = None
    has_text: bool = False

    @property
    def agrees(self) -> bool | None:
        """Printed CGPA matches the recomputed one; None if either is missing."""
        if self.printed_cgpa is None or self.recomputed_cgpa is None:
            return None
        return abs(self.printed_cgpa - self.recomputed_cgpa) <= AGREE_TOLERANCE


def _first(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _parse_semesters(text: str) -> list[tuple[str, Decimal, Decimal]]:
    semesters = []
    label = ""
    for line in text.splitlines():
        heading = _SEM_HEADING.search(line)
        if heading:
            # A "(contd.)" heading repeats the label of the table it continues,
            # so it just keeps the current label. Only the closing totals line
            # emits a semester, which means a split table is counted once.
            label = f"{heading.group(1)} Semester {heading.group(2)}"
            continue
        totals = _SEM_TOTALS.search(line)
        if totals and label:
            semesters.append((label, Decimal(totals.group(1)), Decimal(totals.group(2))))
            label = ""
    return semesters


def _recompute(semesters) -> Decimal | None:
    total_credits = sum((credits for _, credits, _ in semesters), Decimal(0))
    if total_credits == 0:
        return None
    weighted = sum((credits * sgpa for _, credits, sgpa in semesters), Decimal(0))
    # ROUND_HALF_UP, not the default banker's rounding: 8.005 must print as 8.01
    # to match how the registrar rounds.
    return (weighted / total_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_transcript_text(text: str) -> TranscriptFacts:
    """Parse already-extracted transcript text."""
    if not text or not text.strip():
        return TranscriptFacts()

    totals = _TOTALS.search(text)
    cumulative = _CUMULATIVE.search(text)
    semesters = _parse_semesters(text)
    return TranscriptFacts(
        prn=_first(_PRN, text),
        name=_first(_NAME, text),
        school=_first(_SCHOOL, text),
        # Degree is the first token of the totals line ("BTech Total Credits: ...").
        degree=totals.group(1) if totals else "",
        total_credits=Decimal(totals.group(2)) if totals else None,
        printed_cgpa=Decimal(cumulative.group(1)) if cumulative else None,
        issue_date=_first(_ISSUE_DATE, text),
        semesters=semesters,
        recomputed_cgpa=_recompute(semesters),
        has_text=True,
    )


def parse_transcript(path_or_file) -> TranscriptFacts:
    """Parse a transcript PDF given a path or an open binary file."""
    try:
        if hasattr(path_or_file, "read"):
            text = extract_text(path_or_file, "transcript.pdf")
        else:
            with open(Path(path_or_file), "rb") as handle:
                text = extract_text(handle, "transcript.pdf")
    except ResumeParseError:
        # No text layer (a scan) or an unreadable PDF: report "no text" and let
        # the caller fall back to manual entry instead of failing the upload.
        return TranscriptFacts()
    return parse_transcript_text(text)
