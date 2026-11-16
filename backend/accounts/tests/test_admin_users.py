"""The placement cell's directory of every account (WEEKEND_DEMO_PLAN P1, P2)."""

import pytest
from django.urls import reverse

from accounts.models import Company, Role, Status, User
from core.models import AuditLog
from roster.models import Student

pytestmark = pytest.mark.django_db

USERS = "/api/auth/admin/users"
SUMMARY = "/api/auth/admin/users/summary"


@pytest.fixture
def directory(admin_user, company_user, make_student):
    """One of each role, plus a student who has not opened a profile yet."""
    on_profile = make_student(prn="220200901", full_name="Aarav Mehta", batch=2026)
    Student.objects.filter(pk=on_profile.student_id).update(school="computing_data_science")

    # Signed up and verified, but never opened the profile page, so no
    # StudentProfile row exists. School and batch must still filter.
    roster = Student.objects.create(
        prn="220200955", email="rhea.iyer@college.edu", full_name="Rhea Iyer",
        department="BBA", batch=2027, cgpa="7.90", school="business",
    )
    no_profile = User.objects.create_user(
        email=roster.email, password="StudentPass!234", role=Role.STUDENT,
        prn=roster.prn, full_name=roster.full_name,
    )
    no_profile.mark_verified()

    nimbus = Company.objects.create(name="Nimbus Analytics")
    other_recruiter = User.objects.create_company(
        email="talent@nimbusanalytics.example", password="CompanyPass!234",
        full_name="Dev Menon", company=nimbus,
    )
    return {
        "admin": admin_user,
        "recruiter": company_user,
        "other_recruiter": other_recruiter,
        "student": on_profile.user,
        "student_profile": on_profile,
        "no_profile": no_profile,
    }


def rows(response):
    assert response.status_code == 200, response.content
    return {row["email"]: row for row in response.json()["results"]}


def client_for(user):
    from rest_framework.test import APIClient

    from accounts.serializers import tokens_for

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(user)['access']}")
    return client


def identity_reads():
    return AuditLog.objects.filter(action=AuditLog.Action.IDENTITY_ACCESSED)


class TestAccess:
    def test_only_a_placement_admin_may_list_every_user(
        self, api_client, as_company, directory
    ):
        as_student = client_for(directory["student"])
        assert api_client.get(USERS).status_code == 401
        assert as_company.get(USERS).status_code == 403
        assert as_student.get(USERS).status_code == 403
        assert api_client.get(SUMMARY).status_code == 401
        assert as_company.get(SUMMARY).status_code == 403
        assert as_student.get(SUMMARY).status_code == 403

    def test_the_directory_is_read_only(self, as_admin, directory):
        assert as_admin.post(USERS, {"email": "x@college.edu"}, format="json").status_code == 405
        assert as_admin.delete(USERS).status_code == 405

    def test_the_routes_are_named(self):
        assert reverse("auth-admin-users") == USERS
        assert reverse("auth-admin-users-summary") == SUMMARY


