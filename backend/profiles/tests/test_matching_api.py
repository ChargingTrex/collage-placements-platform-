"""
The JD match endpoints (plan Task 6):

    POST /api/matching/search     company or admin: rank visible profiles
    POST /api/matching/score      company or admin: score named visible profiles
    POST /api/profiles/me/match   student: their own score

Visibility is decided by `visible_to` alone, never by the vector store: a
store returning a hidden profile's id must not get it into a response.
"""

import json
import uuid

import pytest
from django.urls import reverse

from matching import llm, vectorstore
from matching.samples import SAMPLE_JOB_DESCRIPTION, SAMPLES_BY_KEY
from matching.testing import FakeLLMClient, fake_embedding, job_reply
from matching.vectorstore import LocalVectorStore, get_vector_store
from profiles.analysis import profile_document, vector_doc_id
from profiles.models import CompanyShortlist, ProfileSkill, ResumeAnalysis, Visibility

SEARCH = "matching-search"
SCORE = "matching-score"
ME_MATCH = "my-match"

#: (key, prn, department, experience, education)
PEOPLE = [
    ("backend_engineer", "220200901", "Computer Engineering", "3.0", "UG"),
    ("data_engineer", "220200904", "Information Technology", "2.5", "Masters"),
    ("frontend_intern", "220200905", "Information Technology", "0.5", "UG"),
    ("mechanical_designer", "220200909", "Mechanical", "4.0", "UG"),
    ("marketing_executive", "220200910", "Mechanical", "1.0", "UG"),
]


def post(client, name, body):
    return client.post(reverse(name), body, format="json")


def client_for(user):
    from rest_framework.test import APIClient

    from accounts.serializers import tokens_for

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(user)['access']}")
    return client


@pytest.fixture(autouse=True)
def _fast_passwords(settings):
    """Five students a test: the real hasher made setup most of the run."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def people(make_student):
    """The five sample resumes as visible profiles."""
    made = {}
    for key, prn, department, years, level in PEOPLE:
        profile = make_student(
            prn=prn, full_name=key.replace("_", " ").title(), department=department,
            experience_years=years, education_level=level,
        )
        profile.resume_text = SAMPLES_BY_KEY[key].text
        profile.save()
        made[key] = profile
    return made


@pytest.fixture
def indexed(people):
    """Every profile's vector in the local store, as an analysis would write it."""
    store = get_vector_store()
    for profile in people.values():
        store.upsert(
            vector_doc_id(profile),
            fake_embedding(profile_document(profile)),
            {"department": profile.student.department, "skills": [], "categories": []},
            "fake-embed",
        )
    return people


@pytest.fixture
def llm_on(monkeypatch):
    def _install(client=None):
        client = client or FakeLLMClient(lambda system, user: job_reply())
        monkeypatch.setattr(llm, "llm_enabled", lambda: True)
        monkeypatch.setattr(llm, "get_client", lambda: client)
        return client

    return _install


class EveryIdStore(LocalVectorStore):
    """A store that returns every profile it is told about, best first."""

    def __init__(self, ids):
        self.ids = [str(i) for i in ids]

    def search(self, vector, k, model, filters=None):
        return [(doc_id, 0.99) for doc_id in self.ids][:k]

    def get(self, doc_id):
        return (fake_embedding("python django"), {}, "fake-embed")


@pytest.fixture
def leaky_store(monkeypatch, people):
    store = EveryIdStore(p.student_id for p in people.values())

    def get_store(name=None):
        return store

    get_store.cache_clear = lambda: None  # the caches fixture resets it on teardown
    monkeypatch.setattr(vectorstore, "get_vector_store", get_store)
    return store


def keys(results):
    return {row["prn"] for row in results}


def all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_keys(item)


# --- visibility ---------------------------------------------------------------------


