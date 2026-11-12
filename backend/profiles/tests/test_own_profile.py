"""The student's own profile: editing, children, resume upload and pre-fill."""

import pytest
from django.urls import reverse

from profiles.models import ExperienceEntry, ProfileSkill, ProjectEntry


@pytest.mark.django_db
class TestReadAndEdit:
    def test_a_student_sees_their_roster_facts_and_an_empty_profile(self, as_student, profile):
        response = as_student.get(reverse("my-profile"))

        assert response.status_code == 200
        body = response.json()
        assert body["student"]["prn"] == profile.prn
        assert body["student"]["department"] == "Computer Engineering"
        assert body["student"]["cgpa"] == "8.72"
        assert body["completion_percent"] == 0
        assert body["is_verified"] is False

    def test_a_student_edits_their_own_fields(self, as_student):
        response = as_student.patch(
            reverse("my-profile"),
            {"headline": "Backend developer", "summary": "I build APIs.",
             "github_url": "https://github.com/aarav"},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["headline"] == "Backend developer"
        assert response.json()["completion_percent"] > 0

    def test_roster_facts_cannot_be_edited_through_the_profile(self, as_student, profile):
        as_student.patch(
            reverse("my-profile"),
            {"student": {"cgpa": "10.00", "department": "Astrophysics"}},
            format="json",
        )

        profile.student.refresh_from_db()
        assert str(profile.student.cgpa) == "8.72"
        assert profile.student.department == "Computer Engineering"

    def test_verification_cannot_be_set_by_the_student(self, as_student, profile):
        as_student.patch(reverse("my-profile"), {"is_verified": True}, format="json")

        profile.refresh_from_db()
        assert profile.is_verified is False

    def test_completion_detail_names_what_is_still_missing(self, as_student):
        response = as_student.get(reverse("my-profile"))

        detail = response.json()["completion_detail"]
        assert detail["headline"] is False
        assert set(detail) == {
            "headline", "summary", "skills", "experience", "projects", "resume", "links",
            "career_path",
        }

    def test_only_students_have_a_profile_endpoint(self, as_company, as_admin):
        assert as_company.get(reverse("my-profile")).status_code == 403
        assert as_admin.get(reverse("my-profile")).status_code == 403


@pytest.mark.django_db
class TestExperienceEntries:
    def test_create_read_update_delete(self, as_student, profile):
        created = as_student.post(
            reverse("my-experience-list"),
            {
                "role": "Backend Intern",
                "organization": "Loadstar Logistics",
                "kind": "internship",
                "start_date": "2025-05-01",
                "end_date": "2025-07-31",
                "description": "Built Django REST APIs.",
                "skills_used": ["Python", "Django", "PostgreSQL"],
            },
            format="json",
        )
        assert created.status_code == 201
        entry_id = created.json()["id"]
        assert created.json()["duration_months"] == 2
        assert created.json()["is_current"] is False

        listed = as_student.get(reverse("my-experience-list"))
        assert listed.json()["count"] == 1

        updated = as_student.patch(
            reverse("my-experience-detail", args=[entry_id]),
            {"role": "Backend Engineering Intern"},
            format="json",
        )
        assert updated.status_code == 200
        assert updated.json()["role"] == "Backend Engineering Intern"

        deleted = as_student.delete(reverse("my-experience-detail", args=[entry_id]))
        assert deleted.status_code == 204
        assert not ExperienceEntry.objects.filter(id=entry_id).exists()

    def test_an_open_ended_entry_is_current(self, as_student):
        response = as_student.post(
            reverse("my-experience-list"),
            {"role": "Volunteer", "organization": "Robotics Club", "kind": "volunteer",
             "start_date": "2025-01-01"},
            format="json",
        )

        assert response.json()["is_current"] is True

    def test_an_end_date_before_the_start_date_is_rejected(self, as_student):
        response = as_student.post(
            reverse("my-experience-list"),
            {"role": "Intern", "organization": "Acme", "start_date": "2025-07-01",
             "end_date": "2025-05-01"},
            format="json",
        )

        assert response.status_code == 400
        assert "end_date" in response.json()

    def test_skills_used_are_trimmed_and_deduplicated(self, as_student):
        response = as_student.post(
            reverse("my-experience-list"),
            {"role": "Intern", "organization": "Acme", "start_date": "2025-05-01",
             "skills_used": [" Python ", "python", "Django", ""]},
            format="json",
        )

        assert response.json()["skills_used"] == ["Python", "Django"]


@pytest.mark.django_db
class TestProjectEntries:
    def test_create_with_tech_stack_and_links(self, as_student):
        response = as_student.post(
            reverse("my-projects-list"),
            {
                "title": "Fleet tracker",
                "description": "Realtime vehicle tracking dashboard.",
                "tech_stack": ["Django", "PostgreSQL", "React"],
                "role": "Backend lead",
                "team_size": 4,
                "repo_url": "https://github.com/aarav/fleet-tracker",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.json()["tech_stack"] == ["Django", "PostgreSQL", "React"]

    def test_a_malformed_link_is_rejected(self, as_student):
        response = as_student.post(
            reverse("my-projects-list"),
            {"title": "Thing", "repo_url": "not-a-url"},
            format="json",
        )

        assert response.status_code == 400
        assert "repo_url" in response.json()

    def test_delete_removes_the_project(self, as_student, profile):
        created = as_student.post(
            reverse("my-projects-list"), {"title": "Fleet tracker"}, format="json"
        )

        as_student.delete(reverse("my-projects-detail", args=[created.json()["id"]]))

        assert not ProjectEntry.objects.filter(profile=profile).exists()


@pytest.mark.django_db
class TestSkills:
    def test_skills_are_slugged_for_filtering(self, as_student):
        response = as_student.post(
            reverse("my-skills-list"), {"name": "Node.js", "category": "technical"},
            format="json",
        )

        assert response.status_code == 201
        assert response.json()["slug"] == "nodejs"

    def test_adding_the_same_skill_twice_is_not_an_error(self, as_student, profile):
        first = as_student.post(reverse("my-skills-list"), {"name": "Python"}, format="json")
        second = as_student.post(reverse("my-skills-list"), {"name": "python"}, format="json")

        assert (first.status_code, second.status_code) == (201, 200)
        assert ProfileSkill.objects.filter(profile=profile).count() == 1

    def test_an_empty_skill_name_is_rejected(self, as_student):
        response = as_student.post(reverse("my-skills-list"), {"name": "   "}, format="json")

        assert response.status_code == 400


@pytest.mark.django_db
class TestVisibilityToggle:
    @pytest.mark.parametrize("value", ["all", "shortlisted", "hidden"])
    def test_a_student_sets_their_visibility(self, as_student, profile, value):
        response = as_student.put(
            reverse("my-visibility"), {"visibility": value}, format="json"
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.visibility == value

    def test_a_student_can_always_switch_back_out_of_shortlisted_only(
        self, as_student, profile
    ):
        """
        "Shortlisted only" must never be a one-way door.

        The control is on the student's own profile and does not go through
        the visibility rule, so a student who has made themselves invisible
        can always undo it — including when no company has shortlisted them
        and the setting is therefore identical to "hidden".
        """
        for value in ("shortlisted", "hidden", "shortlisted", "all"):
            response = as_student.put(
                reverse("my-visibility"), {"visibility": value}, format="json"
            )
            assert response.status_code == 200, value
            profile.refresh_from_db()
            assert profile.visibility == value

        assert profile.visibility == "all"

    def test_the_student_is_told_how_many_companies_shortlisted_them(
        self, as_student, profile, company_user
    ):
        """
        Without this count, "shortlisted only" with nobody shortlisted looks
        exactly like "visible" to the student while showing their profile to
        no one.
        """
        from profiles.models import CompanyShortlist

        assert as_student.get(reverse("my-profile")).json()["shortlisted_by_count"] == 0

        CompanyShortlist.objects.create(company=company_user.company, profile=profile)

        assert as_student.get(reverse("my-profile")).json()["shortlisted_by_count"] == 1

    def test_an_unknown_visibility_value_is_rejected(self, as_student):
        response = as_student.put(
            reverse("my-visibility"), {"visibility": "friends-only"}, format="json"
        )

        assert response.status_code == 400
