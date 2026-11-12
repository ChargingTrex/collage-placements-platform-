"""Resume upload: the Phase 2 engine pre-filling profile fields for review."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog
from matching.samples import SAMPLES_BY_KEY


@pytest.mark.django_db
class TestUpload:
    def test_upload_prefills_experience_and_education_from_the_resume(
        self, as_student, profile, sample_resume_file
    ):
        sample = SAMPLES_BY_KEY["backend_engineer"]

        response = as_student.post(
            reverse("my-resume"), {"file": sample_resume_file()}, format="multipart"
        )

        assert response.status_code == 201
        suggestion = response.json()["suggestion"]
        assert float(suggestion["experience_years"]) == sample.expected_experience_years
        assert suggestion["education_level"] == "UG"
        assert suggestion["applied"] is True

        profile.refresh_from_db()
        assert float(profile.experience_years) == sample.expected_experience_years
        assert profile.education_level == "UG"
        assert profile.resume_filename.endswith(".pdf")
        assert profile.resume_uploaded_at is not None

    def test_a_masters_resume_prefills_the_masters_level(
        self, as_student, profile, sample_resume_file
    ):
        as_student.post(
            reverse("my-resume"),
            {"file": sample_resume_file("data_engineer")},
            format="multipart",
        )

        profile.refresh_from_db()
        assert profile.education_level == "Masters"
        assert float(profile.experience_years) == 2.5

    def test_the_prefilled_values_are_editable_by_the_student(self, as_student, profile, sample_resume_file):
        as_student.post(
            reverse("my-resume"), {"file": sample_resume_file()}, format="multipart"
        )

        response = as_student.post(
            reverse("my-confirm-parsed"),
            {"experience_years": "1.5", "education_level": "UG"},
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert float(profile.experience_years) == 1.5
        assert profile.parsed_values_confirmed is True

    def test_a_later_upload_does_not_overwrite_a_confirmed_correction(
        self, as_student, profile, sample_resume_file
    ):
        """The student's correction is the record; the parser's reading is a
        suggestion, and a re-upload must not quietly undo the correction."""
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")
        as_student.post(
            reverse("my-confirm-parsed"),
            {"experience_years": "1.0", "education_level": "UG"},
            format="json",
        )

        response = as_student.post(
            reverse("my-resume"),
            {"file": sample_resume_file("mechanical_designer")},
            format="multipart",
        )

        assert response.json()["suggestion"]["applied"] is False
        profile.refresh_from_db()
        assert float(profile.experience_years) == 1.0          # kept
        assert float(profile.parsed_experience_years) == 4.0   # new reading recorded
        assert profile.parsed_differs_from_confirmed is True

    def test_the_parsed_text_is_stored_for_later_matching(
        self, as_student, profile, sample_resume_file
    ):
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        profile.refresh_from_db()
        assert "Django REST Framework" in profile.resume_text

    def test_upload_is_audit_logged(self, as_student, profile, sample_resume_file):
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        entry = AuditLog.objects.get(action=AuditLog.Action.RESUME_PARSED)
        assert entry.target == profile.prn
        assert entry.detail["experience_years"] == 3.0

    def test_the_stored_filename_is_randomised(self, as_student, profile, sample_resume_file):
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        profile.refresh_from_db()
        assert profile.prn in profile.resume.name
        # The display name is kept, the stored path is not the user's name.
        assert "aarav_mehta_backend" not in profile.resume.name
        assert profile.resume_filename == "aarav_mehta_backend.pdf"


@pytest.mark.django_db
class TestUploadRejections:
    def test_a_wrong_file_type_is_rejected(self, as_student):
        response = as_student.post(
            reverse("my-resume"),
            {"file": SimpleUploadedFile("resume.txt", b"plain text")},
            format="multipart",
        )

        assert response.status_code == 400
        assert "Unsupported file type" in str(response.json())

    def test_an_unreadable_file_is_rejected_without_replacing_the_stored_one(
        self, as_student, profile, sample_resume_file
    ):
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")
        profile.refresh_from_db()
        original = profile.resume.name

        response = as_student.post(
            reverse("my-resume"),
            {"file": SimpleUploadedFile("broken.pdf", b"not really a pdf")},
            format="multipart",
        )

        assert response.status_code == 400
        profile.refresh_from_db()
        assert profile.resume.name == original

    def test_an_oversized_file_is_rejected(self, as_student, settings):
        settings.MAX_UPLOAD_BYTES = 100

        response = as_student.post(
            reverse("my-resume"),
            {"file": SimpleUploadedFile("resume.pdf", b"x" * 500)},
            format="multipart",
        )

        assert response.status_code == 400
        assert "larger than" in str(response.json())

    def test_a_company_cannot_upload_a_resume(self, as_company, sample_resume_file):
        response = as_company.post(
            reverse("my-resume"), {"file": sample_resume_file()}, format="multipart"
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestRemoval:
    def test_deleting_the_resume_clears_the_parsed_values(
        self, as_student, profile, sample_resume_file
    ):
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        response = as_student.delete(reverse("my-resume"))

        assert response.status_code == 204
        profile.refresh_from_db()
        assert not profile.resume
        assert profile.resume_text == ""
        assert profile.parsed_experience_years is None
