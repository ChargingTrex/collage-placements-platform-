"""Stage 3: GET /api/opportunities/suggestions (cut-off, cap, reasons, cache)."""

import pytest
from django.core.cache import cache
from django.urls import reverse

from matching.throttling import MatchingThrottle
from opportunities import scoring
from opportunities.views import OpportunityViewSet

URL = "/api/opportunities/suggestions"


@pytest.fixture(autouse=True)
def _clean_cache():
    """Scores live in the default cache; no test may inherit another's."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def conf(settings):
    def _set(**over):
        settings.SUGGESTIONS = {"MIN_SCORE": 0, "MAX_RESULTS": 20, **over}

    return _set


def ids(response):
    return [r["id"] for r in response.json()["results"]]


def counting_scorer(monkeypatch):
    calls = []
    real = scoring.score_profile

    def counted(profile, job):
        calls.append(1)
        return real(profile, job)

    monkeypatch.setattr(scoring, "score_profile", counted)
    return calls


def test_the_route_is_not_taken_by_the_detail_route():
    assert reverse("opportunity-suggestions") == URL


def test_both_empty_reasons(conf, as_a, make_opportunity):
    conf()
    assert as_a.get(URL).json() == {"results": [], "open_count": 0, "reason": "no_open_postings"}
    make_opportunity()
    conf(MIN_SCORE=101)
    body = as_a.get(URL).json()
    assert body["results"] == [] and body["open_count"] == 1 and body["reason"] == "none_match"
    conf(MIN_SCORE=0)
    assert as_a.get(URL).json()["reason"] is None


def test_settings_cut_off_is_inclusive(conf, as_a, make_opportunity):
    opp = make_opportunity()
    conf()
    score = as_a.get(URL).json()["results"][0]["score"]
    conf(MIN_SCORE=score)
    assert ids(as_a.get(URL)) == [str(opp.id)]
    conf(MIN_SCORE=score + 1)
    assert ids(as_a.get(URL)) == []


def test_a_postings_own_threshold_beats_settings_even_at_zero(conf, as_a, make_opportunity):
    make_opportunity(title="Strict", similarity_threshold=100)
    lax = make_opportunity(title="Lax", similarity_threshold=0)
    conf(MIN_SCORE=101)
    assert ids(as_a.get(URL)) == [str(lax.id)]
    # And the settings bar applies to a posting with no threshold of its own.
    conf(MIN_SCORE=0)
    unset = make_opportunity(title="Unset")
    listed = ids(as_a.get(URL))
    assert str(unset.id) in listed and str(lax.id) in listed
    conf(MIN_SCORE=101)
    assert ids(as_a.get(URL)) == [str(lax.id)]


def test_results_are_capped_and_sorted_best_first(conf, as_a, make_opportunity):
    for n in range(3):
        make_opportunity(title=f"Role {n}")
    make_opportunity(title="Pastry chef", description="Bake bread and plate desserts.", required_skills=[])
    conf(MAX_RESULTS=3)
    body = as_a.get(URL).json()
    scores = [r["score"] for r in body["results"]]
    assert len(scores) == 3 and scores == sorted(scores, reverse=True)
    assert body["open_count"] == 4


def test_unknown_parameter_is_400_and_a_company_is_403(conf, as_a, as_nimbus):
    conf()
    assert as_a.get(URL, {"colour": "red"}).status_code == 400
    assert as_nimbus.get(URL).status_code == 403


def test_the_matching_throttle_is_applied():
    assert MatchingThrottle in OpportunityViewSet.suggestions.kwargs["throttle_classes"]


def test_it_works_with_the_llm_off_and_never_says_probability(conf, as_a, make_opportunity, settings):
    settings.LLM = {**settings.LLM, "ENABLED": False}
    conf()
    make_opportunity()
    response = as_a.get(URL)
    assert response.status_code == 200 and response.json()["results"]
    assert "probab" not in response.content.decode().lower()


def test_a_cached_score_is_not_computed_again_and_the_feed_shares_it(
    conf, as_a, make_opportunity, monkeypatch
):
    conf()
    make_opportunity()
    calls = counting_scorer(monkeypatch)
    as_a.get(URL)
    assert len(calls) == 1
    as_a.get(URL)
    feed = as_a.get(reverse("opportunity-feed"))
    assert feed.status_code == 200
    assert len(calls) == 1


def test_editing_the_posting_invalidates_its_score(conf, as_a, make_opportunity, monkeypatch):
    conf()
    opp = make_opportunity()
    calls = counting_scorer(monkeypatch)
    as_a.get(URL)
    opp.description += " Kubernetes and Terraform too."
    opp.save()
    as_a.get(URL)
    assert len(calls) == 2


def test_a_changed_resume_invalidates_the_score(conf, as_a, student_a, make_opportunity, monkeypatch):
    conf()
    make_opportunity()
    calls = counting_scorer(monkeypatch)
    as_a.get(URL)
    student_a.resume_text += " Also Rust, Kafka and Spark."
    student_a.save()
    as_a.get(URL)
    assert len(calls) == 2
