"""Applications: scoping, the company allow-list, status moves, withdraw, resume access."""

import pytest
from django.urls import reverse

from core.models import AuditLog
from opportunities.models import Application
from profiles.models import CompanyShortlist

pytestmark = pytest.mark.django_db

COMPANY_KEYS = {
    "id", "status", "applied_at", "score", "similarity", "eligible", "eligibility_reasons",
    "opportunity", "prn", "full_name", "department", "programme", "school", "batch",
    "year_of_study", "cgpa_at_apply", "skills", "resume_url", "contact", "contact_available",
}


@pytest.fixture
def applied(as_a, make_opportunity):
    opp = make_opportunity()
    response = as_a.post(reverse("opportunity-apply", args=[opp.id]))
    return opp, Application.objects.get(pk=response.data["id"])


class TestScoping:
    def test_each_role_sees_its_own_scope(self, applied, as_a, as_b, as_company, as_nimbus, as_admin):
        count = lambda client: client.get(reverse("application-list")).data["count"]  # noqa: E731
        assert count(as_a) == 1 and count(as_company) == 1 and count(as_admin) == 1
        assert count(as_b) == 0 and count(as_nimbus) == 0

    def test_another_company_or_student_gets_404(self, applied, as_b, as_nimbus):
        _, app = applied
        url = reverse("application-detail", args=[app.id])
        assert as_b.get(url).status_code == 404
        assert as_nimbus.get(url).status_code == 404
        assert as_nimbus.get(reverse("application-resume", args=[app.id])).status_code == 404

    def test_filters_unmatched_prns_and_unknown_parameters(self, applied, as_company):
        url = reverse("application-list")
        assert as_company.get(url, {"prn": "220200990"}).data["count"] == 1
        assert as_company.get(url, {"prn": "220200999"}).data["count"] == 0
        data = as_company.get(url, {"prns": "220200990,220200999"}).data
        assert data["unmatched_prns"] == ["220200999"]
        assert as_company.get(url, {"status": "offer"}).data["count"] == 0
        assert as_company.get(url, {"opportunity": str(applied[0].id)}).data["count"] == 1
        assert as_company.get(url, {"nope": "1"}).status_code == 400

    def test_anonymous_is_401(self, api_client):
        assert api_client.get(reverse("application-list")).status_code == 401


class TestCompanyPayload:
    def test_it_is_exactly_the_allow_list(self, applied, as_company):
        row = as_company.get(reverse("application-list")).data["results"][0]
        assert set(row) == COMPANY_KEYS
        assert row["opportunity"]["title"] == "Backend Engineer"
        assert row["skills"] == ["Python", "Django"] or set(row["skills"]) == {"Python", "Django"}

    def test_contact_is_null_until_the_profile_is_verified(self, applied, as_company, student_a, admin_user):
        row = as_company.get(reverse("application-list")).data["results"][0]
        assert row["contact"] is None and row["contact_available"] is False

        student_a.mark_verified(admin_user)
        row = as_company.get(reverse("application-list")).data["results"][0]
        assert row["contact"] == {"email": student_a.student.email, "phone": student_a.phone}
        assert row["contact_available"] is True

    def test_no_forbidden_key_anywhere(self, applied, as_company):
        text = str(as_company.get(reverse("application-list")).data).lower()
        for forbidden in (
            "confirmed_cgpa", "parsed_cgpa", "recomputed_cgpa", "career_path", "transcript",
            "personal_email", "also_attending", "completion_percent", "marksheet",
        ):
            assert forbidden not in text

    def test_student_payload_adds_events_and_admin_adds_the_student_id(
        self, applied, as_a, as_admin, student_a
    ):
        mine = as_a.get(reverse("application-list")).data["results"][0]
        assert set(mine) == COMPANY_KEYS | {"events"}
        admin_row = as_admin.get(reverse("application-list")).data["results"][0]
        assert set(admin_row) == COMPANY_KEYS | {"profile_student_id"}
        assert admin_row["profile_student_id"] == str(student_a.student_id)