class TestListing:
    def test_every_account_is_listed_whatever_its_role(self, as_admin, directory):
        listed = rows(as_admin.get(USERS))
        assert set(listed) == {user.email for user in User.objects.all()}
        assert {row["role"] for row in listed.values()} == {"admin", "company", "student"}

    def test_each_role_shows_its_own_human_key(self, as_admin, directory):
        listed = rows(as_admin.get(USERS))
        admin = directory["admin"]
        recruiter = directory["recruiter"]

        assert listed[admin.email]["human_key"] == admin.admin_id
        assert admin.admin_id.startswith("ADM-")
        assert listed[recruiter.email]["human_key"] == recruiter.company.company_id
        assert listed[recruiter.email]["human_key"].startswith("CMP-")
        assert listed["220200901@college.edu"]["human_key"] == "220200901"

    def test_a_row_carries_the_columns_the_users_page_shows(self, as_admin, directory):
        listed = rows(as_admin.get(USERS))
        student = listed["220200901@college.edu"]
        assert student["full_name"] == "Aarav Mehta"
        assert student["status"] == Status.ACTIVE
        assert student["status_display"]
        assert student["is_active"] is True
        assert student["is_verified"] is True
        assert student["profile_verified"] is False
        assert student["onboarding_completed"] is False
        assert student["school"] == "computing_data_science"
        assert student["school_name"] == "School of Computing and Data Science"
        assert student["batch"] == 2026
        assert student["company"] is None
        assert "last_login" in student and "date_joined" in student

        recruiter = listed[directory["recruiter"].email]
        assert recruiter["company"] == {
            "id": str(directory["recruiter"].company.id),
            "company_id": directory["recruiter"].company.company_id,
            "name": "Acme Tech",
        }
        # Profile, onboarding and roster facts belong to students only.
        for key in ("profile_verified", "onboarding_completed", "school", "batch", "student_id"):
            assert recruiter[key] is None, key

    def test_admin_only_profile_facts_never_ride_the_row(self, as_admin, directory):
        """CGPA, phone and the D18-D20 fields stay on the profile endpoints."""
        student = rows(as_admin.get(USERS))["220200901@college.edu"]
        for key in ("cgpa", "phone", "password", "age", "date_of_birth"):
            assert key not in student

    def test_a_student_links_to_their_profile_only_once_one_exists(self, as_admin, directory):
        listed = rows(as_admin.get(USERS))
        assert listed["220200901@college.edu"]["student_id"] == str(
            directory["student_profile"].student_id
        )
        # No profile row yet: the admin detail page would 404, so no link.
        assert listed["rhea.iyer@college.edu"]["student_id"] is None
        # Roster facts still come through for that student.
        assert listed["rhea.iyer@college.edu"]["school"] == "business"
        assert listed["rhea.iyer@college.edu"]["batch"] == 2027

    def test_onboarding_and_profile_verification_reflect_the_profile(
        self, as_admin, directory
    ):
        from django.utils import timezone

        profile = directory["student_profile"]
        profile.onboarding_completed_at = timezone.now()
        profile.save(update_fields=["onboarding_completed_at"])
        profile.mark_verified(directory["admin"])

        student = rows(as_admin.get(USERS))["220200901@college.edu"]
        assert student["onboarding_completed"] is True
        assert student["profile_verified"] is True

    def test_the_list_is_paginated_like_every_other(self, as_admin, admin_user):
        for n in range(25):
            User.objects.create_admin(
                email=f"officer{n:02d}@college.edu", password="AdminPass!234",
                full_name=f"Officer {n:02d}",
            )
        first = as_admin.get(USERS).json()
        assert first["count"] == 26
        assert len(first["results"]) == 20
        assert first["next"]
        second = as_admin.get(USERS, {"page": 2}).json()
        assert len(second["results"]) == 6


class TestLastSignIn:
    def test_signing_in_stamps_last_login(self, api_client, as_admin, verified_student):
        assert rows(as_admin.get(USERS))[verified_student.email]["last_login"] is None

        response = api_client.post(
            "/api/auth/login",
            {"identifier": verified_student.prn, "password": "StudentPass!234"},
            format="json",
        )
        assert response.status_code == 200

        verified_student.refresh_from_db()
        assert verified_student.last_login is not None
        assert rows(as_admin.get(USERS))[verified_student.email]["last_login"]

    def test_a_failed_sign_in_does_not(self, api_client, verified_student):
        api_client.post(
            "/api/auth/login",
            {"identifier": verified_student.prn, "password": "NotThePassword!"},
            format="json",
        )
        verified_student.refresh_from_db()
        assert verified_student.last_login is None


