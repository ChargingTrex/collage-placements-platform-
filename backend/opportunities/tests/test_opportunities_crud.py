"""Postings: ownership, the approval gate, visibility and the edit rules."""

import datetime

import pytest
from django.urls import reverse

from core.models import AuditLog
from opportunities.models import Opportunity

pytestmark = pytest.mark.django_db

FUTURE = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()


def payload(**over):
    body = {
        "title": "Data Analyst",
        "description": "Build dashboards with SQL, Python and pandas.",
        "role_type": "full_time",
        "required_skills": ["Python", "Node.js"],
        "deadline": FUTURE,
    }
    body.update(over)
    return body


class TestCreate:
    def test_a_recruiter_creates_a_draft_for_their_company(self, as_company, company):
        response = as_company.post(reverse("opportunity-list"), payload(), format="json")
        assert response.status_code == 201, response.content
        assert response.data["status"] == "draft"
        opp = Opportunity.objects.get(pk=response.data["id"])
        assert opp.company == company
        assert AuditLog.objects.filter(action="opportunity_created").exists()

    def test_a_recruiter_cannot_pick_another_company(self, as_company, nimbus, company):
        response = as_company.post(
            reverse("opportunity-list"), payload(company=str(nimbus.id)), format="json"
        )
        assert response.status_code == 201
        assert Opportunity.objects.get(pk=response.data["id"]).company == company

    def test_skills_are_stored_slugged(self, as_company):
        response = as_company.post(reverse("opportunity-list"), payload(), format="json")
        assert response.data["required_skills"] == ["python", "nodejs"]

    def test_an_admin_must_name_the_company_and_the_posting_opens_at_once(
        self, as_admin, company, admin_user
    ):
        missing = as_admin.post(reverse("opportunity-list"), payload(), format="json")
        assert missing.status_code == 400

        response = as_admin.post(
            reverse("opportunity-list"), payload(company=str(company.id)), format="json"
        )
        assert response.status_code == 201, response.content
        opp = Opportunity.objects.get(pk=response.data["id"])
        assert opp.status == "open" and opp.approved_by == admin_user

    def test_salary_max_may_not_be_below_min(self, as_company):
        response = as_company.post(
            reverse("opportunity-list"),
            payload(salary_disclosed=True, salary_min=50000, salary_max=40000, salary_period="month"),
            format="json",
        )
        assert response.status_code == 400

    def test_undisclosed_salary_is_stored_as_null(self, as_company):
        response = as_company.post(
            reverse("opportunity-list"),
            payload(salary_disclosed=False, salary_min=50000, salary_max=60000, salary_period="month"),
            format="json",
        )
        assert response.status_code == 201
        assert response.data["salary_min"] is None and response.data["salary_max"] is None

    def test_a_student_cannot_create(self, as_a):
        assert as_a.post(reverse("opportunity-list"), payload(), format="json").status_code == 403

    def test_a_recruiter_without_a_company_is_refused(self, lonely_recruiter):
        from opportunities.tests.conftest import client_for

        client = client_for(lonely_recruiter)
        assert client.post(reverse("opportunity-list"), payload(), format="json").status_code == 403
        assert client.get(reverse("opportunity-list")).status_code == 403

    def test_anonymous_is_401(self, api_client):
        assert api_client.get(reverse("opportunity-list")).status_code == 401


class TestVisibility:
    def test_students_see_only_open_postings(self, as_a, make_opportunity):
        open_opp = make_opportunity(status="open")
        for status in ("draft", "pending_review", "rejected", "closed"):
            make_opportunity(status=status)
        response = as_a.get(reverse("opportunity-list"))
        assert [row["id"] for row in response.data["results"]] == [str(open_opp.id)]

    def test_a_student_gets_404_for_a_pending_posting(self, as_a, make_opportunity):
        pending = make_opportunity(status="pending_review")
        assert as_a.get(reverse("opportunity-detail", args=[pending.id])).status_code == 404

    def test_a_recruiter_sees_all_their_statuses_and_nobody_elses(
        self, as_company, make_opportunity, nimbus
    ):
        mine = [make_opportunity(status=s) for s in ("draft", "open", "closed")]
        theirs = make_opportunity(company=nimbus, status="open")
        response = as_company.get(reverse("opportunity-list"))
        ids = {row["id"] for row in response.data["results"]}
        assert ids == {str(o.id) for o in mine}
        assert as_company.get(reverse("opportunity-detail", args=[theirs.id])).status_code == 404

    def test_a_recruiter_cannot_edit_delete_or_submit_another_companys_posting(
        self, as_company, make_opportunity, nimbus
    ):
        theirs = make_opportunity(company=nimbus, status="draft")
        url = reverse("opportunity-detail", args=[theirs.id])
        assert as_company.patch(url, {"title": "x"}, format="json").status_code == 404
        assert as_company.delete(url).status_code == 404
        assert as_company.post(reverse("opportunity-submit", args=[theirs.id])).status_code == 404

    def test_an_admin_sees_everything(self, as_admin, make_opportunity, nimbus):
        make_opportunity(status="draft")
        make_opportunity(company=nimbus, status="pending_review")
        assert as_admin.get(reverse("opportunity-list")).data["count"] == 2

    def test_filters_and_unknown_parameters(self, as_admin, make_opportunity):
        make_opportunity(status="open", role_type="internship", title="Frontend Intern")
        make_opportunity(status="draft", title="Backend")
        url = reverse("opportunity-list")
        assert as_admin.get(url, {"role_type": "internship"}).data["count"] == 1
        assert as_admin.get(url, {"status": "draft"}).data["count"] == 1
        assert as_admin.get(url, {"search": "Frontend"}).data["count"] == 1
        assert as_admin.get(url, {"bogus": "1"}).status_code == 400