class TestStatusMoves:
    def move(self, client, app, to, **extra):
        return client.post(reverse("application-status", args=[app.id]), {"status": to, **extra}, format="json")

    def test_the_whole_happy_path_writes_events_and_audit(self, applied, as_company):
        _, app = applied
        for to in ("shortlisted", "interview", "offer"):
            assert self.move(as_company, app, to, note="ok").status_code == 200
        app.refresh_from_db()
        assert app.status == "offer"
        assert [e.to_status for e in app.events.all()] == ["applied", "shortlisted", "interview", "offer"]
        assert app.events.last().note == "ok" and app.events.last().actor
        assert AuditLog.objects.filter(action="application_status_changed").count() == 3

    def test_disallowed_transitions_are_400(self, applied, as_company):
        _, app = applied
        for to in ("interview", "offer", "applied", "withdrawn", "bogus"):
            assert self.move(as_company, app, to).status_code == 400
        self.move(as_company, app, "rejected")
        assert self.move(as_company, app, "shortlisted").status_code == 400

    def test_a_student_cannot_move_their_own_application(self, applied, as_a):
        assert self.move(as_a, applied[1], "shortlisted").status_code == 403

    def test_the_other_company_gets_404(self, applied, as_nimbus):
        assert self.move(as_nimbus, applied[1], "shortlisted").status_code == 404

    def test_an_admin_may_move_it(self, applied, as_admin):
        assert self.move(as_admin, applied[1], "shortlisted").status_code == 200

    def test_a_withdrawn_application_cannot_be_moved(self, applied, as_a, as_company):
        _, app = applied
        as_a.post(reverse("application-withdraw", args=[app.id]))
        assert self.move(as_company, app, "shortlisted").status_code == 400


class TestWithdraw:
    def test_withdraw_sets_status_writes_an_event_and_never_deletes(self, applied, as_a):
        _, app = applied
        assert as_a.post(reverse("application-withdraw", args=[app.id])).status_code == 200
        app.refresh_from_db()
        assert app.status == "withdrawn"
        assert app.events.last().to_status == "withdrawn"
        assert AuditLog.objects.filter(action="application_withdrawn").exists()

    def test_withdraw_from_a_final_status_is_400(self, applied, as_a, as_company):
        _, app = applied
        as_company.post(reverse("application-status", args=[app.id]), {"status": "rejected"}, format="json")
        assert as_a.post(reverse("application-withdraw", args=[app.id])).status_code == 400

    def test_only_the_student_who_applied_may_withdraw(self, applied, as_b, as_company):
        _, app = applied
        assert as_b.post(reverse("application-withdraw", args=[app.id])).status_code == 404
        assert as_company.post(reverse("application-withdraw", args=[app.id])).status_code == 403

    def test_withdraw_removes_an_application_grant(self, applied, as_a, company, student_a):
        as_a.post(reverse("application-withdraw", args=[applied[1].id]))
        assert not CompanyShortlist.objects.filter(company=company, profile=student_a).exists()

    def test_withdraw_keeps_a_manual_pick(self, applied, as_a, company, student_a):
        CompanyShortlist.objects.filter(company=company, profile=student_a).update(source="manual")
        as_a.post(reverse("application-withdraw", args=[applied[1].id]))
        assert CompanyShortlist.objects.filter(company=company, profile=student_a).exists()

    def test_withdraw_keeps_the_grant_while_another_application_is_active(
        self, applied, as_a, make_opportunity, company, student_a
    ):
        second = make_opportunity(title="Second role")
        as_a.post(reverse("opportunity-apply", args=[second.id]))
        as_a.post(reverse("application-withdraw", args=[applied[1].id]))
        assert CompanyShortlist.objects.filter(company=company, profile=student_a).exists()


class TestResume:
    def test_the_company_gets_the_snapshot_and_it_is_audited(self, applied, as_company):
        _, app = applied
        response = as_company.get(reverse("application-resume", args=[app.id]))
        assert response.status_code == 200
        assert b"".join(response.streaming_content).startswith(b"%PDF")
        entry = AuditLog.objects.get(action="document_accessed")
        assert entry.target == "220200990" and entry.detail["document"] == "resume_snapshot"

    def test_the_student_reads_their_own_unaudited(self, applied, as_a):
        assert as_a.get(reverse("application-resume", args=[applied[1].id])).status_code == 200
        assert not AuditLog.objects.filter(action="document_accessed").exists()

    def test_the_admin_open_is_audited(self, applied, as_admin):
        assert as_admin.get(reverse("application-resume", args=[applied[1].id])).status_code == 200
        assert AuditLog.objects.filter(action="document_accessed").count() == 1
