"""Signup: roster matching, the flag queue, and OTP verification."""

import pytest
from django.core import mail
from django.urls import reverse

from accounts.models import OneTimeCode, Role, User
from core.models import AuditLog
from roster.models import FlaggedSignup, Student


def signup(client, prn, email):
    return client.post(
        reverse("auth-signup"), {"prn": prn, "email": email}, format="json"
    )


@pytest.mark.django_db
class TestRosterMatching:
    def test_matching_pair_creates_an_inactive_account_and_emails_a_code(
        self, api_client, roster_student
    ):
        response = signup(api_client, roster_student.prn, roster_student.email)

        assert response.status_code == 201
        user = User.objects.get(prn=roster_student.prn)
        assert user.role == Role.STUDENT
        assert user.is_active is False  # not until the code is confirmed
        assert user.full_name == "Aarav Mehta"  # copied from the roster
        assert OneTimeCode.objects.filter(
            user=user, purpose=OneTimeCode.Purpose.SIGNUP
        ).exists()
        assert len(mail.outbox) == 1
        assert roster_student.email in mail.outbox[0].to

    def test_prn_is_trimmed_and_email_is_matched_case_insensitively(self, api_client, roster_student):
        # PRNs are digits only, so this checks trimming of the PRN, not its case.
        response = signup(api_client, " 220200901 ", "Aarav.Mehta@College.edu")

        assert response.status_code == 201
        assert User.objects.filter(prn="220200901").exists()

    @pytest.mark.parametrize(
        "prn,email,expected_reason",
        [
            ("220200999", "ghost@college.edu", FlaggedSignup.Reason.NO_SUCH_PRN),
            ("220200901", "someone.else@college.edu", FlaggedSignup.Reason.EMAIL_MISMATCH),
            ("220200997", "aarav.mehta@college.edu", FlaggedSignup.Reason.PRN_MISMATCH),
        ],
    )
    def test_mismatched_pair_is_blocked_and_flagged(
        self, api_client, roster_student, prn, email, expected_reason
    ):
        response = signup(api_client, prn, email)

        assert response.status_code == 403
        assert response.json()["reason"] == expected_reason
        assert response.json()["flagged_for_review"] is True
        assert not User.objects.filter(prn=prn.upper()).exists()

        flagged = FlaggedSignup.objects.get(prn=prn.upper(), email=email.lower())
        assert flagged.reason == expected_reason
        assert flagged.status == FlaggedSignup.Status.OPEN
        assert AuditLog.objects.filter(
            action=AuditLog.Action.SIGNUP_FLAGGED
        ).exists()

    def test_non_college_email_domain_is_refused(self, api_client, roster_student):
        response = signup(api_client, roster_student.prn, "aarav.mehta@gmail.com")

        assert response.status_code == 403
        assert response.json()["reason"] == FlaggedSignup.Reason.DOMAIN_NOT_ALLOWED
        assert User.objects.count() == 0

    def test_ineligible_roster_row_cannot_sign_up(self, api_client):
        Student.objects.create(
            prn="210200911",
            email="former.student@college.edu",
            full_name="Farhan Sheikh",
            department="Computer Engineering",
            batch=2025,
            is_placement_eligible=False,
        )

        response = signup(api_client, "210200911", "former.student@college.edu")

        assert response.status_code == 403
        assert response.json()["reason"] == FlaggedSignup.Reason.NOT_ELIGIBLE

    def test_repeat_attempts_collapse_into_one_flag_with_a_counter(
        self, api_client, roster_student
    ):
        for _ in range(3):
            signup(api_client, "220200999", "ghost@college.edu")

        assert FlaggedSignup.objects.count() == 1
        assert FlaggedSignup.objects.get().attempts == 3

    def test_unverified_student_may_restart_signup(self, api_client, roster_student):
        first = signup(api_client, roster_student.prn, roster_student.email)
        second = signup(api_client, roster_student.prn, roster_student.email)

        assert (first.status_code, second.status_code) == (201, 201)
        assert User.objects.filter(prn=roster_student.prn).count() == 1
        # The older code must no longer work.
        codes = OneTimeCode.objects.filter(user__prn=roster_student.prn).order_by("created_at")
        assert codes.count() == 2
        assert codes.first().is_consumed is True

    def test_already_verified_account_is_told_to_log_in(
        self, api_client, roster_student, verified_student
    ):
        response = signup(api_client, roster_student.prn, roster_student.email)

        assert response.status_code == 403
        assert response.json()["reason"] == FlaggedSignup.Reason.ALREADY_REGISTERED


