"""
Who may see and change what.

The rule under test throughout: authorization is enforced by the queryset,
so a forbidden object is not merely hidden from a list -- it cannot be
reached by any route.
"""

import pytest
from django.urls import reverse

from profiles.models import CompanyShortlist, Visibility


@pytest.mark.django_db
class TestStudentIsolation:
    def test_a_student_cannot_read_another_students_experience_entry(
        self, as_student, as_other_student, other_profile
    ):
        created = as_other_student.post(
            reverse("my-experience-list"),
            {"role": "Intern", "organization": "Acme", "start_date": "2025-05-01"},
            format="json",
        )
        entry_id = created.json()["id"]

        response = as_student.get(reverse("my-experience-detail", args=[entry_id]))

        # 404, not 403: confirming it exists would leak the other student's data.
        assert response.status_code == 404

    def test_a_student_cannot_edit_another_students_entry(
        self, as_student, as_other_student
    ):
        created = as_other_student.post(
            reverse("my-experience-list"),
            {"role": "Intern", "organization": "Acme", "start_date": "2025-05-01"},
            format="json",
        )

        response = as_student.patch(
            reverse("my-experience-detail", args=[created.json()["id"]]),
            {"role": "Hijacked"},
            format="json",
        )

        assert response.status_code == 404

    def test_a_student_cannot_delete_another_students_project(
        self, as_student, as_other_student, other_profile
    ):
        created = as_other_student.post(
            reverse("my-projects-list"), {"title": "Their project"}, format="json"
        )

        response = as_student.delete(
            reverse("my-projects-detail", args=[created.json()["id"]])
        )

        assert response.status_code == 404
        assert other_profile.projects.count() == 1

    def test_a_student_only_ever_lists_their_own_entries(
        self, as_student, as_other_student
    ):
        as_other_student.post(
            reverse("my-experience-list"),
            {"role": "Theirs", "organization": "Acme", "start_date": "2025-05-01"},
            format="json",
        )
        as_student.post(
            reverse("my-experience-list"),
            {"role": "Mine", "organization": "Beta", "start_date": "2025-05-01"},
            format="json",
        )

        listed = as_student.get(reverse("my-experience-list")).json()

        assert [row["role"] for row in listed["results"]] == ["Mine"]

    def test_a_student_cannot_browse_the_company_profile_list(self, as_student):
        assert as_student.get(reverse("company-profile-list")).status_code == 403

    def test_a_student_cannot_reach_the_admin_profile_list(self, as_student):
        assert as_student.get(reverse("admin-profile-list")).status_code == 403


@pytest.mark.django_db
class TestVisibilityRuleIsServerSide:
    def test_all_companies_can_see_an_all_companies_profile(self, as_company, profile):
        profile.visibility = Visibility.ALL
        profile.save()

        listed = as_company.get(reverse("company-profile-list")).json()

        assert [row["prn"] for row in listed["results"]] == [profile.prn]

    def test_a_hidden_profile_is_absent_from_the_list(self, as_company, profile):
        profile.visibility = Visibility.HIDDEN
        profile.save()

        listed = as_company.get(reverse("company-profile-list")).json()

        assert listed["results"] == []

    def test_a_hidden_profile_cannot_be_fetched_directly_either(self, as_company, profile):
        """The list being empty is not enough -- the detail route must refuse
        a PRN the company already knows."""
        profile.visibility = Visibility.HIDDEN
        profile.save()

        response = as_company.get(reverse("company-profile-detail", args=[profile.student_id]))

        assert response.status_code == 404

    def test_a_shortlisted_only_profile_is_hidden_from_a_company_that_has_not_shortlisted(
        self, as_company, profile
    ):
        profile.visibility = Visibility.SHORTLISTED
        profile.save()

        assert as_company.get(reverse("company-profile-list")).json()["results"] == []
        assert (
            as_company.get(reverse("company-profile-detail", args=[profile.student_id])).status_code
            == 404
        )

    def test_a_shortlisted_only_profile_is_visible_to_the_company_that_shortlisted_it(
        self, as_company, company_user, profile
    ):
        profile.visibility = Visibility.SHORTLISTED
        profile.save()
        CompanyShortlist.objects.create(company=company_user.company, profile=profile)

        listed = as_company.get(reverse("company-profile-list")).json()

        assert [row["prn"] for row in listed["results"]] == [profile.prn]

    def test_one_companys_shortlist_does_not_expose_the_profile_to_another(
        self, api_client, company_user, admin_user, profile
    ):
        from accounts.models import User
        from accounts.serializers import tokens_for

        from accounts.models import Company

        other_company = User.objects.create_company(
            email="talent@nimbus.example", password="CompanyPass!234",
            company=Company.objects.create(name="Nimbus Analytics"),
        )
        profile.visibility = Visibility.SHORTLISTED
        profile.save()
        CompanyShortlist.objects.create(company=company_user.company, profile=profile)

        api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {tokens_for(other_company)['access']}"
        )
        listed = api_client.get(reverse("company-profile-list")).json()

        assert listed["results"] == []

    def test_an_admin_sees_every_profile_regardless_of_visibility(self, as_admin, profile):
        profile.visibility = Visibility.HIDDEN
        profile.save()

        listed = as_admin.get(reverse("admin-profile-list")).json()

        assert [row["student"]["prn"] for row in listed["results"]] == [profile.prn]

    def test_an_anonymous_visitor_sees_nothing(self, api_client, profile):
        assert api_client.get(reverse("company-profile-list")).status_code == 401
        assert api_client.get(reverse("my-profile")).status_code == 401


