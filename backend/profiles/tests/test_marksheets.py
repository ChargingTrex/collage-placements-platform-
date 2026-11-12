"""
10th and 12th marksheets: the file, the marks beside it, and who may see them.

The file and the marks are deliberately separate: the file moves through its
own endpoint, the marks are self-reported and ride the ordinary profile PATCH.
Neither is placement data a company ever sees.
"""

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from profiles.models import StudentProfile

pytestmark = pytest.mark.django_db

LEVELS = ("10", "12")


def marksheet(name="marksheet.pdf", content=b"%PDF-1.4 marksheet"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def upload(client, level, file=None):
    return client.post(
        reverse("my-marksheet", args=[level]), {"file": file or marksheet()}, format="multipart"
    )


class TestUpload:
    @pytest.mark.parametrize("level", LEVELS)
    def test_a_student_uploads_each_level(self, as_student, profile, level):
        response = upload(as_student, level)

        assert response.status_code == 201
        profile.refresh_from_db()
        assert getattr(profile, f"marksheet_{level}")
        assert getattr(profile, f"marksheet_{level}_filename") == "marksheet.pdf"
        assert getattr(profile, f"marksheet_{level}_uploaded_at") is not None

    @pytest.mark.parametrize("level", LEVELS)
    def test_the_payload_carries_a_url_to_the_students_own_route(self, as_student, level):
        body = upload(as_student, level).json()

        assert body[f"marksheet_{level}_url"] == reverse("my-marksheet-file", args=[level])

    def test_the_two_levels_are_independent(self, as_student, profile):
        upload(as_student, "10")
        profile.refresh_from_db()

        assert profile.marksheet_10
        assert not profile.marksheet_12

    def test_the_stored_name_is_randomised_under_the_prn(self, as_student, profile):
        upload(as_student, "10")
        profile.refresh_from_db()

        assert profile.prn in profile.marksheet_10.name
        assert "marksheet.pdf" not in profile.marksheet_10.name

    def test_a_photographed_marksheet_is_accepted(self, as_student):
        """Most school marksheets are photographed, not issued as PDF."""
        response = upload(as_student, "10", marksheet("marks.jpg", b"\xff\xd8\xff photo"))

        assert response.status_code == 201

    def test_replacing_one_removes_the_previous_file(self, as_student, profile):
        upload(as_student, "10")
        profile.refresh_from_db()
        first = profile.marksheet_10.name

        upload(as_student, "10", marksheet("newer.pdf"))
        profile.refresh_from_db()

        assert profile.marksheet_10.name != first
        assert not profile.marksheet_10.storage.exists(first)

    @pytest.mark.parametrize("level", LEVELS)
    def test_a_student_removes_their_own_marksheet(self, as_student, profile, level):
        upload(as_student, level)

        response = as_student.delete(reverse("my-marksheet", args=[level]))

        assert response.status_code == 200
        profile.refresh_from_db()
        assert not getattr(profile, f"marksheet_{level}")
        assert getattr(profile, f"marksheet_{level}_filename") == ""


class TestUploadRejections:
    def test_an_unsupported_type_is_refused(self, as_student):
        response = upload(as_student, "10", marksheet("notes.docx", b"PK zip"))

        assert response.status_code == 400
        assert "Unsupported file type" in str(response.json())

    def test_an_oversized_file_is_refused(self, as_student, settings):
        settings.MAX_UPLOAD_BYTES = 100

        response = upload(as_student, "10", marksheet("big.pdf", b"x" * 500))

        assert response.status_code == 400
        assert "larger than" in str(response.json())

    def test_an_unknown_level_is_not_a_route(self, as_student):
        response = as_student.post("/api/profiles/me/marksheet/11", {}, format="multipart")

        assert response.status_code == 404

    def test_a_company_cannot_upload(self, as_company):
        response = upload(as_company, "10")

        assert response.status_code == 403


class TestMarks:
    """The marks are an ordinary self-reported profile field."""

    def test_a_student_states_their_marks(self, as_student, profile):
        response = as_student.patch(
            reverse("my-profile"),
            {
                "marks_10_percentage": "92.40",
                "marks_10_board": "cbse",
                "marks_10_year": 2020,
                "marks_12_percentage": "88.60",
                "marks_12_board": "state",
                "marks_12_year": 2022,
            },
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert str(profile.marks_10_percentage) == "92.40"
        assert profile.marks_10_board == "cbse"
        assert profile.marks_10_year == 2020
        assert str(profile.marks_12_percentage) == "88.60"

    def test_marks_need_no_marksheet_file(self, as_student, profile):
        """Stating marks and attaching the proof are two separate steps."""
        as_student.patch(
            reverse("my-profile"), {"marks_10_percentage": "75.00"}, format="json"
        )

        profile.refresh_from_db()
        assert str(profile.marks_10_percentage) == "75.00"
        assert not profile.marksheet_10

    @pytest.mark.parametrize("value", ["-1.00", "100.01", "250.00"])
    def test_an_impossible_percentage_is_refused(self, as_student, value):
        response = as_student.patch(
            reverse("my-profile"), {"marks_10_percentage": value}, format="json"
        )

        assert response.status_code == 400
        assert "marks_10_percentage" in response.json()

    def test_an_unknown_board_is_refused(self, as_student):
        response = as_student.patch(
            reverse("my-profile"), {"marks_10_board": "hogwarts"}, format="json"
        )

        assert response.status_code == 400

    def test_the_file_fields_are_not_writable_through_the_profile(self, as_student, profile):
        """A filename is set by uploading, never by claiming one."""
        as_student.patch(
            reverse("my-profile"), {"marksheet_10_filename": "forged.pdf"}, format="json"
        )

        profile.refresh_from_db()
        assert profile.marksheet_10_filename == ""


class TestWhoCanRead:
    def test_a_student_reopens_their_own(self, as_student):
        upload(as_student, "10")

        response = as_student.get(reverse("my-marksheet-file", args=["10"]))

        assert response.status_code == 200

    def test_no_marksheet_is_a_404_not_an_empty_file(self, as_student):
        response = as_student.get(reverse("my-marksheet-file", args=["12"]))

        assert response.status_code == 404

    def test_an_admin_open_is_audited(self, as_student, admin_client, profile):
        from core.models import AuditLog

        upload(as_student, "10")

        response = admin_client.get(
            reverse("admin-profile-marksheet", args=[profile.student_id, "10"])
        )

        assert response.status_code == 200
        assert AuditLog.objects.filter(
            action=AuditLog.Action.DOCUMENT_ACCESSED, target=profile.prn
        ).exists()

    def test_a_company_has_no_marksheet_route(self, as_student, as_company, profile):
        """Companies never see school marksheets, as they never see transcripts."""
        upload(as_student, "10")

        response = as_company.get(
            f"/api/profiles/students/{profile.student_id}/marksheet/10"
        )

        assert response.status_code == 404


class TestCompanyPayloadIsClean:
    """Marksheets and the student's CGPA are placement-cell data."""

    FORBIDDEN = {
        "marksheet_10",
        "marksheet_10_url",
        "marksheet_10_filename",
        "marks_10_percentage",
        "marks_10_board",
        "marks_10_year",
        "marksheet_12",
        "marksheet_12_url",
        "marks_12_percentage",
        "confirmed_cgpa",
        "parsed_cgpa",
        "recomputed_cgpa",
        "cgpa_sources",
    }

    def all_keys(self, value):
        if isinstance(value, dict):
            for key, inner in value.items():
                yield key
                yield from self.all_keys(inner)
        elif isinstance(value, list):
            for item in value:
                yield from self.all_keys(item)

    def test_the_company_list_carries_no_marksheet_or_cgpa_field(
        self, as_student, as_company, profile
    ):
        upload(as_student, "10")
        as_student.patch(
            reverse("my-profile"),
            {"marks_10_percentage": "92.40", "marks_10_board": "cbse"},
            format="json",
        )
        StudentProfile.objects.filter(pk=profile.pk).update(confirmed_cgpa="9.41")

        body = as_company.get(reverse("company-profile-list")).json()

        assert not self.FORBIDDEN & set(self.all_keys(body))
        # And no value leaks under a differently-spelled key.
        assert "92.40" not in json.dumps(body)
        assert "9.41" not in json.dumps(body)