@pytest.mark.django_db
class TestVerification:
    def test_correct_code_activates_the_account_and_returns_tokens(
        self, api_client, roster_student
    ):
        created = signup(api_client, roster_student.prn, roster_student.email)
        code = created.json()["debug_otp"]

        response = api_client.post(
            reverse("auth-verify"),
            {"identifier": roster_student.prn, "code": code, "password": "StudentPass!234"},
            format="json",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["prn"] == roster_student.prn
        assert body["user"]["is_verified"] is True
        assert body["tokens"]["access"] and body["tokens"]["refresh"]

        user = User.objects.get(prn=roster_student.prn)
        assert user.is_active is True
        assert user.email_verified_at is not None
        assert user.check_password("StudentPass!234")

    def test_code_is_single_use(self, api_client, roster_student):
        code = signup(api_client, roster_student.prn, roster_student.email).json()["debug_otp"]
        payload = {
            "identifier": roster_student.prn,
            "code": code,
            "password": "StudentPass!234",
        }

        assert api_client.post(reverse("auth-verify"), payload, format="json").status_code == 200
        replay = api_client.post(reverse("auth-verify"), payload, format="json")

        assert replay.status_code == 400

    def test_wrong_code_is_refused_and_counts_down_attempts(self, api_client, roster_student):
        signup(api_client, roster_student.prn, roster_student.email)

        response = api_client.post(
            reverse("auth-verify"),
            {"identifier": roster_student.prn, "code": "000000", "password": "StudentPass!234"},
            format="json",
        )

        assert response.status_code == 400
        assert "attempt(s) left" in response.json()["detail"]
        assert User.objects.get(prn=roster_student.prn).is_active is False

    def test_code_locks_after_the_configured_number_of_wrong_attempts(
        self, api_client, roster_student, settings
    ):
        settings.PLACEMENT = {**settings.PLACEMENT, "OTP_MAX_ATTEMPTS": 3}
        real_code = signup(api_client, roster_student.prn, roster_student.email).json()["debug_otp"]

        for _ in range(3):
            api_client.post(
                reverse("auth-verify"),
                {"identifier": roster_student.prn, "code": "000000", "password": "StudentPass!234"},
                format="json",
            )

        # Even the genuine code is dead once the record is locked.
        response = api_client.post(
            reverse("auth-verify"),
            {"identifier": roster_student.prn, "code": real_code, "password": "StudentPass!234"},
            format="json",
        )
        assert response.status_code == 400
        assert "Too many wrong attempts" in response.json()["detail"]

    def test_expired_code_is_refused(self, api_client, roster_student):
        from django.utils import timezone

        code = signup(api_client, roster_student.prn, roster_student.email).json()["debug_otp"]
        OneTimeCode.objects.update(expires_at=timezone.now() - timezone.timedelta(minutes=1))

        response = api_client.post(
            reverse("auth-verify"),
            {"identifier": roster_student.prn, "code": code, "password": "StudentPass!234"},
            format="json",
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"]

    def test_weak_password_is_rejected(self, api_client, roster_student):
        code = signup(api_client, roster_student.prn, roster_student.email).json()["debug_otp"]

        response = api_client.post(
            reverse("auth-verify"),
            {"identifier": roster_student.prn, "code": code, "password": "password"},
            format="json",
        )

        assert response.status_code == 400
        assert "password" in response.json()

    def test_code_is_never_stored_in_plaintext(self, api_client, roster_student):
        code = signup(api_client, roster_student.prn, roster_student.email).json()["debug_otp"]

        record = OneTimeCode.objects.get()
        assert code not in record.code_hash
        assert len(record.code_hash) == 64
