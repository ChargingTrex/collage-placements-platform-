"""Applying: the snapshot, the stored score, the shortlist row (D27) and every refusal."""

import datetime

import pytest
from django.urls import reverse

from core.models import AuditLog
from opportunities.models import Application
from profiles.models import CompanyShortlist, Visibility

pytestmark = pytest.mark.django_db


def apply(client, opportunity):
    return client.post(reverse("opportunity-apply", args=[opportunity.id]))


class TestApplyHappyPath:
    def test_apply_creates_the_application_snapshot_score_and_event(
        self, as_a, student_a, make_opportunity
    ):
        opp = make_opportunity()
        response = apply(as_a, opp)
        assert response.status_code == 201, response.content

        app = Application.objects.get()
        assert app.status == "applied" and app.profile == student_a
        assert app.prn == "220200990" and app.full_name == "Test Student A"
        assert app.department == student_a.student.department
        assert str(app.cgpa_at_apply) == "8.72"
        assert 0 < app.score <= 100 and app.eligible is True
        assert app.events.get().to_status == "applied"
        assert app.events.get().from_status == ""
        assert AuditLog.objects.filter(action="application_created").exists()
        # The student's own payload carries the history.
        assert response.data["events"][0]["to_status"] == "applied"

    def test_the_resume_is_copied_to_a_new_path(self, as_a, student_a, make_opportunity):
        apply(as_a, make_opportunity())
        app = Application.objects.get()
        assert app.resume_snapshot.name.startswith("applications/220200990/")
        assert app.resume_snapshot.name != student_a.resume.name
        assert app.resume_snapshot.read() == student_a.resume.read()
        assert app.resume_snapshot_filename == "resume.pdf"

    def test_later_profile_changes_do_not_rewrite_the_snapshot(
        self, as_a, student_a, make_opportunity
    ):
        apply(as_a, make_opportunity())
        student = student_a.student
        student.programme, student.cgpa, student.batch = "MCA", "5.00", 2030
        student.save()
        student_a.resume.delete(save=False)
        student_a.resume = ""
        student_a.save()

        app = Application.objects.get()
        assert app.programme != "MCA" and str(app.cgpa_at_apply) == "8.72" and app.batch == 2026
        assert app.resume_snapshot.read()

    def test_applying_creates_an_application_sourced_shortlist_row(
        self, as_a, student_a, make_opportunity, company
    ):
        apply(as_a, make_opportunity())
        row = CompanyShortlist.objects.get(company=company, profile=student_a)
        assert row.source == "application"

    def test_an_existing_manual_row_is_left_alone(self, as_a, student_a, make_opportunity, company):
        CompanyShortlist.objects.create(company=company, profile=student_a, source="manual", note="keen")
        apply(as_a, make_opportunity())
        row = CompanyShortlist.objects.get(company=company, profile=student_a)
        assert row.source == "manual" and row.note == "keen"

    def test_a_shortlisted_only_student_becomes_visible_to_that_company_alone(
        self, as_a, student_a, make_opportunity, as_company, as_nimbus
    ):
        student_a.visibility = Visibility.SHORTLISTED
        student_a.save()
        url = reverse("company-profile-detail", args=[student_a.student_id])
        assert as_company.get(url).status_code == 404
        apply(as_a, make_opportunity())
        assert as_company.get(url).status_code == 200
        assert as_nimbus.get(url).status_code == 404

    def test_a_hidden_student_may_apply_and_the_company_sees_the_application_only(
        self, as_a, student_a, make_opportunity, as_company
    ):
        student_a.visibility = Visibility.HIDDEN
        student_a.save()
        assert apply(as_a, make_opportunity()).status_code == 201
        # The application is visible to the owner...
        assert as_company.get(reverse("application-list")).data["count"] == 1
        # ...the profile is not, through browse.
        assert as_company.get(reverse("company-profile-detail", args=[student_a.student_id])).status_code == 404
        assert as_company.get(reverse("company-profile-list")).data["count"] == 0


