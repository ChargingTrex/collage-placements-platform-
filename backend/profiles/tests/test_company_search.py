"""Company-facing search: the PRD's filter set over visible profiles."""

import pytest
from django.urls import reverse

from profiles.models import ProfileSkill, ProjectEntry, Visibility


@pytest.fixture
def population(make_student):
    """Four visible profiles with distinct departments, CGPAs and skills."""
    people = {
        "aarav": make_student(
            prn="220200901", full_name="Aarav Mehta",
            department="Computer Engineering", cgpa="8.72",
            headline="Backend developer", experience_years="3.0", education_level="UG",
        ),
        "diya": make_student(
            prn="220200902", full_name="Diya Sharma",
            department="Computer Engineering", cgpa="9.10",
            headline="ML engineer", experience_years="1.0", education_level="UG",
        ),
        "sana": make_student(
            prn="220200904", full_name="Sana Qureshi",
            department="Information Technology", cgpa="8.05",
            headline="Data engineer", experience_years="2.5", education_level="Masters",
        ),
        "arjun": make_student(
            prn="220200909", full_name="Arjun Deshmukh",
            department="Mechanical", cgpa="6.95",
            headline="Design engineer", experience_years="4.0", education_level="UG",
        ),
    }
    skills = {
        "aarav": ["Python", "Django", "PostgreSQL"],
        "diya": ["Python", "TensorFlow"],
        "sana": ["Python", "SQL", "Airflow"],
        "arjun": ["SolidWorks", "AutoCAD"],
    }
    for key, names in skills.items():
        for name in names:
            ProfileSkill.objects.create(profile=people[key], name=name)

    ProjectEntry.objects.create(
        profile=people["aarav"], title="Fleet tracker",
        description="Realtime vehicle dashboard.", tech_stack=["Django", "React"],
    )
    ProjectEntry.objects.create(
        profile=people["arjun"], title="Suspension bracket",
        description="Lightweight bracket redesign.", tech_stack=["SolidWorks"],
    )
    return people


def prns(response) -> set[str]:
    return {row["prn"] for row in response.json()["results"]}


@pytest.mark.django_db
class TestFilters:
    def test_department(self, as_company, population):
        response = as_company.get(
            reverse("company-profile-list"), {"department": "Computer Engineering"}
        )

        assert prns(response) == {"220200901", "220200902"}

    def test_department_is_case_insensitive(self, as_company, population):
        response = as_company.get(
            reverse("company-profile-list"), {"department": "computer engineering"}
        )

        assert len(response.json()["results"]) == 2

    def test_cgpa_range(self, as_company, population):
        response = as_company.get(
            reverse("company-profile-list"), {"cgpa_min": "8.0", "cgpa_max": "9.0"}
        )

        assert prns(response) == {"220200901", "220200904"}

    def test_a_single_skill(self, as_company, population):
        response = as_company.get(reverse("company-profile-list"), {"skills": "django"})

        assert prns(response) == {"220200901"}

    def test_several_skills_are_combined_with_and(self, as_company, population):
        """Asking for Python AND Django must not return somebody with only Python."""
        response = as_company.get(
            reverse("company-profile-list"), {"skills": "python,django"}
        )

        assert prns(response) == {"220200901"}

    def test_skill_matching_ignores_punctuation_and_case(self, as_company, population, make_student):
        node_person = make_student(prn="230200906", full_name="Ananya Rao")
        ProfileSkill.objects.create(profile=node_person, name="Node.js")

        response = as_company.get(reverse("company-profile-list"), {"skills": "nodejs"})

        assert prns(response) == {"230200906"}

    def test_project_keyword_searches_titles_descriptions_and_stack(
        self, as_company, population
    ):
        by_title = as_company.get(
            reverse("company-profile-list"), {"project_keyword": "fleet"}
        )
        by_stack = as_company.get(
            reverse("company-profile-list"), {"project_keyword": "React"}
        )

        assert prns(by_title) == {"220200901"}
        assert prns(by_stack) == {"220200901"}

    def test_minimum_experience(self, as_company, population):
        response = as_company.get(
            reverse("company-profile-list"), {"min_experience_years": "2.5"}
        )

        assert prns(response) == {"220200901", "220200904", "220200909"}

    def test_education_level(self, as_company, population):
        response = as_company.get(
            reverse("company-profile-list"), {"education_level": "Masters"}
        )

        assert prns(response) == {"220200904"}

    def test_filters_combine(self, as_company, population):
        response = as_company.get(
            reverse("company-profile-list"),
            {"department": "Computer Engineering", "skills": "python", "cgpa_min": "9.0"},
        )

        assert prns(response) == {"220200902"}

    def test_free_text_search_covers_name_and_headline(self, as_company, population):
        by_name = as_company.get(reverse("company-profile-list"), {"search": "Qureshi"})
        by_headline = as_company.get(reverse("company-profile-list"), {"search": "Backend"})

        assert prns(by_name) == {"220200904"}
        assert prns(by_headline) == {"220200901"}

    def test_verified_filter(self, as_company, population, admin_user):
        population["aarav"].mark_verified(admin_user)

        response = as_company.get(reverse("company-profile-list"), {"verified": "true"})

        assert prns(response) == {"220200901"}


@pytest.mark.django_db
class TestFiltersRespectVisibility:
    def test_a_hidden_profile_is_excluded_from_every_filter(
        self, as_company, population
    ):
        population["aarav"].visibility = Visibility.HIDDEN
        population["aarav"].save()

        by_department = as_company.get(
            reverse("company-profile-list"), {"department": "Computer Engineering"}
        )
        by_skill = as_company.get(reverse("company-profile-list"), {"skills": "django"})
        by_project = as_company.get(
            reverse("company-profile-list"), {"project_keyword": "fleet"}
        )

        assert "220200901" not in prns(by_department)
        assert prns(by_skill) == set()
        assert prns(by_project) == set()

    def test_a_filter_never_returns_more_than_the_visible_set(self, as_company, population):
        for profile in population.values():
            profile.visibility = Visibility.HIDDEN
            profile.save()

        response = as_company.get(reverse("company-profile-list"), {"cgpa_min": "0"})

        assert response.json()["count"] == 0


@pytest.mark.django_db
class TestResultShape:
    def test_a_profile_appears_once_even_when_several_skills_match(
        self, as_company, population
    ):
        response = as_company.get(reverse("company-profile-list"), {"skills": "python"})
        returned = [row["prn"] for row in response.json()["results"]]

        assert len(returned) == len(set(returned))

    def test_verified_profiles_are_listed_first(self, as_company, population, admin_user):
        population["arjun"].mark_verified(admin_user)  # lowest CGPA of the four

        response = as_company.get(reverse("company-profile-list"))

        assert response.json()["results"][0]["prn"] == "220200909"

    def test_each_row_carries_skills_experience_and_projects(self, as_company, population):
        response = as_company.get(reverse("company-profile-list"), {"skills": "django"})
        row = response.json()["results"][0]

        assert {skill["name"] for skill in row["skills"]} == {"Python", "Django", "PostgreSQL"}
        assert row["projects"][0]["title"] == "Fleet tracker"
        assert row["experience_years"] == "3.0"