class TestEditRules:
    def test_a_recruiter_edits_a_draft_but_not_an_open_posting(self, as_company, make_opportunity):
        draft = make_opportunity(status="draft")
        assert as_company.patch(
            reverse("opportunity-detail", args=[draft.id]), {"title": "New"}, format="json"
        ).status_code == 200
        opened = make_opportunity(status="open")
        response = as_company.patch(
            reverse("opportunity-detail", args=[opened.id]), {"title": "New"}, format="json"
        )
        assert response.status_code == 400

    def test_a_recruiter_may_edit_a_rejected_posting(self, as_company, make_opportunity):
        rejected = make_opportunity(status="rejected", rejection_reason="Add a salary")
        response = as_company.patch(
            reverse("opportunity-detail", args=[rejected.id]), {"title": "Fixed"}, format="json"
        )
        assert response.status_code == 200

    def test_status_is_not_writable(self, as_company, make_opportunity):
        draft = make_opportunity(status="draft")
        as_company.patch(
            reverse("opportunity-detail", args=[draft.id]), {"status": "open"}, format="json"
        )
        draft.refresh_from_db()
        assert draft.status == "draft"

    def test_an_admin_edits_any_status_but_closed(self, as_admin, make_opportunity):
        opened = make_opportunity(status="open")
        closed = make_opportunity(status="closed")
        assert as_admin.patch(
            reverse("opportunity-detail", args=[opened.id]), {"title": "Edited"}, format="json"
        ).status_code == 200
        assert as_admin.patch(
            reverse("opportunity-detail", args=[closed.id]), {"title": "Edited"}, format="json"
        ).status_code == 400

    def test_only_drafts_can_be_deleted(self, as_company, make_opportunity):
        draft = make_opportunity(status="draft")
        opened = make_opportunity(status="open")
        assert as_company.delete(reverse("opportunity-detail", args=[opened.id])).status_code == 400
        assert as_company.delete(reverse("opportunity-detail", args=[draft.id])).status_code == 204
        assert not Opportunity.objects.filter(pk=draft.pk).exists()


class TestLifecycle:
    def test_submit_approve_close(self, as_company, as_admin, make_opportunity, as_a):
        opp = make_opportunity(status="draft")
        assert as_company.post(reverse("opportunity-submit", args=[opp.id])).status_code == 200
        opp.refresh_from_db()
        assert opp.status == "pending_review" and opp.submitted_at

        # Not visible to students until approved.
        assert as_a.get(reverse("opportunity-detail", args=[opp.id])).status_code == 404

        assert as_admin.post(reverse("opportunity-approve", args=[opp.id])).status_code == 200
        opp.refresh_from_db()
        assert opp.status == "open" and opp.approved_at and opp.approved_by
        assert as_a.get(reverse("opportunity-detail", args=[opp.id])).status_code == 200

        assert as_company.post(reverse("opportunity-close", args=[opp.id])).status_code == 200
        opp.refresh_from_db()
        assert opp.status == "closed"
        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert {"opportunity_submitted", "opportunity_approved", "opportunity_closed"} <= actions

    def test_transitions_from_the_wrong_state_are_400(self, as_company, as_admin, make_opportunity):
        opened = make_opportunity(status="open")
        draft = make_opportunity(status="draft")
        assert as_company.post(reverse("opportunity-submit", args=[opened.id])).status_code == 400
        assert as_admin.post(reverse("opportunity-approve", args=[draft.id])).status_code == 400
        assert as_company.post(reverse("opportunity-close", args=[draft.id])).status_code == 400

    def test_reject_needs_a_reason_and_may_be_resubmitted(
        self, as_company, as_admin, make_opportunity
    ):
        opp = make_opportunity(status="pending_review")
        url = reverse("opportunity-reject", args=[opp.id])
        assert as_admin.post(url, {}, format="json").status_code == 400
        assert as_admin.post(url, {"reason": "Add the salary"}, format="json").status_code == 200
        opp.refresh_from_db()
        assert opp.status == "rejected" and opp.rejection_reason == "Add the salary"
        assert as_company.post(reverse("opportunity-submit", args=[opp.id])).status_code == 200

    def test_approve_and_reject_are_admin_only(self, as_company, as_a, make_opportunity):
        opp = make_opportunity(status="pending_review")
        for client in (as_company, as_a):
            assert client.post(reverse("opportunity-approve", args=[opp.id])).status_code == 403
            assert client.post(
                reverse("opportunity-reject", args=[opp.id]), {"reason": "x"}, format="json"
            ).status_code == 403

    def test_a_student_cannot_see_review_fields(self, as_a, make_opportunity):
        opp = make_opportunity(status="open", rejection_reason="internal")
        data = as_a.get(reverse("opportunity-detail", args=[opp.id])).data
        assert "rejection_reason" not in data and "approved_by" not in data
        assert "created_by" not in data
