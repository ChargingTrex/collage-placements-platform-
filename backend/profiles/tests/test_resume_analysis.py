"""
Resume analysis: the LLM reading, the profile vector, and form suggestions.

The LLM is off by default, and CI has no Ollama: the model is a
`FakeLLMClient`, installed by monkeypatching `matching.llm`.
"""

import datetime
import json
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.urls import reverse

from core.models import AuditLog
from matching import llm
from matching.models import StoredVector
from matching.testing import FakeLLMClient, resume_reply
from matching.vectorstore import FILTER_FIELDS
from profiles.analysis import profile_document, resume_digest, vector_doc_id
from profiles.models import ExperienceEntry, ProfileSkill, ProjectEntry, ResumeAnalysis

ANALYZE = "my-resume-analyze"
ANALYSIS = "my-resume-analysis"

RESUME = """Aarav Mehta
aarav.mehta@college.edu | +91 98765 43210
Age: 22  DOB: 12/03/2004  CGPA: 8.9/10

EXPERIENCE
Backend Developer Intern, Loadstar Logistics, Jan 2024 - Dec 2024
Freelance web work for Acme Corp in 2023.

SKILLS
Python, Django, Postgres, Docker

EDUCATION
B.Tech in Computer Engineering, 2022 - 2026
"""

#: What the regex path reads off RESUME: the one dated range.
REGEX_YEARS = 1.0
#: What the model's dated entries add up to: 12 + 6 months.
LLM_YEARS = 1.5

LOADSTAR = {
    "role": "Backend Developer Intern", "organization": "Loadstar Logistics", "kind": "internship",
    "start": "2024-01", "end": "2024-12", "is_current": False, "summary": "Built REST APIs.",
}
ACME = {
    "role": "Freelance Web Developer", "organization": "Acme Corp", "kind": "freelance",
    "start": "2023-06", "end": "2023-11", "is_current": False, "summary": "Built a storefront.",
}


def full_reply(**overrides):
    """A reply carrying every admin-only field, so leaks would show."""
    return resume_reply(
        **{
            "emails": ["aarav.mehta@college.edu"],
            "phones": ["9876543210"],
            "age": 22,
            "date_of_birth": "2004-03-12",
            "cgpa": 8.9,
            "experience": [LOADSTAR, ACME],
            "skills": ["Python", "Django", "Postgres", "Docker", "JS"],
            **overrides,
        }
    )


@pytest.fixture
def llm_on(monkeypatch):
    """Route the portal's LLM calls to a fake client."""

    def _install(client):
        monkeypatch.setattr(llm, "llm_enabled", lambda: True)
        monkeypatch.setattr(llm, "get_client", lambda: client)
        return client

    return _install


@pytest.fixture
def with_resume():
    """Give a profile a stored resume whose text is known exactly."""

    def _attach(profile, text=RESUME):
        profile.resume.save("cv.pdf", ContentFile(b"%PDF-1.4 stub"), save=False)
        profile.resume_filename = "cv.pdf"
        profile.resume_text = text
        profile.save()
        ResumeAnalysis.objects.update_or_create(
            profile=profile, defaults={"resume_sha256": resume_digest(text)}
        )
        return profile

    return _attach


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


# --- upload --------------------------------------------------------------------


