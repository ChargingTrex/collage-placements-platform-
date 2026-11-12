"""Reading another student's profile is logged; reading your own is not."""

import pytest
from django.urls import reverse

from core.models import AuditLog


def _identity_rows():
    return AuditLog.objects.filter(action="identity_accessed")


@pytest.mark.django_db
class TestIdentityAccessLog:
    def test_admin_detail_read_names_the_prn(self, as_admin, admin_user, profile):
        as_admin.get(reverse("admin-profile-detail", args=[profile.student_id]))

        row = _identity_rows().get()
        assert row.actor == admin_user
        assert row.target == profile.prn

    def test_company_detail_read_names_the_prn(self, as_company, company_user, profile):
        as_company.get(reverse("company-profile-detail", args=[profile.student_id]))

        row = _identity_rows().get()
        assert row.actor == company_user
        assert row.target == profile.prn

    def test_a_list_read_writes_nothing(self, as_admin, profile):
        as_admin.get(reverse("admin-profile-list"))
        assert not _identity_rows().exists()

    def test_a_hidden_profile_read_by_a_company_is_a_404_and_unlogged(
        self, as_company, profile
    ):
        profile.visibility = "hidden"
        profile.save()
        response = as_company.get(reverse("company-profile-detail", args=[profile.student_id]))
        assert response.status_code == 404
        assert not _identity_rows().exists()

    def test_own_profile_read_writes_nothing(self, as_student, profile):
        as_student.get(reverse("my-profile"))
        assert AuditLog.objects.count() == 0
