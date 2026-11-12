"""Shared pytest fixtures.

Tests always run against the locmem email backend and a per-test media
directory, regardless of what the developer's .env points at.
"""

import os

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


@pytest.fixture(autouse=True)
def _isolated_media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    return settings.MEDIA_ROOT


@pytest.fixture(autouse=True)
def _reset_throttles():
    """DRF throttle history is process-global; leaking it across tests makes
    unrelated tests fail with 429 depending on run order."""
    from rest_framework.throttling import SimpleRateThrottle

    SimpleRateThrottle.cache.clear()
    yield
    SimpleRateThrottle.cache.clear()


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def roster_student(db):
    """One eligible roster row -- the happy path for every signup test."""
    from roster.models import Student

    return Student.objects.create(
        prn="220200901",
        email="aarav.mehta@college.edu",
        full_name="Aarav Mehta",
        department="Computer Engineering",
        batch=2026,
        cgpa="8.72",
    )


@pytest.fixture
def admin_user(db):
    from accounts.models import User

    return User.objects.create_admin(
        email="placement.officer@college.edu",
        password="AdminPass!234",
        full_name="Priya Kulkarni",
    )


@pytest.fixture
def company(db):
    """The organisation. Shortlists and opportunities belong to this."""
    from accounts.models import Company

    return Company.objects.create(name="Acme Tech", email="careers@acmetech.example")


@pytest.fixture
def company_user(db, company):
    """A recruiter login belonging to that organisation."""
    from accounts.models import User

    return User.objects.create_company(
        email="recruiter@acmetech.example",
        password="CompanyPass!234",
        full_name="Priya Raman",
        company=company,
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    from accounts.serializers import tokens_for

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(admin_user)['access']}")
    return api_client


@pytest.fixture
def verified_student(db, roster_student):
    """A roster student who has completed signup and can log in."""
    from accounts.models import Role, User

    user = User.objects.create_user(
        email=roster_student.email,
        password="StudentPass!234",
        role=Role.STUDENT,
        prn=roster_student.prn,
        full_name=roster_student.full_name,
    )
    user.mark_verified()
    return user


@pytest.fixture
def student_client(api_client, verified_student):
    from accounts.serializers import tokens_for

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {tokens_for(verified_student)['access']}"
    )
    return api_client


# --- Phase 3: profile fixtures ---------------------------------------------


@pytest.fixture
def make_student(db):
    """Build a roster row plus a verified account and an empty profile."""
    from accounts.models import Role, User
    from profiles.models import StudentProfile
    from roster.models import Student

    def _make(
        prn="220200901",
        email=None,
        full_name="Aarav Mehta",
        department="Computer Engineering",
        batch=2026,
        cgpa="8.72",
        **profile_fields,
    ):
        email = email or f"{prn.lower()}@college.edu"
        student = Student.objects.create(
            prn=prn,
            email=email,
            full_name=full_name,
            department=department,
            batch=batch,
            cgpa=cgpa,
        )
        user = User.objects.create_user(
            email=email, password="StudentPass!234", role=Role.STUDENT, prn=student.prn,
            full_name=full_name,
        )
        user.mark_verified()
        profile = StudentProfile.objects.create(user=user, student=student, **profile_fields)
        return profile

    return _make


@pytest.fixture
def profile(make_student):
    return make_student()


@pytest.fixture
def other_profile(make_student):
    return make_student(
        prn="220200904", full_name="Sana Qureshi", department="Information Technology",
        cgpa="8.05",
    )


def _client_for(user):
    from accounts.serializers import tokens_for
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(user)['access']}")
    return client


@pytest.fixture
def as_student(profile):
    return _client_for(profile.user)


@pytest.fixture
def as_other_student(other_profile):
    return _client_for(other_profile.user)


@pytest.fixture
def as_company(company_user):
    return _client_for(company_user)


@pytest.fixture
def as_admin(admin_user):
    return _client_for(admin_user)


@pytest.fixture
def sample_resume_file():
    """A real PDF resume with known content, as an upload."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from matching.management.commands.make_sample_resumes import write_pdf
    from matching.samples import SAMPLES_BY_KEY

    def _make(key="backend_engineer", tmp_dir=None):
        import tempfile
        from pathlib import Path

        sample = SAMPLES_BY_KEY[key]
        directory = Path(tmp_dir or tempfile.mkdtemp())
        path = directory / f"{key}.pdf"
        write_pdf(path, list(sample.lines))
        return SimpleUploadedFile(
            sample.filename.replace(".docx", ".pdf"),
            path.read_bytes(),
            content_type="application/pdf",
        )

    return _make
