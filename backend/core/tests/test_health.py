"""Phase 0 smoke test: the health endpoint and the storage boundary."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.storage import upload_path, validate_resume


@pytest.mark.django_db
def test_health_returns_ok_with_database_and_storage_checks(api_client):
    response = api_client.get(reverse("health"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "placement-cell-portal"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["storage"]["ok"] is True
    # Whichever similarity backend is live, health must name it.
    assert body["checks"]["matching_engine"]["backend"] in {"spacy", "tfidf"}


@pytest.mark.django_db
def test_health_is_reachable_without_authentication(api_client):
    """Container orchestrators probe this endpoint with no credentials."""
    assert api_client.get("/api/health").status_code == 200


def test_validate_resume_rejects_unsupported_extension():
    bad = SimpleUploadedFile("resume.txt", b"plain text", content_type="text/plain")
    with pytest.raises(ValidationError, match="Unsupported file type"):
        validate_resume(bad)


def test_validate_resume_rejects_oversized_file(settings):
    settings.MAX_UPLOAD_BYTES = 10
    big = SimpleUploadedFile("resume.pdf", b"x" * 50, content_type="application/pdf")
    with pytest.raises(ValidationError, match="larger than"):
        validate_resume(big)


def test_validate_resume_accepts_pdf_and_docx():
    validate_resume(SimpleUploadedFile("cv.pdf", b"%PDF-1.4"))
    validate_resume(SimpleUploadedFile("cv.DOCX", b"PK"))


def test_upload_path_randomises_filename_and_keeps_extension():
    class FakeStudent:
        prn = "220200901"

    class FakeResume:
        student = FakeStudent()

    path = upload_path(FakeResume(), "My Resume (final).pdf")

    assert path.startswith("resumes/220200901/")
    assert path.endswith(".pdf")
    assert "My Resume" not in path  # user-supplied name never reaches storage