@pytest.mark.django_db
class TestUploadCreatesAPendingAnalysis:
    def test_an_upload_records_a_pending_analysis_with_the_resume_digest(
        self, as_student, profile, sample_resume_file
    ):
        response = as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        assert response.status_code == 201
        profile.refresh_from_db()
        analysis = profile.analysis
        assert analysis.status == ResumeAnalysis.Status.PENDING
        assert analysis.resume_sha256 == resume_digest(profile.resume_text)
        assert response.json()["analysis"]["status"] == "pending"

    def test_the_upload_still_prefills_from_regex_synchronously(
        self, as_student, profile, sample_resume_file
    ):
        response = as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        assert response.json()["suggestion"]["experience_years"] == 3.0

    def test_a_new_upload_resets_a_finished_analysis_to_pending(
        self, as_student, profile, sample_resume_file
    ):
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")
        as_student.post(reverse(ANALYZE))
        assert ResumeAnalysis.objects.get(profile=profile).status == "done"

        as_student.post(
            reverse("my-resume"), {"file": sample_resume_file("data_engineer")}, format="multipart"
        )

        analysis = ResumeAnalysis.objects.get(profile=profile)
        assert analysis.status == "pending"
        assert analysis.facts is None

    def test_a_different_resume_drops_the_old_vector_and_categories_at_once(
        self, as_student, profile, with_resume, llm_on, sample_resume_file
    ):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))
        as_student.post(reverse(ANALYZE))
        ResumeAnalysis.objects.filter(profile=profile).update(categories=["Backend Engineer"])
        assert StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()

        response = as_student.post(
            reverse("my-resume"), {"file": sample_resume_file("data_engineer")}, format="multipart"
        )

        assert response.status_code == 201
        assert not StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()
        assert ResumeAnalysis.objects.get(profile=profile).categories == []

    def test_the_same_resume_again_keeps_its_vector(
        self, as_student, profile, llm_on, sample_resume_file
    ):
        llm_on(FakeLLMClient([full_reply()]))
        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")
        as_student.post(reverse(ANALYZE))
        assert StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()

        as_student.post(reverse("my-resume"), {"file": sample_resume_file()}, format="multipart")

        assert StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()

    def test_a_store_failure_does_not_fail_the_upload(
        self, as_student, profile, with_resume, sample_resume_file, monkeypatch
    ):
        with_resume(profile)
        deleted = []

        class Down:
            def delete(self, doc_id):
                deleted.append(doc_id)
                raise ConnectionError("store down")

        monkeypatch.setattr("profiles.analysis.get_vector_store", lambda: Down())
        response = as_student.post(
            reverse("my-resume"), {"file": sample_resume_file("data_engineer")}, format="multipart"
        )
        assert response.status_code == 201
        assert deleted == [vector_doc_id(profile)]


# --- analyze ------------------------------------------------------------------------


