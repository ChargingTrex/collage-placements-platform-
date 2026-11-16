"""Notification triggers and API (D26). Synthetic people only."""

import datetime
from io import StringIO

import pytest
from django.core.management import call_command

from notifications.models import Notification
from notifications.services import notify_deadlines, notify_new_opportunity

pytestmark = pytest.mark.django_db


def test_new_opportunity_goes_to_each_eligible_student_once(make_opportunity, student_a, student_b):
    posting = make_opportunity(eligible_departments=["B.Tech Computer Science"], min_cgpa="7.00")

    assert notify_new_opportunity(posting) == 1
    assert notify_new_opportunity(posting) == 0  # idempotent
    note = Notification.objects.get()
    assert note.recipient_id == student_a.user_id and note.kind == "new_opportunity"
    assert note.read_at is None


def test_a_suspended_or_ineligible_student_is_skipped(make_opportunity, student_a, student_b):
    student_a.user.set_status("suspended")
    student_b.student.is_placement_eligible = False
    student_b.student.save()
    assert notify_new_opportunity(make_opportunity(eligible_departments=[])) == 0


def test_deadline_notices_skip_applicants_far_postings_and_repeat_runs(
    make_opportunity, student_a, student_b, as_a
):
    soon = make_opportunity(
        title="Soon", deadline=datetime.date.today() + datetime.timedelta(days=1), eligible_departments=[]
    )
    make_opportunity(title="Far", deadline=datetime.date.today() + datetime.timedelta(days=60))
    assert as_a.post(f"/api/opportunities/{soon.id}/apply").status_code == 201

    assert notify_deadlines() == 1  # student B only: A applied
    assert notify_deadlines() == 0
    assert list(Notification.objects.values_list("recipient_id", "opportunity_id")) == [
        (student_b.user_id, soon.id)
    ]


def test_the_command_reports_what_it_sent(make_opportunity, student_a):
    make_opportunity(
        deadline=datetime.date.today() + datetime.timedelta(days=1), eligible_departments=[]
    )
    out = StringIO()
    call_command("notify_deadlines", stdout=out)
    assert "1 deadline notification(s) sent." in out.getvalue()
    call_command("notify_deadlines", stdout=out)
    assert "0 deadline notification(s) sent." in out.getvalue()


def test_read_marks_one_and_read_all_marks_the_rest(make_opportunity, student_a, as_a):
    for title in ("One", "Two"):
        notify_new_opportunity(make_opportunity(title=title, eligible_departments=[]))
    rows = as_a.get("/api/notifications/").json()["results"]
    assert len(rows) == 2

    assert as_a.post(f"/api/notifications/{rows[0]['id']}/read").status_code == 204
    assert as_a.get("/api/notifications/", {"unread": "true"}).json()["count"] == 1
    assert as_a.post("/api/notifications/read-all").status_code == 204
    assert as_a.get("/api/notifications/", {"unread": "true"}).json()["count"] == 0
