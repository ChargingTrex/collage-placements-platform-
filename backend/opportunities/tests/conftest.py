"""
Fixtures for the opportunity tests: the matching-cache reset (as in
profiles/tests/conftest.py) plus builders. Synthetic people only, PRNs
220200990-999.
"""

import datetime

import pytest
from django.core.files.base import ContentFile


@pytest.fixture(autouse=True)
def _fresh_matching_caches(settings):
    """
    The skill graph and vector store are cached per process, and a test's
    rollback fires no signal, so either would leak between tests. The local
    store is pinned so a developer's MONGO_URI never receives test vectors.
    """
    from matching.skills import reset_skill_graph
    from matching.vectorstore import reset_vector_store

    settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "local"}
    reset_skill_graph()
    reset_vector_store()
    yield
    reset_skill_graph()
    reset_vector_store()


def client_for(user):
    from accounts.serializers import tokens_for
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(user)['access']}")
    return client


@pytest.fixture
def nimbus(db):
    from accounts.models import Company

    return Company.objects.create(name="Nimbus Analytics", email="careers@nimbus.example")


@pytest.fixture
def nimbus_user(db, nimbus):
    from accounts.models import User

    return User.objects.create_company(
        email="talent@nimbus.example", password="CompanyPass!234",
        full_name="Dev Menon", company=nimbus,
    )


@pytest.fixture
def as_nimbus(nimbus_user):
    return client_for(nimbus_user)


@pytest.fixture
def lonely_recruiter(db):
    """A recruiter login with no company: every company action is a 403."""
    from accounts.models import User

    return User.objects.create_company(
        email="nocompany@example.test", password="CompanyPass!234", full_name="No Company",
    )


@pytest.fixture
def make_opportunity(db, company, admin_user):
    from opportunities.models import Opportunity

    def _make(**fields):
        defaults = dict(
            company=company,
            title="Backend Engineer",
            description=(
                "Build REST APIs with Python and Django on PostgreSQL. "
                "Docker and Git are used daily."
            ),
            role_type="full_time",
            required_skills=["python", "django"],
            deadline=datetime.date.today() + datetime.timedelta(days=14),
            status="open",
            created_by=admin_user,
        )
        defaults.update(fields)
        return Opportunity.objects.create(**defaults)

    return _make


BACKEND_RESUME = (
    "Backend developer. Built REST APIs in Python and Django on PostgreSQL, "
    "deployed with Docker. 2 years of experience. B.Tech Computer Science."
)
CHEF_RESUME = "Pastry chef. Baked bread, managed a kitchen and plated desserts."


@pytest.fixture
def make_applicant(make_student):
    """A verified roster student whose profile has a resume file and its text."""

    def _make(prn="220200990", resume_text=BACKEND_RESUME, skills=("Python", "Django"), **kw):
        from profiles.models import ProfileSkill

        profile = make_student(prn=prn, full_name=kw.pop("full_name", f"Student {prn}"), **kw)
        if resume_text is not None:
            profile.resume.save("resume.pdf", ContentFile(b"%PDF-1.4 fake " + prn.encode()), save=False)
            profile.resume_filename = "resume.pdf"
            profile.resume_text = resume_text
            profile.save()
        for name in skills:
            ProfileSkill.objects.create(profile=profile, name=name)
        return profile

    return _make


@pytest.fixture
def student_a(make_applicant):
    return make_applicant("220200990", full_name="Test Student A")


@pytest.fixture
def student_b(make_applicant):
    return make_applicant(
        "220200991", full_name="Test Student B", resume_text=CHEF_RESUME,
        skills=("Baking",), department="Information Technology", cgpa="6.50",
    )


@pytest.fixture
def as_a(student_a):
    return client_for(student_a.user)


@pytest.fixture
def as_b(student_b):
    return client_for(student_b.user)