@pytest.mark.django_db
class TestAnalyze:
    def test_with_the_llm_off_the_reading_is_regex_and_done(self, as_student, profile, with_resume):
        with_resume(profile)

        response = as_student.post(reverse(ANALYZE))

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "done"
        assert body["source"] == "regex"
        assert body["experience_years"] == REGEX_YEARS
        assert body["education_level"] == "UG"
        assert body["suggested_skills"] == []
        assert body["suggested_experience"] == []
        analysis = ResumeAnalysis.objects.get(profile=profile)
        assert analysis.facts is None
        assert analysis.analysed_at is not None
        assert analysis.error == ""

    def test_with_the_llm_on_the_reading_is_the_models(self, as_student, profile, with_resume, llm_on):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        body = as_student.post(reverse(ANALYZE)).json()

        assert body["source"] == "llm"
        assert body["status"] == "done"
        assert body["experience_years"] == LLM_YEARS
        analysis = ResumeAnalysis.objects.get(profile=profile)
        assert analysis.model_name == "fake-llama"
        assert analysis.facts["skills"][0] == "Python"
        assert analysis.regex_facts["experience_years"] == REGEX_YEARS

    def test_the_llm_date_total_prefills_unconfirmed_experience(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        profile.refresh_from_db()
        assert profile.parsed_experience_years == Decimal("1.5")
        assert profile.experience_years == Decimal("1.5")

    def test_the_llm_date_total_never_overwrites_a_confirmed_value(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        profile.experience_years = Decimal("0.5")
        profile.parsed_values_confirmed = True
        profile.save()
        llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        profile.refresh_from_db()
        assert profile.experience_years == Decimal("0.5")
        assert profile.parsed_experience_years == Decimal("1.5")

    def test_an_unreachable_llm_falls_back_to_regex_and_records_the_error(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient(down=True))

        body = as_student.post(reverse(ANALYZE)).json()

        assert body["status"] == "done"
        assert body["source"] == "regex"
        assert body["retryable"] is True
        assert "down" in ResumeAnalysis.objects.get(profile=profile).error

    def test_a_fallen_back_reading_is_retried_on_the_next_call(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient(down=True))
        as_student.post(reverse(ANALYZE))

        llm_on(FakeLLMClient([full_reply()]))
        body = as_student.post(reverse(ANALYZE)).json()

        assert body["source"] == "llm"
        assert body["retryable"] is False
        assert ResumeAnalysis.objects.get(profile=profile).error == ""

    def test_a_spent_time_budget_falls_back_to_regex_without_calling_the_model(
        self, as_student, profile, with_resume, llm_on, settings
    ):
        settings.RESUME_ANALYSIS = {**settings.RESUME_ANALYSIS, "TIME_BUDGET_SECONDS": 0}
        with_resume(profile)
        client = llm_on(FakeLLMClient([full_reply()]))

        body = as_student.post(reverse(ANALYZE)).json()

        assert body["source"] == "regex"
        assert body["status"] == "done"
        assert client.prompts == []
        assert "budget" in ResumeAnalysis.objects.get(profile=profile).error

    def test_the_budget_caps_the_clients_own_timeout(self, profile, with_resume, settings):
        from profiles.analysis import analyse

        settings.RESUME_ANALYSIS = {**settings.RESUME_ANALYSIS, "TIME_BUDGET_SECONDS": 5}
        with_resume(profile)
        seen = []

        def reply(system, user):
            seen.append(client.timeout)
            return full_reply()

        client = FakeLLMClient(reply)
        client.timeout = 60

        analyse(profile, client=client)

        assert seen and 0 < seen[0] <= 5

    def test_a_resume_with_no_readable_text_is_skipped(self, as_student, profile, with_resume):
        with_resume(profile, text="   ")

        body = as_student.post(reverse(ANALYZE)).json()

        assert body["status"] == "skipped"

    def test_analyzing_without_a_resume_is_a_400(self, as_student, profile):
        response = as_student.post(reverse(ANALYZE))

        assert response.status_code == 400
        assert not ResumeAnalysis.objects.exists()


@pytest.mark.django_db
class TestIdempotency:
    def test_the_same_resume_is_not_analysed_twice(self, as_student, profile, with_resume, llm_on):
        with_resume(profile)
        # One reply only: a second model call would raise "ran out of replies".
        client = llm_on(FakeLLMClient([full_reply()]))

        first = as_student.post(reverse(ANALYZE)).json()
        second = as_student.post(reverse(ANALYZE)).json()

        assert first == second
        assert len(client.prompts) == 1
        assert AuditLog.objects.filter(action=AuditLog.Action.RESUME_ANALYSED).count() == 1

    def test_changed_resume_text_is_analysed_again(self, as_student, profile, with_resume, llm_on):
        with_resume(profile)
        client = llm_on(FakeLLMClient([full_reply(), full_reply(experience=[LOADSTAR])]))
        as_student.post(reverse(ANALYZE))

        profile.resume_text = RESUME + "\nCertified in Kubernetes."
        profile.save()
        body = as_student.post(reverse(ANALYZE)).json()

        assert len(client.prompts) == 2
        assert body["experience_years"] == 1.0
        assert ResumeAnalysis.objects.get(profile=profile).resume_sha256 == resume_digest(profile.resume_text)


@pytest.mark.django_db
class TestPolling:
    def test_polling_before_analysis_reports_pending(self, as_student, profile, with_resume):
        with_resume(profile)

        body = as_student.get(reverse(ANALYSIS)).json()

        assert body["status"] == "pending"
        assert body["experience_years"] is None
        assert body["suggested_skills"] == []

    def test_polling_after_analysis_returns_the_same_payload(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        posted = as_student.post(reverse(ANALYZE)).json()
        polled = as_student.get(reverse(ANALYSIS))

        assert polled.status_code == 200
        assert polled.json() == posted

    def test_polling_with_no_resume_is_a_404(self, as_student, profile):
        assert as_student.get(reverse(ANALYSIS)).status_code == 404


# --- complementing the form ----------------------------------------------------------


@pytest.mark.django_db
class TestSuggestions:
    def test_resume_skills_missing_from_the_profile_are_suggested_by_canonical_name(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        ProfileSkill.objects.create(profile=profile, name="PostgreSQL")
        ProfileSkill.objects.create(profile=profile, name="python")
        llm_on(FakeLLMClient([full_reply()]))

        body = as_student.post(reverse(ANALYZE)).json()

        # Postgres is PostgreSQL through the alias, so it is not offered again.
        assert body["suggested_skills"] == ["Django", "Docker", "JavaScript"]

    def test_resume_roles_with_no_form_entry_are_suggested(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        ExperienceEntry.objects.create(
            profile=profile, role="Backend Intern", organization="Loadstar Logistics Pvt. Ltd.",
            start_date=datetime.date(2024, 1, 1), end_date=datetime.date(2024, 12, 31),
        )
        llm_on(FakeLLMClient([full_reply()]))

        body = as_student.post(reverse(ANALYZE)).json()

        assert body["suggested_experience"] == [
            {
                "role": "Freelance Web Developer",
                "organization": "Acme Corp",
                "kind": "freelance",
                "start_date": "2023-06-01",
                "end_date": "2023-11-30",
                "description": "Built a storefront.",
            }
        ]

    def test_nothing_is_added_to_the_profile_automatically(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        assert not ProfileSkill.objects.filter(profile=profile).exists()
        assert not ExperienceEntry.objects.filter(profile=profile).exists()


def _leaves(value):
    """Every scalar in a JSON body, however deeply nested."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


@pytest.mark.django_db
class TestPrivacy:
    ADMIN_ONLY_KEYS = {"age", "date_of_birth", "dob", "cgpa", "phones", "phone", "emails", "email",
                       "facts", "regex_facts", "error"}

    def test_a_student_payload_never_carries_age_dob_cgpa_phones_or_emails(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        posted = as_student.post(reverse(ANALYZE)).json()
        polled = as_student.get(reverse(ANALYSIS)).json()

        for body in (posted, polled):
            assert not set(_keys(body)) & self.ADMIN_ONLY_KEYS
            dumped = json.dumps(body)
            for value in ("9876543210", "aarav.mehta@college.edu", "2004-03-12", '"22"'):
                assert value not in dumped
            # The CGPA is checked as a value, not a substring: "8.9" also turns
            # up inside timestamps ("...:48.946142") and made this test flaky.
            assert not {8.9, "8.9", "8.90"} & set(_leaves(body))
            assert set(body["agreement"]) <= {"experience_years", "education_level"}

    def test_the_facts_are_still_stored_for_admins(self, as_student, profile, with_resume, llm_on):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        analysis = ResumeAnalysis.objects.get(profile=profile)
        assert analysis.facts["age"] == 22
        assert analysis.agreement["cgpa"]["regex"] == 8.9

    def test_the_audit_row_holds_no_resume_content(self, as_student, profile, with_resume, llm_on):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        entry = AuditLog.objects.get(action=AuditLog.Action.RESUME_ANALYSED)
        assert entry.target == profile.prn
        assert entry.detail == {
            "model_name": "fake-llama", "source": "llm", "status": "done", "experience_years": 1.5,
        }


# --- the vector -----------------------------------------------------------------------


@pytest.mark.django_db
class TestVector:
    def test_analysis_upserts_a_vector_with_only_filter_fields(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        ProfileSkill.objects.create(profile=profile, name="Postgres")
        client = llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        row = StoredVector.objects.get(doc_id=vector_doc_id(profile))
        assert row.model == "fake-embed"
        assert set(row.meta) == set(FILTER_FIELDS)
        assert row.meta["department"] == "Computer Engineering"
        assert row.meta["batch"] == 2026
        assert row.meta["education_level"] == "UG"
        assert row.meta["experience_months"] == 18
        assert row.meta["skills"] == ["postgresql", "sql"]  # canonical, with implications
        assert row.meta["categories"] == []
        assert "aarav" not in json.dumps(row.meta).lower()
        assert client.embedded == [profile_document(profile)]
        analysis = ResumeAnalysis.objects.get(profile=profile)
        assert analysis.embedding_model == "fake-embed"
        assert analysis.needs_reindex is False

    def test_the_document_covers_the_form_and_the_resume(self, profile, with_resume):
        with_resume(profile)
        profile.headline = "Backend developer"
        profile.save()
        ProfileSkill.objects.create(profile=profile, name="Go")
        ProjectEntry.objects.create(profile=profile, title="Fleet tracker", tech_stack=["Kafka"])
        ExperienceEntry.objects.create(
            profile=profile, role="Intern", organization="Loadstar", start_date=datetime.date(2024, 1, 1)
        )

        document = profile_document(profile)

        for part in ("Backend developer", "Go", "Fleet tracker", "Kafka", "Loadstar", "Freelance web work"):
            assert part in document

    def test_with_the_llm_off_no_vector_is_written(self, as_student, profile, with_resume):
        with_resume(profile)

        as_student.post(reverse(ANALYZE))

        assert not StoredVector.objects.exists()
        assert ResumeAnalysis.objects.get(profile=profile).needs_reindex is False

    def test_deleting_the_resume_deletes_the_vector_and_the_analysis(
        self, as_student, profile, with_resume, llm_on
    ):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))
        as_student.post(reverse(ANALYZE))
        assert StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()

        response = as_student.delete(reverse("my-resume"))

        assert response.status_code == 204
        assert not StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()
        assert not ResumeAnalysis.objects.filter(profile=profile).exists()
        assert as_student.get(reverse(ANALYSIS)).status_code == 404

    def test_deleting_the_profile_deletes_the_vector(self, as_student, profile, with_resume, llm_on):
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))
        as_student.post(reverse(ANALYZE))
        doc_id = vector_doc_id(profile)

        profile.delete()

        assert not StoredVector.objects.filter(doc_id=doc_id).exists()


@pytest.mark.django_db
class TestDirtySignals:
    @pytest.fixture
    def analysed(self, profile, with_resume):
        with_resume(profile)
        ResumeAnalysis.objects.filter(profile=profile).update(status="done", needs_reindex=False)
        return profile

    def _dirty(self, profile):
        return ResumeAnalysis.objects.get(profile=profile).needs_reindex

    def test_adding_a_skill_marks_the_analysis_dirty(self, analysed):
        ProfileSkill.objects.create(profile=analysed, name="Rust")

        assert self._dirty(analysed) is True

    def test_editing_an_experience_entry_marks_the_analysis_dirty(self, analysed):
        entry = ExperienceEntry.objects.create(
            profile=analysed, role="Intern", organization="Acme", start_date=datetime.date(2024, 1, 1)
        )
        ResumeAnalysis.objects.update(needs_reindex=False)

        entry.role = "Senior Intern"
        entry.save()

        assert self._dirty(analysed) is True

    def test_deleting_a_project_marks_the_analysis_dirty(self, analysed):
        project = ProjectEntry.objects.create(profile=analysed, title="Fleet tracker")
        ResumeAnalysis.objects.update(needs_reindex=False)

        project.delete()

        assert self._dirty(analysed) is True

    def test_editing_the_profile_through_the_api_marks_the_analysis_dirty(self, as_student, analysed):
        as_student.patch(reverse("my-profile"), {"headline": "Data engineer"}, format="json")

        assert self._dirty(analysed) is True

    def test_another_students_edit_leaves_this_analysis_clean(self, analysed, other_profile):
        ProfileSkill.objects.create(profile=other_profile, name="Rust")

        assert self._dirty(analysed) is False


# --- authorisation ---------------------------------------------------------------------


@pytest.mark.django_db
class TestAuthorisation:
    @pytest.mark.parametrize("name, method", [(ANALYZE, "post"), (ANALYSIS, "get")])
    def test_unauthenticated_requests_get_401(self, api_client, name, method):
        assert getattr(api_client, method)(reverse(name)).status_code == 401

    @pytest.mark.parametrize("name, method", [(ANALYZE, "post"), (ANALYSIS, "get")])
    def test_a_company_cannot_use_the_student_endpoints(self, as_company, name, method):
        assert getattr(as_company, method)(reverse(name)).status_code == 403

    def test_another_student_can_only_ever_analyse_their_own_resume(
        self, as_other_student, profile, other_profile, with_resume
    ):
        with_resume(profile)

        response = as_other_student.post(reverse(ANALYZE))

        # "me" only: there is no way to name someone else's profile, and the
        # caller has no resume of their own.
        assert response.status_code == 400
        assert ResumeAnalysis.objects.get(profile=profile).status == "pending"

    def test_polling_never_shows_another_students_analysis(
        self, as_other_student, profile, with_resume, as_student
    ):
        with_resume(profile)
        as_student.post(reverse(ANALYZE))

        assert as_other_student.get(reverse(ANALYSIS)).status_code == 404


# --- commands ------------------------------------------------------------------------------


@pytest.mark.django_db
class TestAnalyzeResumesCommand:
    def test_one_prn_is_analysed(self, profile, with_resume, capsys):
        with_resume(profile)

        call_command("analyze_resumes", "--prn", profile.prn)

        assert ResumeAnalysis.objects.get(profile=profile).status == "done"
        assert "Analysed 1" in capsys.readouterr().out

    def test_all_profiles_with_a_resume_are_analysed(self, profile, other_profile, with_resume):
        with_resume(profile)

        call_command("analyze_resumes", "--all")

        assert ResumeAnalysis.objects.get(profile=profile).status == "done"
        assert not ResumeAnalysis.objects.filter(profile=other_profile).exists()

    def test_an_up_to_date_analysis_is_skipped_unless_forced(self, profile, with_resume, capsys, llm_on):
        with_resume(profile)
        client = llm_on(FakeLLMClient([full_reply(), full_reply()]))
        call_command("analyze_resumes", "--all")

        call_command("analyze_resumes", "--all")
        assert len(client.prompts) == 1
        assert "1 already up to date" in capsys.readouterr().out

        call_command("analyze_resumes", "--all", "--force")
        assert len(client.prompts) == 2

    def test_an_unknown_prn_is_an_error(self, db):
        with pytest.raises(CommandError):
            call_command("analyze_resumes", "--prn", "999999999")

    def test_a_scope_is_required(self, db):
        with pytest.raises(CommandError):
            call_command("analyze_resumes")


@pytest.mark.django_db
class TestReindexVectorsCommand:
    @pytest.fixture
    def analysed(self, profile, with_resume, as_student):
        with_resume(profile)
        as_student.post(reverse(ANALYZE))  # LLM off: done, no vector
        return profile

    def test_with_the_llm_off_reindexing_is_an_error(self, analysed):
        with pytest.raises(CommandError):
            call_command("reindex_vectors")

    def test_every_analysed_profile_is_embedded(self, analysed, llm_on):
        llm_on(FakeLLMClient())

        call_command("reindex_vectors")

        row = StoredVector.objects.get(doc_id=vector_doc_id(analysed))
        assert set(row.meta) == set(FILTER_FIELDS)
        assert ResumeAnalysis.objects.get(profile=analysed).embedding_model == "fake-embed"

    def test_dirty_only_skips_clean_profiles(self, analysed, other_profile, with_resume, llm_on, capsys):
        llm_on(FakeLLMClient())
        call_command("reindex_vectors")
        with_resume(other_profile)
        ResumeAnalysis.objects.filter(profile=other_profile).update(status="done")
        ProfileSkill.objects.create(profile=other_profile, name="Rust")
        capsys.readouterr()

        call_command("reindex_vectors", "--dirty-only")

        assert "Reindexed 1" in capsys.readouterr().out
        assert ResumeAnalysis.objects.get(profile=other_profile).needs_reindex is False

    def test_one_prn_is_reindexed(self, analysed, llm_on, capsys):
        llm_on(FakeLLMClient())

        call_command("reindex_vectors", "--prn", analysed.prn)

        assert "Reindexed 1" in capsys.readouterr().out

    def test_a_failed_embedding_leaves_the_profile_dirty(self, analysed, llm_on):
        llm_on(FakeLLMClient(down=True))

        call_command("reindex_vectors")

        assert not StoredVector.objects.exists()
        assert ResumeAnalysis.objects.get(profile=analysed).needs_reindex is True


# --- fixes from the Tasks 4-5 verification ------------------------------------------


@pytest.mark.django_db
class TestUnknownResumeSkillsBecomeAliasSuggestions:
    """V2: `suggest_aliases` had no caller, so no suggestion was ever made."""

    @pytest.fixture(autouse=True)
    def _suggest_everything(self, settings):
        settings.SKILL_GRAPH = {**settings.SKILL_GRAPH, "ALIAS_SUGGESTION_THRESHOLD": 0.0}

    def test_an_unknown_skill_becomes_a_pending_suggestion_and_nothing_more(
        self, as_student, profile, with_resume, llm_on
    ):
        from matching.models import SkillAlias, SkillAliasSuggestion

        with_resume(profile)
        llm_on(FakeLLMClient([full_reply(skills=["Python", "Postgres", "Djangoo Rest Framwork"])]))

        as_student.post(reverse(ANALYZE))

        assert list(SkillAliasSuggestion.objects.values_list("alias", "status")) == [
            ("Djangoo Rest Framwork", "pending")
        ]
        assert not SkillAlias.objects.filter(name="Djangoo Rest Framwork").exists()

    def test_known_skills_cost_no_extra_embedding(self, as_student, profile, with_resume, llm_on):
        from matching.models import SkillAliasSuggestion

        with_resume(profile)
        client = llm_on(FakeLLMClient([full_reply()]))

        as_student.post(reverse(ANALYZE))

        assert not SkillAliasSuggestion.objects.exists()
        assert client.embedded == [profile_document(profile)]

    def test_with_the_llm_off_nothing_is_suggested(self, as_student, profile, with_resume):
        from matching.models import SkillAliasSuggestion

        with_resume(profile, RESUME + "\nSKILLS\nDjangoo Rest Framwork\n")

        as_student.post(reverse(ANALYZE))

        assert not SkillAliasSuggestion.objects.exists()

    def test_a_failing_suggestion_never_breaks_the_analysis(
        self, as_student, profile, with_resume, llm_on, monkeypatch
    ):
        from profiles import analysis as analysis_service

        def broken(*args, **kwargs):
            raise RuntimeError("the skill graph is on fire")

        monkeypatch.setattr(analysis_service, "suggest_aliases", broken)
        with_resume(profile)
        llm_on(FakeLLMClient([full_reply(skills=["Djangoo Rest Framwork"])]))

        response = as_student.post(reverse(ANALYZE))

        assert response.status_code == 200
        assert response.json()["status"] == "done"
        assert response.json()["source"] == "llm"


@pytest.mark.django_db
class TestDeletingAnAnalysisDeletesItsVector:
    """V5: Django admin can delete an analysis; its vector must go with it."""

    @pytest.fixture
    def analysed(self, profile, with_resume, llm_on):
        from profiles.analysis import analyse

        with_resume(profile)
        llm_on(FakeLLMClient([full_reply()]))
        analyse(profile)
        assert StoredVector.objects.filter(doc_id=vector_doc_id(profile)).exists()
        return profile

    def test_deleting_the_row_deletes_the_vector(self, analysed):
        ResumeAnalysis.objects.get(profile=analysed).delete()

        assert not StoredVector.objects.filter(doc_id=vector_doc_id(analysed)).exists()

    def test_the_django_admin_delete_action_deletes_the_vector(self, analysed, rf, admin_user):
        from django.contrib.admin.sites import AdminSite

        from profiles.admin import ResumeAnalysisAdmin

        model_admin = ResumeAnalysisAdmin(ResumeAnalysis, AdminSite())
        request = rf.post("/")
        request.user = admin_user

        model_admin.delete_queryset(request, ResumeAnalysis.objects.filter(profile=analysed))

        assert not ResumeAnalysis.objects.exists()
        assert not StoredVector.objects.exists()

    def test_another_profiles_vector_is_untouched(self, analysed, other_profile, with_resume, llm_on):
        from profiles.analysis import analyse

        with_resume(other_profile)
        llm_on(FakeLLMClient([full_reply()]))
        analyse(other_profile)

        ResumeAnalysis.objects.get(profile=analysed).delete()

        assert list(StoredVector.objects.values_list("doc_id", flat=True)) == [vector_doc_id(other_profile)]

    def test_a_vector_store_failure_does_not_stop_the_delete(self, analysed, monkeypatch):
        from profiles import analysis as analysis_service

        class BrokenStore:
            def delete(self, doc_id):
                raise ConnectionError("mongo is down")

        monkeypatch.setattr(analysis_service, "get_vector_store", lambda: BrokenStore())

        ResumeAnalysis.objects.get(profile=analysed).delete()

        assert not ResumeAnalysis.objects.exists()


@pytest.mark.django_db
class TestSuggestedExperienceKindsAndGrounding:
    """V6: no invented internships, no invented jobs."""

    def suggest(self, as_student, profile, with_resume, llm_on, entries, text=RESUME):
        with_resume(profile, text)
        llm_on(FakeLLMClient([full_reply(experience=entries)]))
        return as_student.post(reverse(ANALYZE)).json()["suggested_experience"]

    def test_a_null_kind_is_left_out_not_made_an_internship(self, as_student, profile, with_resume, llm_on):
        [suggestion] = self.suggest(as_student, profile, with_resume, llm_on, [{**LOADSTAR, "kind": None}])

        assert "kind" not in suggestion

    def test_an_unknown_kind_is_left_out(self, as_student, profile, with_resume, llm_on):
        [suggestion] = self.suggest(as_student, profile, with_resume, llm_on, [{**LOADSTAR, "kind": "job"}])

        assert "kind" not in suggestion

    @pytest.mark.parametrize("kind", ["full_time", "part_time", "internship", "volunteer", "freelance"])
    def test_a_known_kind_is_kept(self, as_student, profile, with_resume, llm_on, kind):
        [suggestion] = self.suggest(as_student, profile, with_resume, llm_on, [{**LOADSTAR, "kind": kind}])

        assert suggestion["kind"] == kind

    def test_an_entry_whose_start_year_is_not_on_the_resume_is_not_offered(
        self, as_student, profile, with_resume, llm_on
    ):
        invented = {"role": "CTO", "organization": "Imaginary Inc", "kind": "full_time",
                    "start": "1980-01", "end": None, "is_current": True, "summary": None}

        suggestions = self.suggest(as_student, profile, with_resume, llm_on, [LOADSTAR, invented])

        assert [s["organization"] for s in suggestions] == ["Loadstar Logistics"]

    def test_an_entry_with_no_start_is_not_offered(self, as_student, profile, with_resume, llm_on):
        undated = {**ACME, "start": None, "end": None}

        assert self.suggest(as_student, profile, with_resume, llm_on, [undated]) == []

    def test_a_two_digit_year_on_the_resume_grounds_the_entry(self, as_student, profile, with_resume, llm_on):
        text = "EXPERIENCE\nWeb Intern, Acme Corp (Jun'23 - Nov'23)\n"

        [suggestion] = self.suggest(as_student, profile, with_resume, llm_on, [ACME], text=text)

        assert suggestion["organization"] == "Acme Corp"

    def test_every_suggestion_is_accepted_by_the_experience_endpoint(
        self, as_student, profile, with_resume, llm_on
    ):
        entries = [{**LOADSTAR, "kind": None}, {**ACME, "kind": "full_time"}]

        for suggestion in self.suggest(as_student, profile, with_resume, llm_on, entries):
            response = as_student.post(reverse("my-experience-list"), suggestion, format="json")
            assert response.status_code == 201, response.json()
