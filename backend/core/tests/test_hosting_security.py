"""H5: what the public demo link exposes with DEBUG off.

Two layers. In-process tests use override_settings. Because several settings
(OTP exposure, the admin route, the renderers) are fixed at import time from
DJANGO_DEBUG, `test_booted_with_debug_off` also starts a fresh interpreter the
way scripts/serve_demo.sh does and probes it with Django's test client, so it
holds however a later change gates the demo-login routes.
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import override_settings
from django.urls import clear_url_caches

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def reload_urls():
    """Re-evaluate config.urls under the current settings, restoring it after."""
    import config.urls

    def _reload():
        clear_url_caches()
        importlib.reload(config.urls)

    yield _reload
    # The settings fixture has already been undone by the time we get here in
    # fixture teardown order only if requested first; reload under the real values.
    clear_url_caches()
    importlib.reload(config.urls)


@override_settings(DEBUG=False)
def test_no_media_route_with_debug_off(client):
    assert client.get("/media/resumes/220200901.pdf").status_code == 404


@override_settings(DEBUG=False, ADMIN_ENABLED=False)
def test_admin_route_is_absent_when_disabled(client, reload_urls):
    reload_urls()
    assert client.get("/django-admin/").status_code == 404
    assert client.get("/django-admin/login/").status_code == 404


@override_settings(DEBUG=False, ADMIN_ENABLED=True)
def test_admin_route_exists_when_explicitly_enabled(client, reload_urls):
    reload_urls()
    assert client.get("/django-admin/login/").status_code == 200


@override_settings(DEBUG=False)
def test_unknown_url_is_a_plain_404_not_the_debug_page(client):
    response = client.get("/api/definitely-not-here")
    assert response.status_code == 404
    body = response.content.decode()
    assert "URLconf" not in body and "DEBUG = True" not in body


@pytest.mark.django_db
def test_signup_response_carries_no_code_unless_exposure_is_on(api_client, roster_student, settings):
    settings.PLACEMENT = {**settings.PLACEMENT, "EXPOSE_OTP_IN_RESPONSE": False}
    response = api_client.post(
        "/api/auth/signup",
        {"prn": roster_student.prn, "email": roster_student.email},
        format="json",
    )
    assert response.status_code == 201
    assert "debug_otp" not in response.json()
    assert "debug_otp" not in response.content.decode()


def test_otp_exposure_follows_debug_by_default():
    # The default is the DEBUG value; the env var is the only override.
    source = (BACKEND_DIR / "config" / "settings.py").read_text()
    assert '"EXPOSE_OTP_IN_RESPONSE": env_bool("EXPOSE_OTP_IN_RESPONSE", DEBUG)' in source


@override_settings(DEBUG=False)
def test_demo_login_routes_404_with_debug_off(client):
    assert client.get("/api/auth/demo/personas").status_code == 404
    response = client.post("/api/auth/demo/login", {"persona": "student"}, content_type="application/json")
    assert response.status_code == 404


_PROBE = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
from django.test import Client
c = Client()
out = {
    "debug": settings.DEBUG,
    "admin_enabled": settings.ADMIN_ENABLED,
    "expose_otp": settings.PLACEMENT["EXPOSE_OTP_IN_RESPONSE"],
    "renderers": list(settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]),
    "csrf_trusted": settings.CSRF_TRUSTED_ORIGINS,
    "admin": c.get("/django-admin/").status_code,
    "admin_login": c.get("/django-admin/login/").status_code,
    "media": c.get("/media/x.pdf").status_code,
    "personas": c.get("/api/auth/demo/personas").status_code,
    "demo_login": c.post("/api/auth/demo/login", "{}", content_type="application/json").status_code,
}
print("PROBE" + json.dumps(out))
"""


def test_booted_with_debug_off():
    env = {
        **os.environ,
        "DJANGO_DEBUG": "false",
        "DJANGO_ALLOWED_HOSTS": "testserver",
        "CSRF_TRUSTED_ORIGINS": "https://demo.example",
        "DATABASE_URL": "sqlite:///:memory:",
        "LLM_ENABLED": "false",
    }
    for name in ("DJANGO_ADMIN_ENABLED", "EXPOSE_OTP_IN_RESPONSE"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]
    line = next(l for l in result.stdout.splitlines() if l.startswith("PROBE"))
    probe = json.loads(line[len("PROBE"):])
    assert probe["debug"] is False
    assert probe["admin_enabled"] is False
    assert probe["expose_otp"] is False
    assert probe["renderers"] == ["rest_framework.renderers.JSONRenderer"]
    assert probe["csrf_trusted"] == ["https://demo.example"]
    assert probe["admin"] == probe["admin_login"] == 404
    assert probe["media"] == 404
    assert probe["personas"] == 404
    assert probe["demo_login"] == 404


# --- QA-1 fixes ----------------------------------------------------------------


