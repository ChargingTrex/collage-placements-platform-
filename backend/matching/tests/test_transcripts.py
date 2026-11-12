"""R5 transcript parser, against the synthetic PDFs in checkpoints."""

from decimal import Decimal

import pytest

from checkpoints.transcript_fixtures import CASES, SCHOOL, make_case
from matching.transcripts import TranscriptFacts, parse_transcript, parse_transcript_text

PRN = "220200930"


def facts_for(kind, tmp_path):
    return parse_transcript(make_case(kind, tmp_path, prn=PRN, name="Test Student"))


def d(value):
    return None if value is None else Decimal(value)


@pytest.mark.parametrize("kind", ["clean", "tampered", "roster_mismatch", "contd_split"])
def test_text_cases_match_expected_values(kind, tmp_path):
    case = CASES[kind]
    facts = facts_for(kind, tmp_path)
    assert facts.has_text
    assert facts.prn == PRN
    assert facts.name == "Test Student"
    assert facts.school == SCHOOL
    assert facts.degree == "BTech"
    assert facts.total_credits == Decimal("60.0")
    assert facts.issue_date == "05-Jul-26"
    assert facts.printed_cgpa == d(case.printed)
    assert facts.recomputed_cgpa == d(case.recomputed)
    assert [(c, g) for _, c, g in facts.semesters] == [
        (Decimal("20.0"), Decimal("8.00")),
        (Decimal("20.0"), Decimal("8.50")),
        (Decimal("20.0"), Decimal("9.00")),
    ]


def test_clean_agrees(tmp_path):
    assert facts_for("clean", tmp_path).agrees is True


def test_tampered_disagrees(tmp_path):
    facts = facts_for("tampered", tmp_path)
    assert facts.printed_cgpa == Decimal("9.40")
    assert facts.agrees is False


def test_roster_mismatch_still_agrees_internally(tmp_path):
    # The roster comparison is the caller's job; the document itself is consistent.
    assert facts_for("roster_mismatch", tmp_path).agrees is True


def test_wrong_prn_is_returned_unvalidated(tmp_path):
    facts = facts_for("wrong_prn", tmp_path)
    assert facts.prn == "999999999"
    assert facts.prn != PRN


def test_image_only_returns_empty_facts_without_raising(tmp_path):
    facts = facts_for("image_only", tmp_path)
    assert facts.has_text is False
    assert facts.prn == "" and facts.name == "" and facts.school == ""
    assert facts.degree == "" and facts.issue_date == ""
    assert facts.total_credits is None
    assert facts.printed_cgpa is None
    assert facts.recomputed_cgpa is None
    assert facts.semesters == []
    assert facts.agrees is None


def test_contd_semester_counted_once(tmp_path):
    facts = facts_for("contd_split", tmp_path)
    labels = [label for label, _, _ in facts.semesters]
    assert len(labels) == 3 and len(set(labels)) == 3
    assert facts.recomputed_cgpa == Decimal("8.50")


def test_accepts_open_file(tmp_path):
    path = make_case("clean", tmp_path, prn=PRN)
    with open(path, "rb") as handle:
        assert parse_transcript(handle).printed_cgpa == Decimal("8.50")


def test_prn_is_trimmed():
    assert parse_transcript_text("Name: A B PRN:   220200931  \n").prn == "220200931"


CONTD_TEXT = """\
Transcript Issue Date: 05-Jul-26
Name: Test Student PRN: 220200930
BTech Total Credits: 30.0 Cumulative GPA: 8.00
Academic Year 2022-23 Semester 1.0
CS101 Programming 4.0 A
Academic Year 2022-23 Semester 1.0 (contd.)
CS102 Maths 4.0 A
Semester Credits: 15.0 Semester GPA: 7.00
Academic Year 2022-23 Semester 2.0
Semester Credits: 15.0 Semester GPA: 9.00
"""


def test_contd_text_reads_semester_whole():
    facts = parse_transcript_text(CONTD_TEXT)
    assert facts.semesters == [
        ("2022-23 Semester 1.0", Decimal("15.0"), Decimal("7.00")),
        ("2022-23 Semester 2.0", Decimal("15.0"), Decimal("9.00")),
    ]
    assert facts.recomputed_cgpa == Decimal("8.00")


def test_notes_page_cgpa_is_not_the_cumulative_gpa():
    text = "Note: CGPA is the credit-weighted average. CGPA: 3.10\n"
    assert parse_transcript_text(text).printed_cgpa is None


def test_header_wins_over_notes_cgpa():
    text = "BTech Total Credits: 60.0 Cumulative GPA: 8.50\nNote: CGPA: 3.10\n"
    assert parse_transcript_text(text).printed_cgpa == Decimal("8.50")


def test_recompute_rounds_half_up():
    # (15*8.01 + 15*8.00) / 30 = 8.005 -> 8.01 (banker's rounding would give 8.00)
    text = (
        "Academic Year 2022-23 Semester 1.0\nSemester Credits: 15.0 Semester GPA: 8.01\n"
        "Academic Year 2022-23 Semester 2.0\nSemester Credits: 15.0 Semester GPA: 8.00\n"
    )
    assert parse_transcript_text(text).recomputed_cgpa == Decimal("8.01")


def test_agrees_tolerance_is_inclusive_and_none_when_missing():
    base = dict(
        prn="", name="", school="", degree="", total_credits=None,
        issue_date="", semesters=[], has_text=True,
    )
    on_edge = TranscriptFacts(printed_cgpa=Decimal("8.52"), recomputed_cgpa=Decimal("8.50"), **base)
    past = TranscriptFacts(printed_cgpa=Decimal("8.53"), recomputed_cgpa=Decimal("8.50"), **base)
    missing = TranscriptFacts(printed_cgpa=None, recomputed_cgpa=Decimal("8.50"), **base)
    assert on_edge.agrees is True
    assert past.agrees is False
    assert missing.agrees is None
