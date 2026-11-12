"""
Fixtures for the checkpoint gates.

Separate from the root `conftest.py` on purpose. The root fixtures are shared
with every module's suite and still carry the invented `PRN2022CS001` shape;
rewriting them is A5's stream A-5. These fixtures use the real nine-digit PRN
(D4) because a checkpoint gate must assert the target state, not the state the
existing fixtures happen to describe.

Nine-digit PRNs are accepted by the current validator as well as by the
`^[0-9]{9}$` one that replaces it, so nothing here depends on which has landed.
"""

from __future__ import annotations

import json

import pytest

#: Three roster rows, which is the size the silent-ignore bug was measured on
#: (IMPLEMENTATION_PLAN.md §3.5, 2026-09-30). A filter that returns three when
#: it should return one is only visibly wrong against a known-size table.
ROSTER = (
    ("220200921", "anaya.krishnan@college.edu", "Anaya Krishnan",
     "B.Tech Computer Science", 2026, "8.72"),
    ("220200922", "kabir.rao@college.edu", "Kabir Rao",
     "B.Tech Data Science", 2026, "7.90"),
    ("230200923", "meera.iyer@college.edu", "Meera Iyer",
     "B.A. (Hons.) Economics", 2027, "9.10"),
)

#: A PRN that is nine digits, valid in shape, and on no roster row. The
#: fail-open bug returns the whole table for it.
ABSENT_PRN = "999999999"


def token_for(user) -> str:
    """The access token the portal itself mints for this user."""
    from accounts.serializers import tokens_for

    return tokens_for(user)["access"]


def client_for(user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_for(user)}")
    return client


def claims_in(token: str) -> dict:
    """
    Decode a token without verifying it.

    A contract test asks what the token *says*; whether the signature holds is
    a separate question with its own gate (checkbox 7).
    """
    import jwt

    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
    )


def body_without_results(response) -> str:
    """
    Everything a list response says apart from the rows themselves.

    Used to ask whether a batch lookup *named* the PRNs it could not find,
    without depending on which key A1 chooses to name them under.
    """
    payload = response.json()
    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k != "results"}
    return json.dumps(payload, default=str)


@pytest.fixture
def roster(db):
    """The three-row roster the fail-open bug was measured against."""
    from roster.models import Student

    rows = []
    for prn, email, full_name, department, batch, cgpa in ROSTER:
        rows.append(
            Student.objects.create(
                prn=prn,
                email=email,
                full_name=full_name,
                department=department,
                batch=batch,
                cgpa=cgpa,
            )
        )
    return rows


@pytest.fixture
def make_account(db):
    """A verified account for one roster row, with its profile."""
    from accounts.models import Role, User
    from profiles.models import StudentProfile

    def _make(student):
        user = User.objects.create_user(
            email=student.email,
            password="StudentPass!234",
            role=Role.STUDENT,
            prn=student.prn,
            full_name=student.full_name,
        )
        user.mark_verified()
        return StudentProfile.objects.create(user=user, student=student)

    return _make


@pytest.fixture
def profiles(roster, make_account):
    """A full profile for each of the three roster rows."""
    return [make_account(student) for student in roster]


@pytest.fixture
def placement_admin(db):
    from accounts.models import User

    return User.objects.create_admin(
        email="placement.officer@college.edu",
        password="AdminPass!234",
        full_name="Priya Kulkarni",
    )


@pytest.fixture
def recruiter(db):
    from accounts.models import User

    return User.objects.create_company(
        email="careers@acmetech.example",
        password="CompanyPass!234",
        full_name="Acme Tech",
    )


@pytest.fixture
def second_recruiter(db):
    """
    A second login at the *same* company as `recruiter`.

    Which is the whole point of checkbox 20: until `Company` is an entity there
    is no way to say "same company", so this fixture can only state the
    intention and let the gate fail.
    """
    from accounts.models import User

    return User.objects.create_company(
        email="hiring@acmetech.example",
        password="CompanyPass!234",
        full_name="Acme Tech",
    )


@pytest.fixture
def as_admin(placement_admin):
    return client_for(placement_admin)


@pytest.fixture
def as_recruiter(recruiter):
    return client_for(recruiter)


@pytest.fixture
def as_second_recruiter(second_recruiter):
    return client_for(second_recruiter)
