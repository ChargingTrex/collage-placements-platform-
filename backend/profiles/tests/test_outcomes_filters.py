"""
`?career_path=` and `?school=` on the admin profile list.

These are what the outcomes dashboard drills on: a bar is clickable, and the
people table under the chart has to come back narrowed to that one path or
school. Both are admin-only, like the rest of that list.
"""

import pytest
from django.urls import reverse

from profiles.models import CareerPath

pytestmark = pytest.mark.django_db


@pytest.fixture
def three_students(make_student):
    """One per career path, across two schools."""
    law = make_student(
        prn="220200901",
        full_name="Aarav Mehta",
        career_path=CareerPath.COMPETITIVE_EXAMS,
    )
    law.student.school = "law"
    law.student.save(update_fields=["school"])

    computing = make_student(
        prn="220200902",
        full_name="Diya Sharma",
        career_path=CareerPath.PLACEMENT,
    )
    computing.student.school = "computing_data_science"
    computing.student.save(update_fields=["school"])

    also_computing = make_student(
        prn="220200903",
        full_name="Rohan Iyer",
        career_path=CareerPath.HIGHER_STUDIES,
    )
    also_computing.student.school = "computing_data_science"
    also_computing.student.save(update_fields=["school"])
    return law, computing, also_computing


def names(response):
    return {row["student"]["full_name"] for row in response.data["results"]}


def test_career_path_filter_returns_only_that_path(admin_client, three_students):
    response = admin_client.get(
        reverse("admin-profile-list"), {"career_path": CareerPath.COMPETITIVE_EXAMS}
    )

    assert response.status_code == 200
    assert names(response) == {"Aarav Mehta"}


def test_school_filter_returns_every_path_in_that_school(admin_client, three_students):
    response = admin_client.get(
        reverse("admin-profile-list"), {"school": "computing_data_science"}
    )

    assert response.status_code == 200
    assert names(response) == {"Diya Sharma", "Rohan Iyer"}


def test_school_filter_ignores_case(admin_client, three_students):
    response = admin_client.get(reverse("admin-profile-list"), {"school": "LAW"})

    assert names(response) == {"Aarav Mehta"}


def test_the_two_filters_combine(admin_client, three_students):
    response = admin_client.get(
        reverse("admin-profile-list"),
        {"school": "computing_data_science", "career_path": CareerPath.PLACEMENT},
    )

    assert names(response) == {"Diya Sharma"}


def test_an_unknown_career_path_is_a_400_not_an_empty_page(admin_client, three_students):
    """A typo must not read as "nobody is on this path"."""
    response = admin_client.get(reverse("admin-profile-list"), {"career_path": "astronaut"})

    assert response.status_code == 400
    assert "career_path" in response.data


def test_search_still_finds_a_student_by_name(admin_client, three_students):
    """The people table's search box, which rides the existing search_fields."""
    response = admin_client.get(reverse("admin-profile-list"), {"search": "Rohan"})

    assert names(response) == {"Rohan Iyer"}


def test_a_company_cannot_use_the_career_path_filter(as_company, three_students):
    """career_path is placement-cell planning data; the company list rejects it."""
    response = as_company.get(
        reverse("company-profile-list"), {"career_path": CareerPath.PLACEMENT}
    )

    assert response.status_code == 400