class TestRefusals:
    def reason(self, response):
        assert response.status_code == 400, response.content
        return response.data["reason"]

    def test_not_open(self, as_a, make_opportunity):
        # A posting that closed after the student saw it, or one that never
        # opened, is "not open" rather than a 404 (ids are unguessable UUIDs).
        for status in ("closed", "draft", "pending_review"):
            assert self.reason(apply(as_a, make_opportunity(status=status))) == "not_open"
        assert as_a.post(reverse("opportunity-apply", args=["00000000-0000-0000-0000-000000000000"])).status_code == 404

    def test_deadline_passed(self, as_a, make_opportunity):
        late = make_opportunity(deadline=datetime.date.today() - datetime.timedelta(days=1))
        assert self.reason(apply(as_a, late)) == "deadline_passed"

    def test_the_deadline_day_itself_is_still_open(self, as_a, make_opportunity):
        assert apply(as_a, make_opportunity(deadline=datetime.date.today())).status_code == 201

    def test_already_applied(self, as_a, make_opportunity):
        opp = make_opportunity()
        apply(as_a, opp)
        assert self.reason(apply(as_a, opp)) == "already_applied"
        assert Application.objects.count() == 1

    def test_a_withdrawn_application_still_counts_as_applied(self, as_a, make_opportunity):
        opp = make_opportunity()
        app_id = apply(as_a, opp).data["id"]
        as_a.post(reverse("application-withdraw", args=[app_id]))
        assert self.reason(apply(as_a, opp)) == "already_applied"

    def test_no_resume(self, make_applicant, make_opportunity):
        from opportunities.tests.conftest import client_for

        bare = make_applicant("220200992", resume_text=None)
        assert self.reason(apply(client_for(bare.user), make_opportunity())) == "no_resume"

    def test_not_eligible_on_department(self, as_a, make_opportunity):
        opp = make_opportunity(eligible_departments=["Mechanical Engineering"])
        response = apply(as_a, opp)
        assert self.reason(response) == "not_eligible"
        assert "department" in response.data["detail"].lower()

    def test_not_eligible_on_roster_cgpa(self, as_a, make_opportunity):
        assert self.reason(apply(as_a, make_opportunity(min_cgpa="9.00"))) == "not_eligible"

    def test_a_cgpa_the_student_typed_does_not_help(self, as_b, student_b, make_opportunity):
        student_b.confirmed_cgpa = "9.90"
        student_b.save()
        assert self.reason(apply(as_b, make_opportunity(min_cgpa="8.00"))) == "not_eligible"

    def test_a_null_roster_cgpa_fails_a_cutoff_but_passes_without_one(
        self, make_applicant, make_opportunity
    ):
        from opportunities.tests.conftest import client_for

        nocgpa = make_applicant("220200993", cgpa=None)
        client = client_for(nocgpa.user)
        assert self.reason(apply(client, make_opportunity(min_cgpa="5.00"))) == "not_eligible"
        assert apply(client, make_opportunity(min_cgpa=None)).status_code == 201

    def test_eligible_department_by_either_name_and_any_case(self, as_a, make_opportunity):
        opp = make_opportunity(eligible_departments=["computer engineering"])
        assert apply(as_a, opp).status_code == 201

    def test_experience_and_education_never_block_applying(self, as_a, make_opportunity):
        opp = make_opportunity(min_experience_years="9", required_education_levels=["PG"])
        assert apply(as_a, opp).status_code == 201

    def test_only_students_apply(self, as_company, as_admin, make_opportunity):
        opp = make_opportunity()
        assert apply(as_company, opp).status_code == 403
        assert apply(as_admin, opp).status_code == 403

    def test_a_refusal_leaves_no_shortlist_row(self, as_a, make_opportunity, company):
        apply(as_a, make_opportunity(min_cgpa="9.90"))
        assert not CompanyShortlist.objects.filter(company=company).exists()


class TestScoreAndFeed:
    def test_a_matching_resume_scores_above_a_mismatched_one_and_both_are_shown(
        self, as_a, as_b, make_opportunity
    ):
        make_opportunity(eligible_departments=["Computer Engineering"])
        a_row = as_a.get(reverse("opportunity-feed")).data["results"][0]
        b_row = as_b.get(reverse("opportunity-feed")).data["results"][0]
        assert a_row["eligible"] is True and b_row["eligible"] is False
        assert b_row["eligibility_reasons"]
        # The score is computed and shown whatever the eligibility.
        assert a_row["score"] > b_row["score"]
        for key in ("components", "matched_skills", "missing_skills", "has_applied", "application_status"):
            assert key in a_row

    def test_the_feed_is_ordered_by_score_and_open_unexpired_only(self, as_a, make_opportunity):
        good = make_opportunity(title="Backend")
        poor = make_opportunity(
            title="Pastry", description="Bake bread and pastries in a busy kitchen.",
            required_skills=["baking"],
        )
        make_opportunity(title="Draft", status="draft")
        make_opportunity(title="Late", deadline=datetime.date.today() - datetime.timedelta(days=1))
        rows = as_a.get(reverse("opportunity-feed")).data["results"]
        assert [r["id"] for r in rows] == [str(good.id), str(poor.id)]

    def test_the_feed_marks_what_was_applied_for(self, as_a, make_opportunity):
        opp = make_opportunity()
        apply(as_a, opp)
        row = as_a.get(reverse("opportunity-feed")).data["results"][0]
        assert row["has_applied"] is True and row["application_status"] == "applied"

    def test_feed_is_student_only_and_filterable(self, as_a, as_company, make_opportunity):
        make_opportunity(role_type="internship", title="Intern")
        make_opportunity(role_type="full_time")
        assert as_company.get(reverse("opportunity-feed")).status_code == 403
        assert as_a.get(reverse("opportunity-feed"), {"role_type": "internship"}).data["count"] == 1
        assert as_a.get(reverse("opportunity-feed"), {"bogus": "1"}).status_code == 400

    def test_the_stored_score_is_the_one_shown_at_apply(self, as_a, make_opportunity):
        opp = make_opportunity()
        shown = as_a.get(reverse("opportunity-feed")).data["results"][0]["score"]
        apply(as_a, opp)
        assert Application.objects.get().score == shown

    def test_scores_are_cached_per_resume_opportunity_and_update(
        self, as_a, student_a, make_opportunity, monkeypatch
    ):
        from matching.engine import MatchingEngine

        calls = []
        real = MatchingEngine.match_score

        def counting(self, *args, **kwargs):
            calls.append(1)
            return real(self, *args, **kwargs)

        monkeypatch.setattr(MatchingEngine, "match_score", counting)
        opp = make_opportunity()
        as_a.get(reverse("opportunity-feed"))
        as_a.get(reverse("opportunity-feed"))
        assert len(calls) == 1

        # Editing the posting changes updated_at, so it is scored afresh.
        opp.title = "Backend Engineer II"
        opp.save()
        as_a.get(reverse("opportunity-feed"))
        assert len(calls) == 2

        # A new resume is a new key.
        student_a.resume_text += " Also knows Kubernetes."
        student_a.save()
        as_a.get(reverse("opportunity-feed"))
        assert len(calls) == 3