@pytest.mark.django_db
class TestVisibility:
    @pytest.fixture
    def restricted(self, people, company):
        people["backend_engineer"].visibility = Visibility.HIDDEN
        people["backend_engineer"].save()
        people["data_engineer"].visibility = Visibility.SHORTLISTED
        people["data_engineer"].save()
        return people

    def test_hidden_and_unshortlisted_profiles_never_appear_even_when_the_store_returns_them(
        self, as_company, restricted, leaky_store, llm_on
    ):
        llm_on()
        response = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION})
        assert response.status_code == 200
        found = keys(response.json()["results"])
        assert "220200901" not in found
        assert "220200904" not in found
        assert found == {"220200905", "220200909", "220200910"}

    def test_a_shortlisted_only_profile_appears_to_the_company_that_shortlisted_it(
        self, as_company, restricted, leaky_store, llm_on, company
    ):
        llm_on()
        CompanyShortlist.objects.create(company=company, profile=restricted["data_engineer"])
        found = keys(post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()["results"])
        assert "220200904" in found
        assert "220200901" not in found

    def test_the_fallback_search_respects_visibility_too(self, as_company, restricted):
        found = keys(post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()["results"])
        assert found == {"220200905", "220200909", "220200910"}

    def test_an_admin_sees_every_profile(self, as_admin, restricted):
        found = keys(post(as_admin, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()["results"])
        assert {"220200901", "220200904"} <= found

    def test_scoring_named_hidden_or_unknown_ids_silently_omits_them(self, as_company, restricted, leaky_store):
        ids = [str(p.student_id) for p in restricted.values()] + [str(uuid.uuid4())]
        response = post(as_company, SCORE, {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": ids})
        assert response.status_code == 200
        assert keys(response.json()["results"]) == {"220200905", "220200909", "220200910"}

    def test_an_unknown_id_and_a_hidden_id_look_the_same(self, as_company, restricted):
        hidden = post(as_company, SCORE, {
            "jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": [str(restricted["backend_engineer"].student_id)],
        })
        unknown = post(as_company, SCORE, {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": [str(uuid.uuid4())]})
        assert hidden.status_code == unknown.status_code == 200
        assert hidden.json()["results"] == unknown.json()["results"] == []


# --- privacy ------------------------------------------------------------------------


FORBIDDEN_KEYS = {
    "age", "date_of_birth", "facts", "regex_facts", "agreement", "verification_checks",
    "warning_count", "resume_text", "phones", "emails", "error",
}


@pytest.mark.django_db
class TestPrivacy:
    @pytest.fixture
    def with_facts(self, people):
        for profile in people.values():
            ResumeAnalysis.objects.create(
                profile=profile, status=ResumeAnalysis.Status.DONE, source="llm",
                facts={"age": 22, "date_of_birth": "2004-03-12", "cgpa": 9.37, "experience_months": 0,
                       "education_levels": [], "skills": []},
                regex_facts={"age": 22, "cgpa": 9.37, "education_levels": []},
            )
        return people

    @pytest.mark.parametrize("llm_state", ["off", "on"])
    def test_search_results_carry_no_age_dob_resume_cgpa_or_flags(
        self, as_company, with_facts, llm_on, llm_state
    ):
        if llm_state == "on":
            llm_on()
        body = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert body["results"]
        assert not FORBIDDEN_KEYS & set(all_keys(body))
        assert "9.37" not in json.dumps(body)
        assert "2004-03-12" not in json.dumps(body)

    def test_scored_results_carry_none_of_it_either(self, as_company, with_facts):
        ids = [str(p.student_id) for p in with_facts.values()]
        body = post(as_company, SCORE, {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": ids}).json()
        assert len(body["results"]) == 5
        assert not FORBIDDEN_KEYS & set(all_keys(body))
        assert "9.37" not in json.dumps(body)

    def test_the_students_own_match_carries_none_of_it(self, people):

        profile = people["backend_engineer"]
        ResumeAnalysis.objects.create(profile=profile, status="done", facts={"age": 22, "cgpa": 9.37})
        body = post(client_for(profile.user), ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert not FORBIDDEN_KEYS & set(all_keys(body))
        assert "9.37" not in json.dumps(body)


# --- roles --------------------------------------------------------------------------


@pytest.mark.django_db
class TestRoles:
    @pytest.mark.parametrize("name", [SEARCH, SCORE, ME_MATCH])
    def test_unauthenticated_requests_get_401(self, api_client, name):
        assert post(api_client, name, {"jd_text": SAMPLE_JOB_DESCRIPTION}).status_code == 401

    @pytest.mark.parametrize("name", [SEARCH, SCORE])
    def test_a_student_cannot_search_or_score_others(self, as_student, name):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": []}
        assert post(as_student, name, body).status_code == 403

    def test_a_company_has_no_own_match(self, as_company):
        assert post(as_company, ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).status_code == 403

    def test_an_admin_has_no_own_match(self, as_admin):
        assert post(as_admin, ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).status_code == 403


# --- validation ---------------------------------------------------------------------


@pytest.mark.django_db
class TestValidation:
    def test_an_unknown_filter_is_a_400(self, as_company):
        response = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"age": 22}})
        assert response.status_code == 400
        assert "age" in json.dumps(response.json())

    def test_an_unknown_filter_operator_is_a_400(self, as_company):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"experience_months": {"gt": 3}}}
        assert post(as_company, SEARCH, body).status_code == 400

    def test_filters_must_be_an_object(self, as_company):
        assert post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": ["x"]}).status_code == 400

    @pytest.mark.parametrize("name", [SEARCH, SCORE])
    @pytest.mark.parametrize("jd_text", ["", "too short", "x" * 20_001])
    def test_the_jd_text_must_be_30_to_20000_characters(self, as_company, name, jd_text):
        assert post(as_company, name, {"jd_text": jd_text, "student_ids": []}).status_code == 400

    def test_the_students_jd_text_is_bounded_too(self, as_student):
        assert post(as_student, ME_MATCH, {"jd_text": "short"}).status_code == 400

    @pytest.mark.parametrize("k", [0, 51, "lots"])
    def test_k_is_bounded(self, as_company, k):
        assert post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION, "k": k}).status_code == 400

    @pytest.mark.parametrize("field", ["categories", "skills", "department", "batch"])
    def test_an_in_list_of_more_than_20_values_is_a_400(self, as_company, field):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {field: {"in": [f"v{i}" for i in range(21)]}}}
        response = post(as_company, SEARCH, body)
        assert response.status_code == 400
        assert field in response.json()["filters"]

    def test_a_100_000_value_category_list_is_refused_before_any_work(self, as_company):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"categories": {"in": [f"v{i}" for i in range(100_000)]}}}
        assert post(as_company, SEARCH, body).status_code == 400

    @pytest.mark.parametrize("condition", [{"in": ["x" * 101]}, "x" * 101])
    def test_a_filter_value_over_100_characters_is_a_400(self, as_company, condition):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"categories": condition}}
        assert post(as_company, SEARCH, body).status_code == 400

    def test_20_values_of_100_characters_are_accepted(self, as_company):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"skills": {"in": ["x" * 100] * 20}}}
        assert post(as_company, SEARCH, body).status_code == 200

    def test_a_20_value_category_list_costs_no_more_queries_than_one_value(self, as_company, people):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries(values):
            body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"categories": {"in": values}}}
            with CaptureQueriesContext(connection) as ctx:
                assert post(as_company, SEARCH, body).status_code == 200
            return len(ctx.captured_queries)

        queries(["Role 0"])  # warm the per-process caches (the skill graph)
        assert queries([f"Role {i}" for i in range(20)]) == queries(["Role 0"])

    def test_student_ids_must_be_uuids(self, as_company):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": ["220200901"]}
        assert post(as_company, SCORE, body).status_code == 400