def _boot(extra_env: dict, code: str) -> dict:
    """Boot settings in a fresh interpreter with `extra_env`; return the JSON it prints."""
    env = {
        **os.environ,
        "DJANGO_ALLOWED_HOSTS": "testserver",
        "DATABASE_URL": "sqlite:///:memory:",
        "LLM_ENABLED": "false",
        **extra_env,
    }
    for name in ("DJANGO_DEBUG", "DJANGO_ADMIN_ENABLED", "EXPOSE_OTP_IN_RESPONSE", "DEMO_MODE", "SERVE_DEMO_LOCAL_TEST", "TRUSTED_PROXY_COUNT"):
        if name not in extra_env:
            env.pop(name, None)
    script = (
        "import os,json,django\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')\n"
        "django.setup()\n"
        "from django.conf import settings\n" + code
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


_FLAGS = (
    "print(json.dumps({'otp': settings.PLACEMENT['EXPOSE_OTP_IN_RESPONSE'],"
    " 'admin': settings.ADMIN_ENABLED, 'demo': settings.DEMO_MODE}))"
)


def test_serve_demo_exports_win_over_dotenv_style_values():
    # serve_demo exports these explicitly; load_dotenv never overrides an
    # exported variable, so a .env that says "true" cannot win.
    flags = _boot(
        {"DJANGO_DEBUG": "false", "EXPOSE_OTP_IN_RESPONSE": "false", "DJANGO_ADMIN_ENABLED": "false", "DEMO_MODE": "false"},
        _FLAGS,
    )
    assert flags == {"otp": False, "admin": False, "demo": False}


def test_otp_exposure_is_forced_off_with_debug_off_even_if_env_asks():
    flags = _boot({"DJANGO_DEBUG": "false", "EXPOSE_OTP_IN_RESPONSE": "true", "DEMO_MODE": "true"}, _FLAGS)
    assert flags["otp"] is False and flags["demo"] is False


def test_otp_exposure_with_debug_off_needs_the_explicit_local_test_flag():
    flags = _boot({"DJANGO_DEBUG": "false", "EXPOSE_OTP_IN_RESPONSE": "true", "SERVE_DEMO_LOCAL_TEST": "1"}, _FLAGS)
    assert flags["otp"] is True


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_health_leaks_no_filesystem_path_with_debug_off(api_client, settings):
    response = api_client.get("/api/health")
    text = response.content.decode()
    checks = response.json()["checks"]
    assert str(settings.MEDIA_ROOT) not in text and str(BACKEND_DIR) not in text
    assert "location" not in checks["storage"]
    assert "engine" not in checks["database"]
    assert "detail" not in checks["matching_engine"]


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_health_shows_the_storage_location_with_debug_on(api_client, settings):
    assert api_client.get("/api/health").json()["checks"]["storage"]["location"] == str(settings.MEDIA_ROOT)


def test_client_ip_ignores_forwarded_for_with_no_trusted_proxy(settings):
    from rest_framework.test import APIRequestFactory

    from accounts.views import _client_ip

    settings.TRUSTED_PROXY_COUNT = 0
    request = APIRequestFactory().get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="10.0.0.1")
    assert _client_ip(request) == "10.0.0.1"


def test_client_ip_takes_the_hop_the_trusted_proxies_added(settings):
    from rest_framework.test import APIRequestFactory

    from accounts.views import _client_ip

    settings.TRUSTED_PROXY_COUNT = 2  # Netlify and ngrok each append one entry
    factory = APIRequestFactory()
    spoofed = factory.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9, 18.1.1.1", REMOTE_ADDR="127.0.0.1")
    assert _client_ip(spoofed) == "203.0.113.9"  # the attacker's prefix is ignored
    too_short = factory.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="127.0.0.1")
    assert _client_ip(too_short) == "127.0.0.1"  # cannot be a real chain: use the peer


def test_drf_num_proxies_follows_the_trusted_proxy_count():
    out = _boot({"DJANGO_DEBUG": "false", "TRUSTED_PROXY_COUNT": "2"}, "print(json.dumps(settings.REST_FRAMEWORK['NUM_PROXIES']))")
    assert out == 2
    assert _boot({"DJANGO_DEBUG": "false"}, "print(json.dumps(settings.REST_FRAMEWORK['NUM_PROXIES']))") == 0


@pytest.mark.django_db
@pytest.mark.parametrize("accept", ["text/csv", "text/html", "*/*", "application/json"])
def test_outcomes_csv_export_answers_any_accept_header(accept, admin_client):
    response = admin_client.get("/api/profiles/admin/outcomes/export", HTTP_ACCEPT=accept)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.parametrize("accept", ["text/csv", "text/html", "*/*"])
def test_outcomes_export_negotiates_with_json_only_defaults(accept):
    """With the DEBUG-off JSON-only default, a CSV action must still be negotiable."""
    from rest_framework.negotiation import DefaultContentNegotiation
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from profiles.views import AdminProfileViewSet

    renderers = [cls() for cls in AdminProfileViewSet.outcomes_export.kwargs["renderer_classes"]]
    request = Request(APIRequestFactory().get("/", HTTP_ACCEPT=accept))
    renderer, _ = DefaultContentNegotiation().select_renderer(request, renderers)
    assert renderer is not None
