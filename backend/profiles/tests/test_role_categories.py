"""
Role categories, from the profile side: who fits which role, the company
filter, the category list, `manage.py recategorise`, and which JDs feed them.
"""

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from matching import categories, llm
from matching.llm import JobFacts
from matching.models import RoleCategory
from matching.samples import SAMPLE_JOB_DESCRIPTION, SAMPLES_BY_KEY
from matching.testing import FakeLLMClient, fake_embedding, job_reply
from matching.vectorstore import get_vector_store
from profiles.analysis import vector_doc_id
from profiles.models import ProfileSkill, ResumeAnalysis, Visibility

CATEGORIES = "matching-categories"


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


@pytest.fixture
def backend_role(db):
    return categories.record_job_description(
        JobFacts(data=job_reply(), model="fake"), fake_embedding(SAMPLE_JOB_DESCRIPTION), model="fake-embed"
    )


def analysed(profile, cats=()):
    return ResumeAnalysis.objects.create(profile=profile, status="done", source="regex", categories=list(cats))


# --- which JDs feed categories ----------------------------------------------------


@pytest.mark.django_db
class TestJobsFeedCategories:
    def test_a_company_search_with_the_llm_on_records_the_jd(self, as_company, llm_on):
        llm_on()
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        category = RoleCategory.objects.get()
        assert category.name == "Backend Engineer"
        assert category.centroid_model == "fake-embed"

    def test_scoring_records_the_jd_too(self, as_admin, llm_on):
        llm_on()
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": []}
        as_admin.post(reverse("matching-score"), body, format="json")
        assert RoleCategory.objects.filter(name="Backend Engineer").exists()

    def test_the_same_jd_twice_counts_once(self, as_company, llm_on):
        llm_on()
        for _ in range(2):
            as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert RoleCategory.objects.get().jd_count == 1

    def test_with_the_llm_off_no_category_is_created(self, as_company):
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert not RoleCategory.objects.exists()

    def test_a_students_own_jd_does_not_shape_the_recruiters_categories(self, as_student, profile, llm_on):
        llm_on()
        as_student.post(reverse("my-match"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert not RoleCategory.objects.exists()

    def test_a_jd_a_student_checked_first_still_feeds_the_company_reading_once(
        self, as_student, profile, as_company, llm_on
    ):
        llm_on()
        as_student.post(reverse("my-match"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert RoleCategory.objects.get().jd_count == 1
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert RoleCategory.objects.get().jd_count == 1

    def test_a_recorded_jd_is_marked_even_when_its_facts_cache_expires(self, as_company, llm_on):
        from django.core.cache import cache

        client = llm_on()
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        cache.delete(llm.jd_cache_key(SAMPLE_JOB_DESCRIPTION, client.model))
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert RoleCategory.objects.get().jd_count == 1

    def test_a_jd_that_failed_to_record_is_tried_again(self, as_company, llm_on, monkeypatch):
        from profiles import match

        llm_on()
        real = match.record_job_description

        def broken(*args, **kwargs):
            raise RuntimeError("database hiccup")

        monkeypatch.setattr(match, "record_job_description", broken)
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert not RoleCategory.objects.exists()
        monkeypatch.setattr(match, "record_job_description", real)
        as_company.post(reverse("matching-search"), {"jd_text": SAMPLE_JOB_DESCRIPTION}, format="json")
        assert RoleCategory.objects.get().jd_count == 1


# --- the category list --------------------------------------------------------------


@pytest.mark.django_db
class TestCategoryList:
    @pytest.mark.parametrize("who", ["as_company", "as_admin", "as_student"])
    def test_every_role_can_list_the_categories(self, request, who, backend_role):
        client = request.getfixturevalue(who)
        body = client.get(reverse(CATEGORIES)).json()
        assert body["count"] == 1
        [row] = body["results"]
        assert row == {"name": "Backend Engineer", "jd_count": 1, "top_skills": ["Django", "PostgreSQL", "Python"]}

    def test_unauthenticated_requests_get_401(self, api_client, db):
        assert api_client.get(reverse(CATEGORIES)).status_code == 401

    def test_with_no_jds_the_list_is_empty(self, as_company):
        assert as_company.get(reverse(CATEGORIES)).json()["results"] == []

    def test_the_list_is_paginated_and_rejects_unknown_params(self, as_company, backend_role):
        assert as_company.get(reverse(CATEGORIES), {"bogus": 1}).status_code == 400
        assert "next" in as_company.get(reverse(CATEGORIES)).json()


# --- company filter -----------------------------------------------------------------


@pytest.mark.django_db
class TestCompanyCategoryFilter:
    @pytest.fixture
    def two(self, make_student):
        backend = make_student(prn="220200901", full_name="Aarav Mehta")
        designer = make_student(prn="220200909", full_name="Arjun Deshmukh", department="Mechanical")
        analysed(backend, ["Backend Engineer", "Data Engineer"])
        analysed(designer, ["Mechanical Design Engineer"])
        return backend, designer

    def prns(self, response):
        return {row["prn"] for row in response.json()["results"]}

    def test_the_category_filter_returns_profiles_in_that_category(self, as_company, two):
        response = as_company.get(reverse("company-profile-list"), {"category": "Backend Engineer"})
        assert response.status_code == 200
        assert self.prns(response) == {"220200901"}

    def test_the_filter_ignores_case(self, as_company, two):
        response = as_company.get(reverse("company-profile-list"), {"category": "mechanical design engineer"})
        assert self.prns(response) == {"220200909"}

    def test_the_filter_still_respects_visibility(self, as_company, two):
        two[0].visibility = Visibility.HIDDEN
        two[0].save()
        response = as_company.get(reverse("company-profile-list"), {"category": "Backend Engineer"})
        assert self.prns(response) == set()

    def test_an_unknown_category_matches_nobody(self, as_company, two):
        assert self.prns(as_company.get(reverse("company-profile-list"), {"category": "Astronaut"})) == set()

    def test_category_names_resolve_in_one_query_by_name_or_alias_in_any_case(
        self, backend_role, django_assert_num_queries
    ):
        from profiles.match import normalise_filters

        backend_role.add_alias("Server Developer")
        backend_role.save()
        typed = ["BACKEND engineer", "server  developer", "Astronaut", *[f"Role {i}" for i in range(17)]]
        with django_assert_num_queries(1):
            clean = normalise_filters({"categories": {"in": typed}, "department": "Mechanical"})
        assert clean["categories"]["in"][:3] == ["Backend Engineer", "Backend Engineer", "Astronaut"]
        assert clean["department"] == "Mechanical"

    def test_a_single_category_value_resolves_too(self, backend_role):
        from profiles.match import normalise_filters

        assert normalise_filters({"categories": "backend ENGINEER"}) == {"categories": "Backend Engineer"}

    def test_the_match_search_filters_on_categories(self, as_company, two, backend_role):
        for profile in two:
            profile.resume_text = SAMPLES_BY_KEY["backend_engineer"].text
            profile.save()
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"categories": "backend engineer"}}
        results = as_company.post(reverse("matching-search"), body, format="json").json()["results"]
        assert {row["prn"] for row in results} == {"220200901"}
        assert results[0]["categories"] == ["Backend Engineer", "Data Engineer"]


# --- what the student sees ------------------------------------------------------------


@pytest.mark.django_db
class TestStudentSeesTheirRoles:
    def test_the_own_profile_payload_lists_the_roles_they_fit(self, as_student, profile):
        analysed(profile, ["Backend Engineer"])
        assert as_student.get(reverse("my-profile")).json()["categories"] == ["Backend Engineer"]

    def test_with_no_analysis_the_list_is_empty(self, as_student, profile):
        assert as_student.get(reverse("my-profile")).json()["categories"] == []

    def test_analysis_categorises_from_the_resume_skills(self, profile, backend_role):
        from profiles import analysis

        profile.resume_text = SAMPLES_BY_KEY["backend_engineer"].text
        profile.save()
        result, _ = analysis.analyse(profile)
        assert result.categories == ["Backend Engineer"]


# --- recategorise -----------------------------------------------------------------------


@pytest.mark.django_db
class TestRecategorise:
    @pytest.fixture
    def indexed(self, make_student):
        made = {}
        for key, prn in [("backend_engineer", "220200901"), ("marketing_executive", "220200910")]:
            profile = make_student(prn=prn, full_name=key)
            profile.resume_text = SAMPLES_BY_KEY[key].text
            profile.save()
            analysed(profile)
            get_vector_store().upsert(
                vector_doc_id(profile), fake_embedding(profile.resume_text), {"categories": []}, "fake-embed"
            )
            made[key] = profile
        return made

    def test_profiles_are_rescored_into_the_analysis_and_the_vector_metadata(self, indexed, backend_role, capsys):
        call_command("recategorise")
        backend, marketing = indexed["backend_engineer"], indexed["marketing_executive"]
        assert ResumeAnalysis.objects.get(profile=backend).categories == ["Backend Engineer"]
        assert ResumeAnalysis.objects.get(profile=marketing).categories == []
        assert get_vector_store().get(vector_doc_id(backend))[1]["categories"] == ["Backend Engineer"]
        assert "Recategorised 2" in capsys.readouterr().out

    def test_one_prn_only(self, indexed, backend_role):
        call_command("recategorise", prn="220200910")
        assert ResumeAnalysis.objects.get(profile=indexed["backend_engineer"]).categories == []

    def test_a_category_that_disappears_is_removed_from_profiles(self, indexed, backend_role):
        call_command("recategorise")
        RoleCategory.objects.all().delete()
        call_command("recategorise")
        assert ResumeAnalysis.objects.get(profile=indexed["backend_engineer"]).categories == []

    def test_the_form_skills_count(self, make_student, backend_role):
        profile = make_student(prn="220200990", full_name="Form Only")
        analysed(profile)
        for name in ["DRF", "Postgres"]:
            ProfileSkill.objects.create(profile=profile, name=name)
        call_command("recategorise")
        assert ResumeAnalysis.objects.get(profile=profile).categories == ["Backend Engineer"]

    def test_an_unknown_prn_is_an_error(self, db):
        with pytest.raises(CommandError):
            call_command("recategorise", prn="999999999")
