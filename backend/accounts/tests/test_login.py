"""Login: password and OTP, for all three roles, plus abuse protection."""

import pytest
from django.core import mail
from django.urls import reverse

from accounts.models import OneTimeCode, User


@pytest.mark.django_db
class TestPasswordLogin:
    def test_student_logs_in_with_prn(self, api_client, verified_student):
        response = api_client.post(
            reverse("auth-login"),
            {"identifier": verified_student.prn, "password": "StudentPass!234"},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["user"]["prn"] == verified_student.prn
        assert response.json()["tokens"]["access"]

    def test_student_may_also_log_in_with_their_college_email(
        self, api_client, verified_student
    ):
        response = api_client.post(
            reverse("auth-login"),
            {"identifier": verified_student.email.upper(), "password": "StudentPass!234"},
            format="json",
        )

        assert response.status_code == 200

    def test_admin_and_company_log_in_by_email_and_have_no_prn(
        self, api_client, admin_user, company_user
    ):
        for user, password, role in [
            (admin_user, "AdminPass!234", "placement_admin"),
            (company_user, "CompanyPass!234", "company_recruiter"),
        ]:
            response = api_client.post(
                reverse("auth-login"),
                {"identifier": user.email, "password": password},
                format="json",
            )
            assert response.status_code == 200, role
            # A scoped role carries a ":<uuid>" suffix, per the spec's §4.3.
            roles = response.json()["user"]["roles"]
            assert any(r == role or r.startswith(f"{role}:") for r in roles), roles
            assert response.json()["user"]["prn"] is None

    def test_wrong_password_is_refused_without_saying_which_half_was_wrong(
        self, api_client, verified_student
    ):
        wrong_password = api_client.post(
            reverse("auth-login"),
            {"identifier": verified_student.prn, "password": "NotThePassword!"},
            format="json",
        )
        unknown_account = api_client.post(
            reverse("auth-login"),
            {"identifier": "220200998", "password": "NotThePassword!"},
            format="json",
        )

        assert wrong_password.status_code == unknown_account.status_code == 401
        assert wrong_password.json()["detail"] == unknown_account.json()["detail"]

    def test_unverified_account_is_told_to_verify_rather_than_failing_silently(
        self, api_client, roster_student
    ):
        User.objects.create_user(
            email=roster_student.email, password="StudentPass!234", prn=roster_student.prn
        )

        response = api_client.post(
            reverse("auth-login"),
            {"identifier": roster_student.prn, "password": "StudentPass!234"},
            format="json",
        )

        assert response.status_code == 403
        assert response.json()["needs_verification"] is True


@pytest.mark.django_db
class TestOtpLogin:
    def test_code_request_then_login(self, api_client, verified_student):
        requested = api_client.post(
            reverse("auth-otp-request"),
            {"identifier": verified_student.prn},
            format="json",
        )
        assert requested.status_code == 200
        assert len(mail.outbox) == 1

        response = api_client.post(
            reverse("auth-otp-login"),
            {"identifier": verified_student.prn, "code": requested.json()["debug_otp"]},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["tokens"]["access"]

    def test_request_for_an_unknown_account_looks_identical(self, api_client, verified_student):
        known = api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )
        unknown = api_client.post(
            reverse("auth-otp-request"), {"identifier": "220200998"}, format="json"
        )

        assert known.status_code == unknown.status_code == 200
        assert known.json()["detail"] == unknown.json()["detail"]
        assert "debug_otp" not in unknown.json()  # nothing was actually issued

    def test_a_signup_code_cannot_be_used_to_log_in(self, api_client, verified_student):
        from accounts.otp import issue_code

        signup_code = issue_code(verified_student, OneTimeCode.Purpose.SIGNUP).code

        response = api_client.post(
            reverse("auth-otp-login"),
            {"identifier": verified_student.prn, "code": signup_code},
            format="json",
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestRateLimiting:
    def test_otp_requests_are_capped_per_account_within_the_window(
        self, api_client, verified_student, settings
    ):
        settings.PLACEMENT = {**settings.PLACEMENT, "OTP_REQUESTS_PER_WINDOW": 2}

        first = api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )
        second = api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )
        third = api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )

        assert (first.status_code, second.status_code) == (200, 200)
        assert third.status_code == 429
        assert "Too many codes" in third.json()["detail"]

    def test_the_cap_frees_up_once_the_window_passes(
        self, api_client, verified_student, settings
    ):
        from django.utils import timezone

        settings.PLACEMENT = {**settings.PLACEMENT, "OTP_REQUESTS_PER_WINDOW": 1}
        api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )
        blocked = api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )
        assert blocked.status_code == 429

        OneTimeCode.objects.update(
            created_at=timezone.now() - timezone.timedelta(hours=2)
        )
        allowed = api_client.post(
            reverse("auth-otp-request"), {"identifier": verified_student.prn}, format="json"
        )

        assert allowed.status_code == 200


@pytest.mark.django_db
class TestSession:
    def test_me_requires_a_token(self, api_client):
        assert api_client.get(reverse("auth-me")).status_code == 401

    def test_me_returns_the_authenticated_user(self, student_client, verified_student):
        response = student_client.get(reverse("auth-me"))

        assert response.status_code == 200
        assert response.json()["prn"] == verified_student.prn
        assert response.json()["roles"] == ["student"]

    def test_refresh_exchanges_a_refresh_token_for_a_new_access_token(
        self, api_client, verified_student
    ):
        from accounts.serializers import tokens_for

        tokens = tokens_for(verified_student)
        response = api_client.post(
            reverse("auth-refresh"), {"refresh": tokens["refresh"]}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["access"]

    def test_debug_otp_is_withheld_when_the_setting_is_off(
        self, api_client, roster_student, settings
    ):
        settings.PLACEMENT = {**settings.PLACEMENT, "EXPOSE_OTP_IN_RESPONSE": False}

        response = api_client.post(
            reverse("auth-signup"),
            {"prn": roster_student.prn, "email": roster_student.email},
            format="json",
        )

        assert response.status_code == 201
        assert "debug_otp" not in response.json()
