"""Screen, the applicants CSV, admin stats and the feed. Synthetic people only."""

import csv
import io

import pytest

from core.models import AuditLog
from opportunities.tests.conftest import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_admin(admin_user):
    return client_for(admin_user)


@pytest.fixture
def as_acme(company_user):
    return client_for(company_user)


@pytest.fixture
def pool(make_opportunity, student_a, student_b, as_a, as_b):
    """A posting with two applicants: A is a backend match, B a pastry chef."""
    posting = make_opportunity(eligible_departments=[], min_cgpa=None)
    assert as_a.post(f"/api/opportunities/{posting.id}/apply").status_code == 201
    assert as_b.post(f"/api/opportunities/{posting.id}/apply").status_code == 201
    return posting


def screen(client, posting, **body):
    response = client.post(f"/api/opportunities/{posting.id}/screen", body, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def test_a_zero_threshold_shortlists_everyone_who_passes_the_filters(as_admin, pool):
    result = screen(as_admin, pool, threshold=0, min_experience_years=0)
    assert {r["prn"] for r in result["shortlisted"]} == {"220200990", "220200991"}
    assert result["below_threshold"] == [] and result["filtered_out"] == []


def test_the_cut_is_made_on_the_score_each_row_shows(as_admin, pool):
    result = screen(as_admin, pool, threshold=1, min_experience_years=0)
    assert all(r["score"] >= 1 for r in result["shortlisted"])
    assert all(r["score"] < 1 for r in result["below_threshold"])
    ranked = [r["score"] for r in result["shortlisted"]]
    assert ranked == sorted(ranked, reverse=True)


def test_the_experience_filter_moves_the_applicant_to_filtered_out_with_a_reason(as_admin, pool):
    result = screen(as_admin, pool, threshold=0, min_experience_years=5)
    assert result["shortlisted"] == []
    assert len(result["filtered_out"]) == 2
    assert "5 years of experience" in result["filtered_out"][0]["reasons"][0]


def test_the_request_wins_over_the_posting_which_wins_over_settings(
    as_admin, make_opportunity, student_a, as_a
):
    posting = make_opportunity(eligible_departments=[], min_cgpa=None, min_experience_years="9.0")
    as_a.post(f"/api/opportunities/{posting.id}/apply")
    assert len(screen(as_admin, posting, threshold=0)["filtered_out"]) == 1  # the posting's 9 years
    assert len(screen(as_admin, posting, threshold=0, min_experience_years=0)["shortlisted"]) == 1


def test_a_withdrawn_applicant_is_not_screened(as_admin, pool, as_a):
    application = as_a.get("/api/opportunities/applications").json()["results"][0]
    as_a.post(f"/api/opportunities/applications/{application['id']}/withdraw")
    result = screen(as_admin, pool, threshold=0, min_experience_years=0)
    assert len(result["shortlisted"]) == 1


def test_a_threshold_out_of_range_is_400(as_admin, pool):
    response = as_admin.post(f"/api/opportunities/{pool.id}/screen", {"threshold": 101}, format="json")
    assert response.status_code == 400


def test_the_csv_is_prn_first_blank_for_unverified_contacts_and_audited(as_acme, pool):
    before = AuditLog.objects.filter(action="applications_exported").count()
    response = as_acme.get(f"/api/opportunities/{pool.id}/applicants/export")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    assert list(rows[0])[0] == "prn" and len(rows) == 2
    assert rows[0]["score"] >= rows[1]["score"] or int(rows[0]["score"]) >= int(rows[1]["score"])
    assert all(r["email"] == "" and r["contact_available"] == "false" for r in rows)
    assert AuditLog.objects.filter(action="applications_exported").count() == before + 1


def test_a_name_that_starts_like_a_formula_is_defused_in_the_csv(as_acme, pool, student_a):
    pool.applications.update(full_name="=HYPERLINK(\"x\")")
    text = as_acme.get(f"/api/opportunities/{pool.id}/applicants/export").content.decode()
    assert "\"'=HYPERLINK" in text or ",'=HYPERLINK" in text


def test_stats_count_by_status_and_list_postings_nobody_applied_to(as_admin, pool, make_opportunity):
    make_opportunity(title="Quiet", eligible_departments=[])
    stats = as_admin.get("/api/opportunities/stats").json()
    assert stats["opportunities_by_status"]["open"] == 2
    assert stats["applications_by_status"] == {"applied": 2}
    by_title = {r["title"]: r for r in stats["per_opportunity"]}
    assert by_title["Quiet"]["applicants"] == 0 and by_title["Backend Engineer"]["applicants"] == 2
    assert stats["median_hours_to_shortlist"] is None


def test_the_feed_ranks_by_score_and_flags_eligibility_without_changing_the_score(
    make_opportunity, student_a, student_b, as_b
):
    make_opportunity(title="Open to all", eligible_departments=[], min_cgpa=None)
    make_opportunity(title="CS only", eligible_departments=["B.Tech Computer Science"], min_cgpa="9.00")
    rows = as_b.get("/api/opportunities/feed").json()["results"]
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    by_title = {r["title"]: r for r in rows}
    assert by_title["Open to all"]["eligible"] is True
    restricted = by_title["CS only"]
    assert restricted["eligible"] is False and restricted["eligibility_reasons"]
    assert restricted["has_applied"] is False and restricted["application_status"] is None
