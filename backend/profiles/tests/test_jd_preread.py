"""
V6: a demo JD search must not wait on the chat model.

- `manage.py read_jd` reads a JD ahead of time, with no budget, into the
  same cache key the search uses, and records its category as a search would.
- A live search gives the chat reading only `JD_READING_BUDGET_SECONDS`;
  an unread JD falls back to the text reading fast, and still ranks on vectors.
- `CACHE_BACKEND=file` makes that cache shared and persistent.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.urls import reverse

from matching import llm
from matching.models import RoleCategory
from matching.samples import SAMPLE_JOB_DESCRIPTION
from matching.testing import FakeLLMClient, job_reply
from profiles import match

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _fast_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def llm_on(monkeypatch):
    def _install(client=None):
        client = client or FakeLLMClient(lambda system, user: job_reply())
        monkeypatch.setattr(llm, "llm_enabled", lambda: True)
        monkeypatch.setattr(llm, "get_client", lambda: client)
        return client

    return _install


def no_chat(system, user):
    raise AssertionError("the search called the chat model for a pre-read JD")


# --- manage.py read_jd ------------------------------------------------------------


@pytest.mark.django_db
class TestReadJdCommand:
    def test_with_the_llm_off_it_is_an_error(self):
        with pytest.raises(CommandError):
            call_command("read_jd", stdin=io.StringIO(SAMPLE_JOB_DESCRIPTION))

    def test_it_caches_the_reading_under_the_search_key_and_records_the_category(self, llm_on, tmp_path):
        client = llm_on()
        path = tmp_path / "jd.txt"
        path.write_text(SAMPLE_JOB_DESCRIPTION)

        call_command("read_jd", str(path))

        assert len(client.prompts) == 1
        assert cache.get(llm.jd_cache_key(SAMPLE_JOB_DESCRIPTION, client.model)) is not None
        category = RoleCategory.objects.get()
        assert category.name == "Backend Engineer"
        assert category.jd_count == 1
        assert category.centroid_model == "fake-embed"

    def test_reading_from_stdin_with_stray_whitespace_hits_the_same_key(self, llm_on):
        client = llm_on()

        call_command("read_jd", "-", stdin=io.StringIO("\n\n  " + SAMPLE_JOB_DESCRIPTION + "  \n"))

        assert cache.get(llm.jd_cache_key(SAMPLE_JOB_DESCRIPTION.strip(), client.model)) is not None

    def test_it_runs_without_the_live_budget(self, llm_on, settings):
        """A CPU model takes a minute: the pre-read must wait for it."""
        settings.RESUME_ANALYSIS = {**settings.RESUME_ANALYSIS, "TIME_BUDGET_SECONDS": 0.0}
        settings.MATCH_SCORE = {**settings.MATCH_SCORE, "JD_READING_BUDGET_SECONDS": 0.0}
        client = llm_on()

        call_command("read_jd", "-", stdin=io.StringIO(SAMPLE_JOB_DESCRIPTION))

        assert len(client.prompts) == 1

    def test_the_timeout_option_sets_the_per_request_timeout(self, llm_on):
        seen = []
        client = FakeLLMClient(lambda s, u: seen.append(client.timeout) or job_reply())
        llm_on(client)

        call_command("read_jd", "-", "--timeout", "300", stdin=io.StringIO(SAMPLE_JOB_DESCRIPTION))

        assert seen == [300.0]

    def test_a_reading_that_fails_is_an_error_and_records_nothing(self, llm_on):
        llm_on(FakeLLMClient(down=True))

        with pytest.raises(CommandError):
            call_command("read_jd", "-", stdin=io.StringIO(SAMPLE_JOB_DESCRIPTION))
        assert not RoleCategory.objects.exists()

    def test_a_too_short_jd_is_refused(self, llm_on):
        llm_on()
        with pytest.raises(CommandError):
            call_command("read_jd", "-", stdin=io.StringIO("too short"))

    def test_a_search_with_the_pasted_text_then_uses_the_reading_without_the_model(
        self, llm_on, as_company
    ):
        llm_on()
        call_command("read_jd", "-", stdin=io.StringIO(SAMPLE_JOB_DESCRIPTION))
        client = llm_on(FakeLLMClient(no_chat))

        body = as_company.post(
            reverse("matching-search"), {"jd_text": "  " + SAMPLE_JOB_DESCRIPTION + "\n"}, format="json"
        ).json()

        assert client.prompts == []
        assert body["job"]["source"] == "llm"
        assert body["job"]["canonical_role"] == "Backend Engineer"
        # Recorded once, by the pre-read: the search does not count it again.
        assert RoleCategory.objects.get().jd_count == 1


# --- the live budget for the chat reading -----------------------------------------


@pytest.mark.django_db
class TestLiveJdReadingBudget:
    def test_the_chat_reading_gets_only_the_short_budget(self, llm_on, settings):
        settings.MATCH_SCORE = {**settings.MATCH_SCORE, "JD_READING_BUDGET_SECONDS": 3}
        seen = []

        def reply(system, user):
            seen.append(client.timeout)
            raise llm.LLMUnavailable("read timed out")

        client = FakeLLMClient(reply)
        client.timeout = 60
        llm_on(client)

        job = match.read_job(SAMPLE_JOB_DESCRIPTION, record=True)

        assert seen and max(seen) <= 3
        assert job.facts is None
        assert job.vector is not None  # the embedding still had the full budget

    def test_a_cached_reading_needs_no_budget_at_all(self, llm_on, settings):
        settings.MATCH_SCORE = {**settings.MATCH_SCORE, "JD_READING_BUDGET_SECONDS": 0.0}
        cache.set(llm.jd_cache_key(SAMPLE_JOB_DESCRIPTION, "fake-llama"), job_reply(), 60)
        llm_on(FakeLLMClient(no_chat))

        job = match.read_job(SAMPLE_JOB_DESCRIPTION)

        assert job.facts is not None and job.facts.canonical_role == "Backend Engineer"

    def test_the_default_is_a_few_seconds(self):
        from django.conf import settings

        assert 0 < settings.MATCH_SCORE["JD_READING_BUDGET_SECONDS"] <= 5


# --- the cache backend ------------------------------------------------------------

_READ_CACHES = """
import json, os, sys
sys.path.insert(0, os.getcwd())
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings
print(json.dumps({k: str(v) for k, v in settings.CACHES["default"].items() if k in ("BACKEND", "LOCATION")}))
"""


def read_caches(**env):
    clean = {k: v for k, v in os.environ.items() if k not in ("CACHE_BACKEND", "CACHE_LOCATION")}
    clean.update(env)
    result = subprocess.run(
        [sys.executable, "-c", _READ_CACHES], cwd=BACKEND, env=clean, capture_output=True, text=True
    )
    return result


class TestCacheBackend:
    def test_the_default_is_per_process_memory(self):
        result = read_caches()
        assert json.loads(result.stdout)["BACKEND"].endswith("LocMemCache")

    def test_file_gives_a_shared_persistent_cache_at_the_location(self, tmp_path):
        result = read_caches(CACHE_BACKEND="file", CACHE_LOCATION=str(tmp_path / "cache"))
        assert json.loads(result.stdout) == {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": str(tmp_path / "cache"),
        }

    def test_an_unknown_backend_is_refused(self):
        result = read_caches(CACHE_BACKEND="redis-maybe")
        assert result.returncode != 0
        assert "CACHE_BACKEND" in result.stderr