# --- the two search paths ------------------------------------------------------------


@pytest.mark.django_db
class TestFallbackSearch:
    """The LLM off (the default): no embedder, the similarity backend scores."""

    def test_the_relevant_samples_outrank_the_irrelevant_ones(self, as_company, people):
        body = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        order = [row["prn"] for row in body["results"]]
        assert set(order[:2]) == {"220200901", "220200904"}
        assert body["fallback"] is True
        assert body["job"]["source"] == "text"

    def test_each_result_has_a_bounded_score_and_its_breakdown(self, as_company, people):
        from matching.engine import get_engine

        for row in post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()["results"]:
            match = row["match"]
            assert 0 <= match["score"] <= 100
            assert set(match["components"]) == {"semantic", "skills", "experience", "education"}
            assert match["semantic_source"] == get_engine().backend_name

    def test_results_are_ranked_best_first_and_cut_to_k(self, as_company, people):
        results = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION, "k": 3}).json()["results"]
        scores = [row["match"]["score"] for row in results]
        assert len(results) == 3
        assert scores == sorted(scores, reverse=True)

    def test_profiles_without_resume_text_are_not_scored(self, as_company, people, make_student):
        make_student(prn="220200991", full_name="No Resume")
        found = keys(post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()["results"])
        assert "220200991" not in found

    def test_the_number_scored_is_capped(self, as_company, people, settings):
        settings.MATCH_SCORE = {**settings.MATCH_SCORE, "FALLBACK_MAX_PROFILES": 2}
        assert len(post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()["results"]) == 2

    def test_filters_apply_in_the_fallback(self, as_company, people):
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"department": "Mechanical"}}
        found = keys(post(as_company, SEARCH, body).json()["results"])
        assert found == {"220200909", "220200910"}

    def test_a_skills_filter_goes_through_the_skill_graph(self, as_company, people):
        ProfileSkill.objects.create(profile=people["frontend_intern"], name="React")
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"skills": "JavaScript"}}
        assert keys(post(as_company, SEARCH, body).json()["results"]) == {"220200905"}

    def test_an_unreachable_llm_also_falls_back(self, as_company, people, llm_on):
        llm_on(FakeLLMClient(down=True))
        body = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert body["fallback"] is True
        assert len(body["results"]) == 5


