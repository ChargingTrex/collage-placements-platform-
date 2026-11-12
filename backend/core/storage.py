"""
Upload storage boundary.

Everything that writes a user upload (resumes now, certification proofs in
Phase 5) goes through `upload_path` and `validate_upload` here rather than
touching storage directly. Which backend actually receives the bytes is a
settings concern (STORAGE_BACKEND=local|s3), so moving to an S3-compatible
bucket is a config change, not a code change.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


RESUME_EXTENSIONS = {".pdf", ".docx"}
TRANSCRIPT_EXTENSIONS = {".pdf"}
PROOF_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
#: Marksheets are scanned or photographed far more often than the college's
#: own transcript, so the image types are allowed alongside PDF.
MARKSHEET_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _slugged_name(filename: str) -> str:
    """Randomise the stored name, keep the extension: uploads are untrusted."""
    suffix = Path(filename).suffix.lower()
    return f"{uuid.uuid4().hex}{suffix}"


def upload_path(instance, filename: str) -> str:
    """`upload_to` callable for resume files: resumes/<prn>/<random>.<ext>."""
    prn = getattr(getattr(instance, "student", None), "prn", "unknown")
    return f"resumes/{prn}/{_slugged_name(filename)}"


def transcript_upload_path(instance, filename: str) -> str:
    """`upload_to` callable for transcripts: transcripts/<prn>/<random>.<ext>."""
    prn = getattr(getattr(instance, "student", None), "prn", "unknown")
    return f"transcripts/{prn}/{_slugged_name(filename)}"


def proof_upload_path(instance, filename: str) -> str:
    """`upload_to` callable for certification proofs."""
    prn = getattr(getattr(instance, "student", None), "prn", "unknown")
    return f"proofs/{prn}/{_slugged_name(filename)}"


def marksheet_upload_path(instance, filename: str) -> str:
    """`upload_to` callable for 10th/12th marksheets: marksheets/<prn>/<random>.<ext>."""
    prn = getattr(getattr(instance, "student", None), "prn", "unknown")
    return f"marksheets/{prn}/{_slugged_name(filename)}"


def validate_upload(file_obj, allowed_extensions: set[str] = RESUME_EXTENSIONS) -> None:
    """Reject wrong extensions and oversized files before anything is stored."""
    suffix = Path(file_obj.name).suffix.lower()
    if suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"Unsupported file type '{suffix}'. Allowed: {allowed}.")

    size = getattr(file_obj, "size", None)
    if size is not None and size > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ValidationError(f"File is larger than the {limit_mb:.0f}MB limit.")


def validate_resume(file_obj) -> None:
    validate_upload(file_obj, RESUME_EXTENSIONS)


def validate_transcript(file_obj) -> None:
    # PDF only: the parser reads the text layer, and the size limit is the resume one.
    validate_upload(file_obj, TRANSCRIPT_EXTENSIONS)


def validate_proof(file_obj) -> None:
    validate_upload(file_obj, PROOF_EXTENSIONS)


def validate_marksheet(file_obj) -> None:
    # Images as well as PDF: a school marksheet is usually photographed, not
    # issued as a PDF the way the college's own transcript is.
    validate_upload(file_obj, MARKSHEET_EXTENSIONS)


def storage_info() -> dict[str, str]:
    """Which backend is live -- surfaced by /api/health for smoke tests."""
    backend = settings.STORAGE_BACKEND
    location = (
        settings.AWS_STORAGE_BUCKET_NAME
        if backend == "s3"
        else str(settings.MEDIA_ROOT)
    )
    return {"backend": backend, "location": location}
