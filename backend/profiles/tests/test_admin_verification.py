"""Admin verification and the profile-completion aggregates."""

import pytest
from django.urls import reverse

from core.models import AuditLog
from profiles.models import ProfileSkill, ProjectEntry, Visibility


@pytest.mark.django_db
class TestVerification:
    def test_an_admin_marks_a_profile_verified(self, as_admin, admin_user, profile):
        response = as_admin.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True, "note": "Checked against the department record."},
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.is_verified is True
        assert profile.verified_by == admin_user
        assert profile.verified_at is not None

    def test_the_verified_badge_reaches_the_company_facing_view(
        self, as_admin, as_company, profile
    ):
        before = as_company.get(reverse("company-profile-detail", args=[profile.student_id]))
        assert before.json()["is_verified"] is False

        as_admin.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True},
            format="json",
        )

        after = as_company.get(reverse("company-profile-detail", args=[profile.student_id]))
        assert after.json()["is_verified"] is True
        assert after.json()["verified_at"] is not None

    def test_verification_can_be_revoked(self, as_admin, admin_user, profile):
        profile.mark_verified(admin_user)

        as_admin.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": False},
            format="json",
        )

        profile.refresh_from_db()
        assert profile.is_verified is False
        assert profile.verified_by is None

    def test_both_directions_are_audit_logged(self, as_admin, admin_user, profile):
        for value in (True, False):
            as_admin.post(
                reverse("admin-profile-verification", args=[profile.student_id]),
                {"is_verified": value},
                format="json",
            )

        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert AuditLog.Action.PROFILE_VERIFIED in actions
        assert AuditLog.Action.PROFILE_UNVERIFIED in actions
        assert AuditLog.objects.filter(actor=admin_user).count() == 2

    def test_a_company_cannot_verify_a_profile(self, as_company, profile):
        response = as_company.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True},
            format="json",
        )

        assert response.status_code == 403

    def test_a_student_cannot_verify_their_own_profile(self, as_student, profile):
        response = as_student.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True},
            format="json",
        )

        assert response.status_code == 403
        profile.refresh_from_db()
        assert profile.is_verified is False

    def test_an_admin_can_verify_a_hidden_profile(self, as_admin, profile):
        """Verification is the placement cell's job and does not depend on
        who the student has chosen to show the profile to."""
        profile.visibility = Visibility.HIDDEN
        profile.save()

        response = as_admin.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True},
            format="json",
        )

        assert response.status_code == 200


@pytest.mark.django_db
class TestAdminBrowse:
    def test_an_admin_sees_the_full_profile_including_parser_values(
        self, as_admin, profile
    ):
        body = as_admin.get(reverse("admin-profile-detail", args=[profile.student_id])).json()

        assert "parsed_experience_years" in body
        assert body["student"]["prn"] == profile.prn

    def test_admin_search_by_prn(self, as_admin, profile, other_profile):
        response = as_admin.get(reverse("admin-profile-list"), {"search": other_profile.prn})

        assert [row["student"]["prn"] for row in response.json()["results"]] == [
            other_profile.prn
        ]

    def test_admin_filters_by_verification_state(self, as_admin, admin_user, profile, other_profile):
        profile.mark_verified(admin_user)

        response = as_admin.get(reverse("admin-profile-list"), {"verified": "false"})

        assert [row["student"]["prn"] for row in response.json()["results"]] == [
            other_profile.prn
        ]


@pytest.mark.django_db
class TestStats:
    def test_aggregates_back_the_prd_completion_metric(
        self, as_admin, admin_user, profile, other_profile
    ):
        profile.headline = "Backend developer"
        profile.summary = "I build APIs."
        profile.github_url = "https://github.com/aarav"
        profile.save()
        for name in ("Python", "Django", "PostgreSQL"):
            ProfileSkill.objects.create(profile=profile, name=name)
        ProjectEntry.objects.create(profile=profile, title="Fleet tracker")
        profile.mark_verified(admin_user)

        body = as_admin.get(reverse("admin-profile-stats")).json()

        assert body["profiles"] == 2
        assert body["verified"] == 1
        assert body["with_resume"] == 0
        assert body["fully_complete"] == 0  # no resume, no experience entry yet
        assert 0 < body["average_completion_percent"] < 100

    def test_stats_are_admin_only(self, as_company, as_student):
        assert as_company.get(reverse("admin-profile-stats")).status_code == 403
        assert as_student.get(reverse("admin-profile-stats")).status_code == 403
