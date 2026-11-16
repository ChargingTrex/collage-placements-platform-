"""`seed_demo --with-students`: the reset-safe demo (plan step 1f)."""

from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import User
from profiles.models import CompanyShortlist, ExperienceEntry, ProjectEntry, StudentProfile

pytestmark = pytest.mark.django_db

PUBLIC_A, PUBLIC_B, SHORTLISTED, HIDDEN = "220200901", "220200904", "220200903", "220200902"
COMPANY_A = ("recruiter@acmetech.example", "CompanyPass!234")
COMPANY_B = ("talent@nimbusanalytics.example", "CompanyPass!234")


@pytest.fixture(autouse=True)
def _upload_dir(settings, tmp_path):
    # The seed stores resumes; keep them out of the developer's media folder.
    settings.MEDIA_ROOT = tmp_path


def seed(*flags):
    out = StringIO()
    call_command("seed_demo", *flags, stdout=out, stderr=StringIO())
    return out.getvalue()


def login(email, password):
    client = APIClient()
    response = client.post("/api/auth/login", {"identifier": email, "password": password}, format="json")
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['tokens']['access']}")
    return client


def visible_prns(client):
    response = client.get("/api/profiles/students")
    assert response.status_code == 200
    return {row["prn"] for row in response.data["results"]}


def test_the_default_seed_creates_no_students():
    seed()
    assert not StudentProfile.objects.exists()


def test_the_flag_creates_four_complete_students_who_can_log_in():
    output = seed("--with-students")

    assert StudentProfile.objects.count() == 4
    for profile in StudentProfile.objects.select_related("user", "student"):
        assert profile.user.is_active and profile.user.email_verified_at
        assert profile.skills.count() >= 2
        assert profile.experience_entries.count() >= 1
        assert profile.projects.count() == 2
        # The resume went through the matching engine, not just a file save.
        assert profile.has_resume and profile.parsed_experience_years is not None
        login(profile.student.email, "StudentPass!234")
        assert f"{profile.prn} / {profile.student.email} / StudentPass!234" in output


def test_running_the_seed_twice_creates_no_duplicates():
    seed("--with-students")
    counts = lambda: (  # noqa: E731
        User.objects.count(), StudentProfile.objects.count(),
        ExperienceEntry.objects.count(), ProjectEntry.objects.count(),
        CompanyShortlist.objects.count(),
        sum(p.skills.count() for p in StudentProfile.objects.all()),
    )
    first = counts()
    seed("--with-students")
    assert counts() == first


def test_the_visibility_spread_is_two_public_one_shortlisted_one_hidden():
    seed("--with-students")
    by_prn = {p.prn: p for p in StudentProfile.objects.all()}

    assert [by_prn[p].visibility for p in (PUBLIC_A, PUBLIC_B, SHORTLISTED, HIDDEN)] == [
        "all", "all", "shortlisted", "hidden",
    ]
    assert by_prn[PUBLIC_A].is_verified and by_prn[PUBLIC_B].is_verified
    assert by_prn[SHORTLISTED].is_verified
    assert not by_prn[HIDDEN].is_verified


def test_companies_see_what_each_visibility_setting_promises():
    seed("--with-students")

    # The first company shortlisted the third student while they were public,
    # so it keeps seeing them; the second company never did.
    assert visible_prns(login(*COMPANY_A)) == {PUBLIC_A, PUBLIC_B, SHORTLISTED}
    assert visible_prns(login(*COMPANY_B)) == {PUBLIC_A, PUBLIC_B}
    assert CompanyShortlist.objects.filter(profile__student__prn=SHORTLISTED).count() == 1


def test_the_pilot_officer_is_a_placement_admin_with_their_own_admin_id():
    output = seed()

    shared = User.objects.get(email="placement.officer@college.edu")
    pilot = User.objects.get(email="pilot.officer@college.edu")
    assert pilot.is_placement_admin and pilot.may_log_in
    assert pilot.admin_id.startswith("ADM-") and pilot.admin_id != shared.admin_id
    assert pilot.full_name

    # Signs in with the documented password, and the seed prints both it and
    # the ADM- id it was issued, so the officer can be told which they are.
    client = login("pilot.officer@college.edu", "PilotPass!234")
    assert client.get("/api/auth/admin/users").status_code == 200
    assert f"pilot.officer@college.edu / PilotPass!234  ({pilot.admin_id})" in output


def test_re_seeding_keeps_the_pilot_officers_admin_id():
    seed()
    issued = User.objects.get(email="pilot.officer@college.edu").admin_id
    seed()
    assert User.objects.get(email="pilot.officer@college.edu").admin_id == issued


# --- opportunities, applications, notifications (Phase B) ---------------------


def test_postings_exist_in_every_status_for_both_companies_without_students():
    from accounts.models import Company
    from opportunities.models import Opportunity

    seed()
    for company in Company.objects.all():
        mine = Opportunity.objects.filter(company=company)
        assert set(mine.values_list("status", flat=True)) == {s.value for s in Opportunity.Status}
    assert Opportunity.objects.filter(status="open", salary_disclosed=True, salary_min__isnull=False).exists()
    assert Opportunity.objects.filter(status="open", salary_disclosed=False, salary_min__isnull=True).exists()
    assert not Opportunity.objects.filter(status__in=["open", "closed"], approved_by=None).exists()


def test_students_have_applications_in_every_status_with_events_and_notifications():
    from notifications.models import Notification
    from opportunities.models import Application, ApplicationEvent

    seed("--with-students")
    assert {a.status for a in Application.objects.all()} == {s.value for s in Application.Status}
    for application in Application.objects.all():
        events = list(application.events.all())
        assert events[0].from_status == "" and events[0].to_status == "applied"
        assert events[-1].to_status == application.status
        assert application.resume_snapshot and application.cgpa_at_apply is not None
    assert Notification.objects.exists()
    assert ApplicationEvent.objects.count() > Application.objects.count()


def test_seeded_postings_are_visible_through_the_api():
    seed("--with-students")
    student = login("aarav.mehta@college.edu", "StudentPass!234")
    feed = student.get("/api/opportunities/feed").json()
    assert {r["title"] for r in feed["results"]} >= {"Backend Engineer", "Data Analyst"}
    mine = student.get("/api/opportunities/applications").json()
    assert mine["count"] >= 3
    unread = student.get("/api/notifications/", {"unread": "true"}).json()
    assert unread["count"] >= 1


def test_re_seeding_changes_no_opportunity_application_event_notification_or_audit_row():
    from core.models import AuditLog
    from notifications.models import Notification
    from opportunities.models import Application, ApplicationEvent, Opportunity

    seed("--with-students")
    counts = lambda: (  # noqa: E731
        Opportunity.objects.count(), Application.objects.count(),
        ApplicationEvent.objects.count(), Notification.objects.count(), AuditLog.objects.count(),
        sorted(Opportunity.objects.values_list("status", "deadline")),
        sorted(Application.objects.values_list("status", "score")),
    )
    first = counts()
    seed("--with-students")
    assert counts() == first


def test_applying_to_one_company_never_shows_a_shortlisted_only_student_to_the_other():
    seed("--with-students")
    assert SHORTLISTED not in visible_prns(login(*COMPANY_B))