class TestFilters:
    def test_role_and_status_filter(self, as_admin, directory):
        directory["no_profile"].set_status(Status.SUSPENDED)

        assert set(rows(as_admin.get(USERS, {"role": "company"}))) == {
            "recruiter@acmetech.example", "talent@nimbusanalytics.example",
        }
        assert set(rows(as_admin.get(USERS, {"role": "student", "status": "suspended"}))) == {
            "rhea.iyer@college.edu"
        }

    def test_a_misspelt_role_or_status_is_a_400_not_an_empty_page(self, as_admin, directory):
        assert as_admin.get(USERS, {"role": "recruiter"}).status_code == 400
        assert as_admin.get(USERS, {"status": "enrolled"}).status_code == 400

    def test_prn_matches_exactly_and_tolerates_paste_noise(self, as_admin, directory):
        assert set(rows(as_admin.get(USERS, {"prn": " 220200955 "}))) == {"rhea.iyer@college.edu"}
        assert rows(as_admin.get(USERS, {"prn": "999999999"})) == {}

    def test_prns_reports_the_ones_it_could_not_find(self, as_admin, directory):
        response = as_admin.get(USERS, {"prns": "220200901, 220200955,999999999"})
        assert set(rows(response)) == {"220200901@college.edu", "rhea.iyer@college.edu"}
        assert response.json()["unmatched_prns"] == ["999999999"]

    def test_admin_id_and_company_id_filter_by_human_key(self, as_admin, directory):
        admin = directory["admin"]
        by_admin = rows(as_admin.get(USERS, {"admin_id": admin.admin_id.lower()}))
        assert set(by_admin) == {admin.email}

        acme = directory["recruiter"].company
        assert set(rows(as_admin.get(USERS, {"company_id": acme.company_id}))) == {
            directory["recruiter"].email
        }

    def test_school_and_batch_filter_through_the_roster(self, as_admin, directory):
        assert set(rows(as_admin.get(USERS, {"school": "business"}))) == {"rhea.iyer@college.edu"}
        assert set(rows(as_admin.get(USERS, {"batch": 2026}))) == {"220200901@college.edu"}
        assert rows(as_admin.get(USERS, {"school": "business", "batch": 2026})) == {}

    def test_search_covers_name_email_and_every_human_key(self, as_admin, directory):
        assert set(rows(as_admin.get(USERS, {"search": "rhea"}))) == {"rhea.iyer@college.edu"}
        assert set(rows(as_admin.get(USERS, {"search": "nimbusanalytics"}))) == {
            "talent@nimbusanalytics.example"
        }
        assert set(rows(as_admin.get(USERS, {"search": "220200901"}))) == {"220200901@college.edu"}
        admin = directory["admin"]
        assert set(rows(as_admin.get(USERS, {"search": admin.admin_id}))) == {admin.email}
        acme = directory["recruiter"].company
        assert set(rows(as_admin.get(USERS, {"search": acme.company_id}))) == {
            directory["recruiter"].email
        }

    def test_an_unknown_parameter_is_a_400(self, as_admin, directory):
        response = as_admin.get(USERS, {"pm": "220200901"})
        assert response.status_code == 400
        assert "pm" in response.json()


class TestAudit:
    def test_every_listing_writes_one_identity_access_row(self, as_admin, directory):
        as_admin.get(USERS, {"role": "student"})

        assert identity_reads().count() == 1
        entry = identity_reads().get()
        assert entry.actor == directory["admin"]
        assert entry.detail["route"] == USERS
        assert entry.detail["query"] == {"role": "student"}
        assert entry.detail["count"] == 2
        # Which identities were shown, by human key -- the list counterpart of
        # the PRN a profile read records.
        assert sorted(entry.detail["keys"]) == ["220200901", "220200955"]

    def test_long_query_values_are_truncated_in_the_audit_row(self, as_admin, directory):
        # ?prns= accepts up to 200 keys; the audit row should not store an
        # arbitrarily long string for each call.
        long_search = "x" * 5000
        assert as_admin.get(USERS, {"search": long_search}).status_code == 200
        stored = identity_reads().get().detail["query"]["search"]
        assert len(stored) <= 201
        assert stored.startswith("x" * 200)

    def test_a_prns_lookup_still_writes_only_one_row(self, as_admin, directory):
        # The unmatched-PRN report re-runs the filtered query; that must not
        # double the audit trail.
        as_admin.get(USERS, {"prns": "220200901,999999999"})
        assert identity_reads().count() == 1

    def test_a_refused_request_writes_none(self, as_admin, as_company, directory):
        as_admin.get(USERS, {"pm": "x"})
        as_company.get(USERS)
        assert not identity_reads().exists()

    def test_the_summary_reveals_no_identities_and_writes_none(self, as_admin, directory):
        assert as_admin.get(SUMMARY).status_code == 200
        assert not identity_reads().exists()


class TestSummary:
    def test_counts_by_role_and_status(self, as_admin, directory):
        directory["no_profile"].set_status(Status.GRADUATED)

        summary = as_admin.get(SUMMARY).json()
        assert summary["total"] == 5
        assert summary["by_role"] == {"student": 2, "admin": 1, "company": 2}
        assert summary["by_status"]["active"] == 4
        assert summary["by_status"]["graduated"] == 1

    def test_every_role_and_status_is_present_even_at_zero(self, as_admin):
        summary = as_admin.get(SUMMARY).json()
        assert set(summary["by_role"]) == set(Role.values)
        assert set(summary["by_status"]) == set(Status.values)
        assert summary["by_role"]["student"] == 0

    def test_it_offers_the_school_and_batch_filter_options(self, as_admin, directory):
        summary = as_admin.get(SUMMARY).json()
        assert {"key": "business", "name": "School of Business"} in summary["schools"]
        assert summary["batches"] == [2026, 2027]

    def test_an_unknown_parameter_is_a_400(self, as_admin):
        assert as_admin.get(SUMMARY, {"role": "student"}).status_code == 400