@pytest.mark.django_db
class TestVectorSearch:
    def test_with_an_embedder_the_store_is_searched_and_scores_use_the_embedding(
        self, as_company, indexed, llm_on
    ):
        llm_on()
        body = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert body["fallback"] is False
        assert body["job"]["source"] == "llm"
        assert {row["match"]["semantic_source"] for row in body["results"]} == {"embedding"}
        order = [row["prn"] for row in body["results"]]
        assert set(order[:2]) == {"220200901", "220200904"}

    def test_the_store_is_over_fetched_three_times_k(self, as_company, indexed, llm_on, monkeypatch):
        llm_on()
        asked = []
        store = get_vector_store()
        original = store.search
        monkeypatch.setattr(store, "search", lambda v, k, m, f=None: asked.append(k) or original(v, k, m, f))
        post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION, "k": 2})
        assert asked == [6]

    def test_filters_are_passed_to_the_store(self, as_company, indexed, llm_on):
        llm_on()
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "filters": {"department": "Mechanical"}}
        assert keys(post(as_company, SEARCH, body).json()["results"]) == {"220200909", "220200910"}

    def test_an_empty_store_falls_back_to_the_backend(self, as_company, people, llm_on):
        llm_on()
        body = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert body["fallback"] is True
        assert len(body["results"]) == 5

    def test_the_jd_requirements_come_from_the_model(self, as_company, indexed, llm_on):
        llm_on(FakeLLMClient(lambda s, u: job_reply(required_skills=["SolidWorks"])))
        body = post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert body["job"]["required_skills"] == ["SolidWorks"]


# --- scoring named profiles -----------------------------------------------------------


@pytest.mark.django_db
class TestScoreNamed:
    def test_named_visible_profiles_are_scored_best_first(self, as_company, people):
        ids = [str(people[k].student_id) for k in ("marketing_executive", "backend_engineer")]
        results = post(as_company, SCORE, {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": ids}).json()["results"]
        assert [row["prn"] for row in results] == ["220200901", "220200910"]

    def test_a_profile_without_a_resume_is_still_scored_on_its_form(self, as_company, make_student):
        profile = make_student(prn="220200991", headline="Django developer")
        ProfileSkill.objects.create(profile=profile, name="Postgres")
        body = {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": [str(profile.student_id)]}
        [row] = post(as_company, SCORE, body).json()["results"]
        assert "PostgreSQL" in row["match"]["matched_skills"]


# --- the student's own match ----------------------------------------------------------


@pytest.mark.django_db
class TestMyMatch:
    def test_a_student_gets_their_own_score_missing_skills_and_breakdown(self, people):

        profile = people["frontend_intern"]
        body = post(client_for(profile.user), ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert 0 <= body["match"]["score"] <= 100
        assert "Django" in body["match"]["missing_skills"]
        assert set(body["match"]["components"]) == {"semantic", "skills", "experience", "education"}
        assert body["job"]["required_skills"]

    def test_a_hidden_student_can_still_match_themselves(self, people):

        profile = people["backend_engineer"]
        profile.visibility = Visibility.HIDDEN
        profile.save()
        response = post(client_for(profile.user), ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION})
        assert response.status_code == 200
        assert response.json()["match"]["score"] >= 80

    def test_with_the_llm_on_the_students_stored_vector_is_used(self, indexed, llm_on):

        llm_on()
        profile = indexed["backend_engineer"]
        body = post(client_for(profile.user), ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).json()
        assert body["match"]["semantic_source"] == "embedding"


# --- throttling -----------------------------------------------------------------------


@pytest.mark.django_db
class TestThrottle:
    @pytest.fixture
    def two_an_hour(self, settings):
        settings.REST_FRAMEWORK = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "matching": "2/hour"},
        }

    def test_the_search_endpoint_is_throttled_per_user(self, as_company, people, two_an_hour, as_admin):
        codes = [post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert post(as_admin, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).status_code == 200

    def test_search_and_score_share_one_budget(self, as_company, two_an_hour):
        post(as_company, SEARCH, {"jd_text": SAMPLE_JOB_DESCRIPTION})
        post(as_company, SCORE, {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": []})
        assert post(as_company, SCORE, {"jd_text": SAMPLE_JOB_DESCRIPTION, "student_ids": []}).status_code == 429

    def test_the_students_match_is_throttled(self, as_student, profile, two_an_hour):
        codes = [post(as_student, ME_MATCH, {"jd_text": SAMPLE_JOB_DESCRIPTION}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]

    def test_resume_analysis_is_throttled_too(self, as_student, profile, two_an_hour):
        codes = [as_student.post(reverse("my-resume-analyze")).status_code for _ in range(3)]
        assert codes == [400, 400, 429]  # no resume: refused, but still counted
