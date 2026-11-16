"""One-click demo sign-in (WEEKEND_DEMO_PLAN D-W3, P5): local demo only."""

import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Role, Status, User
from config.settings import demo_mode_from
from core.demo_accounts import ADMINS, COMPANIES, DEMO_STUDENT_PRN, PILOT_OFFICER_EMAIL

pytestmark = pytest.mark.django_db

PERSONAS = "/api/auth/demo/personas"
LOGIN = "/api/auth/demo/login"
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def demo_on(settings):
    settings.DEBUG = True
    settings.DEMO_MODE = True
    return settings


@pytest.fixture
def seeded(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo", "--with-students", stdout=StringIO(), stderr=StringIO())


def login(api_client, persona):
    return api_client.post(LOGIN, {"persona": persona}, format="json")


class TestTheSetting:
    def test_demo_mode_is_forced_off_whenever_debug_is_off(self):
        assert demo_mode_from(debug=False, requested=True) is False
        assert demo_mode_from(debug=False, requested=False) is False
        assert demo_mode_from(debug=True, requested=False) is False
        assert demo_mode_from(debug=True, requested=True) is True

    def test_the_public_link_environment_cannot_switch_it_on(self):
        """DJANGO_DEBUG=false with DEMO_MODE=true, read as the server would."""
        env = {**os.environ, "DJANGO_DEBUG": "false", "DEMO_MODE": "true"}
        env.pop("DJANGO_SETTINGS_MODULE", None)
        result = subprocess.run(
            [sys.executable, "-c",
             "import config.settings as s; print(s.DEBUG, s.DEMO_MODE)"],
            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.split() == ["False", "False"]


class TestOffMeansAbsent:
    def test_both_routes_are_404_when_demo_mode_is_off(self, api_client, settings, seeded):
        settings.DEBUG = True
        settings.DEMO_MODE = False
        assert api_client.get(PERSONAS).status_code == 404
        assert login(api_client, "officer").status_code == 404

    def test_both_routes_are_404_when_debug_is_off_even_with_demo_mode_set(
        self, api_client, settings, seeded
    ):
        settings.DEBUG = False
        settings.DEMO_MODE = True
        assert api_client.get(PERSONAS).status_code == 404
        response = login(api_client, "officer")
        assert response.status_code == 404
        assert "tokens" not in response.json()

    def test_nothing_is_stamped_when_refused(self, api_client, settings, seeded):
        settings.DEBUG = False
        settings.DEMO_MODE = True
        login(api_client, "officer")
        assert User.objects.get(email=PILOT_OFFICER_EMAIL).last_login is None


class TestPersonas:
    def test_each_seeded_persona_is_offered(self, api_client, demo_on, seeded):
        response = api_client.get(PERSONAS)
        assert response.status_code == 200
        personas = {p["key"]: p for p in response.json()["personas"]}
        assert list(personas) == ["student", "officer", "acme", "nimbus"]
        assert personas["student"]["identifier"] == DEMO_STUDENT_PRN
        assert personas["officer"]["identifier"] == PILOT_OFFICER_EMAIL
        assert personas["acme"]["identifier"] == COMPANIES[0][2]
        assert personas["nimbus"]["identifier"] == COMPANIES[1][2]
        for persona in personas.values():
            assert persona["label"] and persona["description"]
            assert "password" not in persona

    def test_a_persona_whose_account_was_not_seeded_is_not_offered(
        self, api_client, demo_on, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        # Without --with-students there is no demo student to sign in as.
        call_command("seed_demo", stdout=StringIO(), stderr=StringIO())
        keys = [p["key"] for p in api_client.get(PERSONAS).json()["personas"]]
        assert keys == ["officer", "acme", "nimbus"]
        assert login(api_client, "student").status_code == 404


class TestDemoLogin:
    @pytest.mark.parametrize(
        "persona, role, identifier",
        [
            ("student", "student", DEMO_STUDENT_PRN),
            ("officer", "placement_admin", PILOT_OFFICER_EMAIL),
            ("acme", "company_recruiter", COMPANIES[0][2]),
            ("nimbus", "company_recruiter", COMPANIES[1][2]),
        ],
    )
    def test_each_seeded_persona_signs_in(
        self, api_client, demo_on, seeded, persona, role, identifier
    ):
        response = login(api_client, persona)
        assert response.status_code == 200, response.content
        body = response.json()
        user = body["user"]
        assert identifier in (user["email"], user["prn"])
        assert any(r == role or r.startswith(f"{role}:") for r in user["roles"])

        # The token works like any other.
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['tokens']['access']}")
        assert api_client.get("/api/auth/me").json()["id"] == user["id"]

    def test_the_tokens_carry_exactly_the_claims_a_password_login_does(
        self, api_client, demo_on, seeded
    ):
        demo = login(api_client, "officer").json()["tokens"]
        password = api_client.post(
            "/api/auth/login",
            {"identifier": PILOT_OFFICER_EMAIL, "password": ADMINS[1][2]},
            format="json",
        ).json()["tokens"]

        demo_claims = AccessToken(demo["access"]).payload
        password_claims = AccessToken(password["access"]).payload
        assert set(demo_claims) == set(password_claims)
        for claim in ("sub", "roles", "admin_id", "student_id", "company_id"):
            if claim in password_claims:
                assert demo_claims[claim] == password_claims[claim], claim

    def test_a_demo_sign_in_counts_as_a_sign_in(self, api_client, demo_on, seeded):
        login(api_client, "acme")
        assert User.objects.get(email=COMPANIES[0][2]).last_login is not None

    def test_an_unknown_persona_is_a_404(self, api_client, demo_on, seeded):
        assert login(api_client, "superuser").status_code == 404

    def test_a_missing_persona_is_a_400(self, api_client, demo_on, seeded):
        assert api_client.post(LOGIN, {}, format="json").status_code == 400

    def test_an_account_the_seed_did_not_create_cannot_be_named(
        self, api_client, demo_on, seeded
    ):
        other = User.objects.create_admin(
            email="another.officer@college.edu", password="AdminPass!234",
            full_name="Another Officer",
        )
        # Not by email, PRN or ADM- id: a persona key is the only handle.
        for handle in (
            ADMINS[0][0], other.email, other.admin_id, "220200902", "admin",
        ):
            response = login(api_client, handle)
            assert response.status_code == 404, handle
            assert "tokens" not in response.json()

    def test_a_seeded_account_that_may_not_sign_in_is_refused(
        self, api_client, demo_on, seeded
    ):
        User.objects.get(prn=DEMO_STUDENT_PRN).set_status(Status.SUSPENDED)
        assert login(api_client, "student").status_code == 404
        keys = [p["key"] for p in api_client.get(PERSONAS).json()["personas"]]
        assert "student" not in keys

    def test_a_student_with_the_seeded_prn_but_another_email_is_refused(
        self, api_client, demo_on, make_student
    ):
        # A real database could hold a real student under that PRN; matching
        # the PRN alone would sign the demo button into their account.
        make_student(prn=DEMO_STUDENT_PRN, email="someone.real@college.edu")
        assert login(api_client, "student").status_code == 404
        keys = [p["key"] for p in api_client.get(PERSONAS).json()["personas"]]
        assert "student" not in keys

    def test_an_account_of_the_wrong_role_at_a_seeded_address_is_refused(
        self, api_client, demo_on, settings, tmp_path
    ):
        # Somebody else holding the officer's address as a recruiter must not
        # be signed in as "officer".
        User.objects.create_company(
            email=PILOT_OFFICER_EMAIL, password="CompanyPass!234", full_name="Impostor"
        )
        assert login(api_client, "officer").status_code == 404
        assert User.objects.get(email=PILOT_OFFICER_EMAIL).role == Role.COMPANY