@pytest.mark.django_db
class TestCompanyViewIsNarrower:
    def test_contact_details_are_withheld_until_the_profile_is_verified(
        self, as_company, as_admin, profile
    ):
        profile.phone = "9820011001"
        profile.save()

        unverified = as_company.get(
            reverse("company-profile-detail", args=[profile.student_id])
        ).json()
        assert unverified["contact"] is None

        as_admin.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True},
            format="json",
        )
        verified = as_company.get(
            reverse("company-profile-detail", args=[profile.student_id])
        ).json()

        assert verified["contact"]["phone"] == "9820011001"
        assert verified["contact"]["email"] == profile.student.email

    def test_the_company_view_never_exposes_parser_internals(self, as_company, profile):
        body = as_company.get(reverse("company-profile-detail", args=[profile.student_id])).json()

        assert "resume_text" not in body
        assert "parsed_experience_years" not in body

    def test_a_company_cannot_edit_a_profile(self, as_company, profile):
        response = as_company.patch(
            reverse("company-profile-detail", args=[profile.student_id]),
            {"headline": "Rewritten"},
            format="json",
        )

        assert response.status_code == 405


@pytest.mark.django_db
class TestShortlisting:
    def test_a_company_shortlists_and_unshortlists_a_student(
        self, as_company, company_user, profile
    ):
        added = as_company.post(
            reverse("company-profile-shortlist", args=[profile.student_id]),
            {"note": "Strong Django background"},
            format="json",
        )
        assert added.status_code == 201
        assert CompanyShortlist.objects.filter(company=company_user.company, profile=profile).exists()

        removed = as_company.delete(
            reverse("company-profile-shortlist", args=[profile.student_id])
        )
        assert removed.status_code == 204
        assert not CompanyShortlist.objects.filter(company=company_user.company).exists()

    def test_shortlisting_twice_does_not_duplicate(self, as_company, company_user, profile):
        for _ in range(2):
            as_company.post(
                reverse("company-profile-shortlist", args=[profile.student_id]), {}, format="json"
            )

        assert CompanyShortlist.objects.filter(company=company_user.company).count() == 1

    def test_a_company_cannot_shortlist_a_profile_it_cannot_see(self, as_company, profile):
        profile.visibility = Visibility.HIDDEN
        profile.save()

        response = as_company.post(
            reverse("company-profile-shortlist", args=[profile.student_id]), {}, format="json"
        )

        assert response.status_code == 404

    def test_narrowing_to_shortlisted_keeps_the_companies_already_interested(
        self, as_company, company_user, profile, api_client
    ):
        """
        The sequence the setting is designed for, and the only one that makes
        it reachable: a profile is public, a company shortlists it, and the
        student then narrows visibility. "Shortlisted only" means "keep the
        companies already interested, drop everyone else" -- so the interested
        company keeps access and a stranger does not.

        A company that never saw the profile cannot shortlist its way in, which
        is why a new company can only reach such a student through the Phase 4
        application flow.
        """
        from accounts.models import User
        from accounts.serializers import tokens_for

        from accounts.models import Company

        stranger = User.objects.create_company(
            email="stranger@nimbus.example", password="CompanyPass!234",
            company=Company.objects.create(name="Nimbus Analytics"),
        )

        # 1. While public, one company shortlists.
        assert (
            as_company.post(
                reverse("company-profile-shortlist", args=[profile.student_id]), {}, format="json"
            ).status_code
            == 201
        )

        # 2. The student narrows visibility.
        profile.visibility = Visibility.SHORTLISTED
        profile.save()

        # 3. The interested company keeps access; the stranger has none.
        assert (
            as_company.get(reverse("company-profile-detail", args=[profile.student_id])).status_code
            == 200
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(stranger)['access']}")
        assert (
            api_client.get(reverse("company-profile-detail", args=[profile.student_id])).status_code
            == 404
        )
        # 4. And the stranger cannot shortlist its way in.
        assert (
            api_client.post(
                reverse("company-profile-shortlist", args=[profile.student_id]), {}, format="json"
            ).status_code
            == 404
        )

    def test_an_admin_cannot_shortlist(self, as_admin, profile):
        response = as_admin.post(
            reverse("company-profile-shortlist", args=[profile.student_id]), {}, format="json"
        )

        assert response.status_code == 403
