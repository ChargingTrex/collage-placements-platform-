"""Roster CSV import: row-level validation, upsert behaviour, and refusals."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from roster.importers import RosterFormatError, import_roster_csv
from roster.models import Student

HEADER = "prn,email,full_name,department,batch,cgpa\n"


def csv_file(body: str, name: str = "roster.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, body.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
def test_imports_valid_rows():
    result = import_roster_csv(
        csv_file(
            HEADER
            + "220200901,a.mehta@college.edu,Aarav Mehta,Computer Engineering,2026,8.72\n"
            + "220200904,s.qureshi@college.edu,Sana Qureshi,Information Technology,2026,8.05\n"
        )
    )

    assert result.created == 2
    assert result.ok
    assert Student.objects.count() == 2
    student = Student.objects.get(prn="220200901")
    assert student.full_name == "Aarav Mehta"
    assert str(student.cgpa) == "8.72"


@pytest.mark.django_db
def test_trims_prn_whitespace_and_normalises_email_case():
    # PRNs are digits only, so this checks trimming of the PRN, not its case.
    import_roster_csv(
        csv_file(HEADER + " 220200901 ,A.Mehta@College.edu,Aarav,CE,2026,8.0\n")
    )

    student = Student.objects.get()
    assert student.prn == "220200901"
    assert student.email == "a.mehta@college.edu"


@pytest.mark.django_db
def test_reupload_updates_in_place_rather_than_duplicating():
    import_roster_csv(csv_file(HEADER + "220200961,a@college.edu,Old Name,CE,2026,7.0\n"))
    result = import_roster_csv(
        csv_file(HEADER + "220200961,a@college.edu,New Name,CE,2026,8.5\n")
    )

    assert (result.created, result.updated) == (0, 1)
    assert Student.objects.count() == 1
    assert Student.objects.get().full_name == "New Name"


@pytest.mark.django_db
def test_identical_reupload_counts_as_unchanged():
    row = HEADER + "220200961,a@college.edu,Same Name,CE,2026,7.00\n"
    import_roster_csv(csv_file(row))
    result = import_roster_csv(csv_file(row))

    assert (result.created, result.updated, result.unchanged) == (0, 0, 1)


@pytest.mark.django_db
def test_bad_rows_are_reported_by_line_number_and_good_rows_still_save():
    body = (
        HEADER
        + "220200950,valid@college.edu,Valid Student,CE,2026,8.10\n"  # line 2
        + ",missing.prn@college.edu,Missing PRN,CE,2026,7.00\n"          # line 3
        + "220200953,bad.cgpa@college.edu,Bad Cgpa,EC,2026,eleven\n"  # line 4
        + "220200955,out.of.range@college.edu,Out Of Range,ME,2026,14.5\n"  # line 5
    )

    result = import_roster_csv(csv_file(body))

    assert result.created == 1
    assert [error.row for error in result.errors] == [3, 4, 5]
    assert "prn" in result.errors[0].errors
    assert "cgpa" in result.errors[1].errors
    assert "cgpa" in result.errors[2].errors  # 14.5 fails the 0-10 validator
    assert Student.objects.filter(prn="220200950").exists()
    assert not Student.objects.filter(prn="220200953").exists()


@pytest.mark.django_db
def test_invalid_email_is_a_row_error_not_a_crash():
    result = import_roster_csv(csv_file(HEADER + "220200961,not-an-email,Bad,CE,2026,7.0\n"))

    assert result.created == 0
    assert "email" in result.errors[0].errors


@pytest.mark.django_db
def test_email_already_used_by_another_prn_is_rejected():
    import_roster_csv(csv_file(HEADER + "220200961,shared@college.edu,First,CE,2026,7.0\n"))
    result = import_roster_csv(csv_file(HEADER + "220200962,shared@college.edu,Second,CE,2026,7.0\n"))

    assert result.created == 0
    assert "220200961" in result.errors[0].errors["email"][0]


@pytest.mark.django_db
def test_dry_run_reports_without_writing():
    result = import_roster_csv(
        csv_file(HEADER + "220200961,a@college.edu,Aarav,CE,2026,8.0\n"), dry_run=True
    )

    assert result.created == 1
    assert Student.objects.count() == 0  # rolled back


@pytest.mark.django_db
def test_missing_required_column_rejects_the_whole_file():
    with pytest.raises(RosterFormatError, match="Missing required column"):
        import_roster_csv(csv_file("prn,email\n220200961,a@college.edu\n"))


@pytest.mark.django_db
def test_empty_file_is_rejected():
    with pytest.raises(RosterFormatError, match="empty"):
        import_roster_csv(csv_file(""))


@pytest.mark.django_db
def test_excel_style_batch_and_bom_are_tolerated():
    # Excel writes a UTF-8 BOM and exports 2026 as "2026.0".
    body = HEADER + "220200961,a@college.edu,Aarav,CE,2026.0,8.0\n"
    result = import_roster_csv(io.BytesIO(body.encode("utf-8-sig")))

    assert result.created == 1
    assert Student.objects.get().batch == 2026


@pytest.mark.django_db
def test_cgpa_is_optional():
    result = import_roster_csv(csv_file(HEADER + "220200961,a@college.edu,Aarav,CE,2026,\n"))

    assert result.created == 1
    assert Student.objects.get().cgpa is None


@pytest.mark.django_db
def test_ineligible_flag_is_read_from_the_file():
    body = (
        "prn,email,full_name,department,batch,cgpa,is_placement_eligible\n"
        "220200961,a@college.edu,Aarav,CE,2026,8.0,false\n"
    )
    import_roster_csv(csv_file(body))

    assert Student.objects.get().is_placement_eligible is False


# --- school / programme code list -------------------------------------------


@pytest.mark.django_db
def test_unknown_programme_is_stored_as_given_reported_and_logged(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        result = import_roster_csv(
            csv_file(HEADER + "230200924,l.p@college.edu,Luna,Department of Wizardry,2027,8.1\n")
        )

    assert result.created == 1
    assert Student.objects.get(prn="230200924").department == "Department of Wizardry"
    assert result.as_dict()["unknown_codes"] == [
        {"row": 2, "prn": "230200924", "field": "department", "value": "Department of Wizardry"}
    ]
    assert any("Department of Wizardry" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
def test_unknown_school_is_stored_as_given_reported_and_logged(caplog):
    import logging

    body = (
        "prn,email,full_name,department,batch,school\n"
        "230200924,l.p@college.edu,Luna,B.Tech Computer Science,2027,School of Wizardry\n"
    )
    with caplog.at_level(logging.WARNING):
        result = import_roster_csv(csv_file(body))

    assert Student.objects.get(prn="230200924").school == "School of Wizardry"
    assert [(c["field"], c["value"]) for c in result.unknown_codes] == [
        ("school", "School of Wizardry")
    ]
    assert any("School of Wizardry" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
def test_known_codes_report_nothing_and_blank_school_is_filled():
    result = import_roster_csv(
        csv_file(HEADER + "230200924,l.p@college.edu,Luna,btech computer science,2027,8.1\n")
    )
    assert result.unknown_codes == []
    assert result.as_dict()["unknown_codes"] == []
    assert Student.objects.get(prn="230200924").school == "computing_data_science"


@pytest.mark.django_db
def test_optional_school_and_year_of_study_columns_are_saved():
    body = (
        "prn,email,full_name,department,batch,school,year_of_study\n"
        "230200924,l.p@college.edu,Luna,MBA,2027,business,3\n"
    )
    result = import_roster_csv(csv_file(body))
    assert result.ok
    student = Student.objects.get(prn="230200924")
    assert (student.school, student.year_of_study) == ("business", 3)


@pytest.mark.django_db
def test_bad_year_of_study_is_a_row_error():
    body = (
        "prn,email,full_name,department,batch,year_of_study\n"
        "230200924,l.p@college.edu,Luna,MBA,2027,third\n"
    )
    result = import_roster_csv(csv_file(body))
    assert result.created == 0
    assert "year_of_study" in result.errors[0].errors
