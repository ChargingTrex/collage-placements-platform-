"""Roster admin API: upload, browse, and the flagged-signup review queue."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog
from roster.models import FlaggedSignup, Student

HEADER = "prn,email,full_name,department,batch,cgpa\n"


def csv_upload(body: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("roster.csv", body.encode(), content_type="text/csv")


@pytest.mark.django_db
class TestUploadAuthorization:
    def test_anonymous_upload_is_rejected(self, api_client):
        response = api_client.post(
            reverse("roster-upload"), {"file": csv_upload(HEADER)}, format="multipart"
        )
        assert response.status_code == 401

    def test_student_cannot_upload_a_roster(self, student_client):
        response = student_client.post(
            reverse("roster-upload"), {"file": csv_upload(HEADER)}, format="multipart"
        )
        assert response.status_code == 403

    def test_company_cannot_upload_a_roster(self, api_client, company_user):
        from accounts.serializers import tokens_for

        api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {tokens_for(company_user)['access']}"
        )
        response = api_client.post(
            reverse("roster-upload"), {"file": csv_upload(HEADER)}, format="multipart"
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestUpload:
    def test_clean_upload_returns_200_and_creates_students(self, admin_client):
        body = (
            HEADER
            + "220200961,a@college.edu,Aarav Mehta,Computer Engineering,2026,8.72\n"
            + "220200962,d@college.edu,Diya Sharma,Computer Engineering,2026,9.10\n"
        )

        response = admin_client.post(
            reverse("roster-upload"), {"file": csv_upload(body)}, format="multipart"
        )

        assert response.status_code == 200
        assert response.json()["created"] == 2
        assert response.json()["errors"] == []
        assert Student.objects.count() == 2

    def test_partial_upload_returns_207_with_row_level_errors(self, admin_client):
        body = (
            HEADER
            + "220200961,a@college.edu,Aarav Mehta,Computer Engineering,2026,8.72\n"
            + "220200962,broken,Diya Sharma,Computer Engineering,2026,9.10\n"
        )

        response = admin_client.post(
            reverse("roster-upload"), {"file": csv_upload(body)}, format="multipart"
        )

        assert response.status_code == 207
        body = response.json()
        assert body["created"] == 1
        assert body["errors"][0]["row"] == 3
        assert body["errors"][0]["prn"] == "220200962"
        assert "email" in body["errors"][0]["errors"]

    def test_malformed_file_returns_400_with_an_explanation(self, admin_client):
        response = admin_client.post(
            reverse("roster-upload"),
            {"file": csv_upload("name,marks\nAarav,90\n")},
            format="multipart",
        )

        assert response.status_code == 400
        assert "Missing required column" in response.json()["detail"]

    def test_non_csv_file_is_rejected(self, admin_client):
        response = admin_client.post(
            reverse("roster-upload"),
            {"file": SimpleUploadedFile("roster.xlsx", b"PK\x03\x04")},
            format="multipart",
        )

        assert response.status_code == 400
        assert "csv" in str(response.json()).lower()

    def test_dry_run_reports_without_writing(self, admin_client):
        body = HEADER + "220200961,a@college.edu,Aarav,CE,2026,8.0\n"

        response = admin_client.post(
            reverse("roster-upload"),
            {"file": csv_upload(body), "dry_run": "true"},
            format="multipart",
        )

        assert response.status_code == 200
        assert response.json()["created"] == 1
        assert Student.objects.count() == 0

    def test_upload_is_audit_logged(self, admin_client, admin_user):
        admin_client.post(
            reverse("roster-upload"),
            {"file": csv_upload(HEADER + "220200961,a@college.edu,Aarav,CE,2026,8.0\n")},
            format="multipart",
        )

        entry = AuditLog.objects.get(action=AuditLog.Action.ROSTER_UPLOADED)
        assert entry.actor == admin_user
        assert entry.detail["created"] == 1

    def test_dry_run_is_not_audit_logged(self, admin_client):
        admin_client.post(
            reverse("roster-upload"),
            {"file": csv_upload(HEADER + "220200961,a@college.edu,Aarav,CE,2026,8.0\n"), "dry_run": "true"},
            format="multipart",
        )

        assert not AuditLog.objects.filter(action=AuditLog.Action.ROSTER_UPLOADED).exists()


@pytest.mark.django_db
class TestStudentBrowse:
    def test_admin_can_filter_the_roster_by_department(self, admin_client, roster_student):
        Student.objects.create(
            prn="220200909",
            email="arjun@college.edu",
            full_name="Arjun Deshmukh",
            department="Mechanical",
            batch=2026,
        )

        response = admin_client.get(
            reverse("roster-student-list"), {"department": "Mechanical"}
        )

        assert response.status_code == 200
        assert [row["prn"] for row in response.json()["results"]] == ["220200909"]

    def test_roster_rows_report_whether_an_account_exists(
        self, admin_client, roster_student, verified_student
    ):
        response = admin_client.get(reverse("roster-student-list"))

        assert response.json()["results"][0]["has_account"] is True

    def test_students_cannot_browse_the_roster(self, student_client):
        assert student_client.get(reverse("roster-student-list")).status_code == 403


@pytest.mark.django_db
class TestFlaggedQueue:
    @pytest.fixture
    def flagged(self, db):
        return FlaggedSignup.record(
            prn="220200999",
            email="ghost@college.edu",
            reason=FlaggedSignup.Reason.NO_SUCH_PRN,
        )

    def test_admin_sees_flagged_signups(self, admin_client, flagged):
        response = admin_client.get(reverse("roster-flagged-list"))

        assert response.status_code == 200
        row = response.json()["results"][0]
        assert row["prn"] == "220200999"
        assert row["status"] == "open"
        assert row["reason_display"] == "PRN not on the roster"

    def test_queue_can_be_filtered_to_open_items(self, admin_client, flagged):
        response = admin_client.get(reverse("roster-flagged-list"), {"status": "resolved"})

        assert response.json()["results"] == []

    def test_admin_resolves_a_flag_with_a_note(self, admin_client, admin_user, flagged):
        response = admin_client.post(
            reverse("roster-flagged-review", args=[flagged.id]),
            {"status": "resolved", "admin_note": "Added to the roster manually."},
            format="json",
        )

        assert response.status_code == 200
        flagged.refresh_from_db()
        assert flagged.status == FlaggedSignup.Status.RESOLVED
        assert flagged.reviewed_by == admin_user
        assert flagged.reviewed_at is not None
        assert AuditLog.objects.filter(action=AuditLog.Action.SIGNUP_REVIEWED).exists()

    def test_review_rejects_an_unknown_status(self, admin_client, flagged):
        response = admin_client.post(
            reverse("roster-flagged-review", args=[flagged.id]),
            {"status": "approved"},
            format="json",
        )

        assert response.status_code == 400

    def test_a_dismissed_flag_reopens_when_the_pair_is_tried_again(self, flagged):
        flagged.status = FlaggedSignup.Status.DISMISSED
        flagged.save(update_fields=["status"])

        FlaggedSignup.record(
            prn=flagged.prn, email=flagged.email, reason=FlaggedSignup.Reason.NO_SUCH_PRN
        )

        flagged.refresh_from_db()
        assert flagged.status == FlaggedSignup.Status.OPEN
        assert flagged.attempts == 2

    def test_students_cannot_read_the_flag_queue(self, student_client):
        assert student_client.get(reverse("roster-flagged-list")).status_code == 403
