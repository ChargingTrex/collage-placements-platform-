"""The two notification triggers (D26). Neither scores anyone: eligibility only."""

from __future__ import annotations

import datetime

from django.conf import settings

from accounts.models import Role, Status, User
from notifications.models import Notification
from opportunities.eligibility import check_eligibility
from roster.models import Student


def eligible_students(opportunity):
    """
    `(user, student)` for every student the posting is open to: an account,
    `active`, `is_placement_eligible`, and passing department and roster CGPA.
    """
    users = {
        u.prn: u
        for u in User.objects.filter(role=Role.STUDENT, status=Status.ACTIVE, prn__isnull=False)
    }
    roster = Student.objects.filter(prn__in=list(users), is_placement_eligible=True)
    for student in roster.order_by("prn"):
        if check_eligibility(opportunity, student)[0]:
            yield users[student.prn], student


def _notify(opportunity, kind, users) -> int:
    existing = set(
        Notification.objects.filter(opportunity=opportunity, kind=kind).values_list(
            "recipient_id", flat=True
        )
    )
    fresh = [
        Notification(recipient=user, kind=kind, opportunity=opportunity)
        for user in users
        if user.id not in existing
    ]
    Notification.objects.bulk_create(fresh, ignore_conflicts=True)
    return len(fresh)


def notify_new_opportunity(opportunity) -> int:
    """Trigger 1: the posting just reached `open`."""
    return _notify(
        opportunity, Notification.Kind.NEW_OPPORTUNITY,
        (user for user, _ in eligible_students(opportunity)),
    )


def notify_deadlines(today: datetime.date | None = None) -> int:
    """Trigger 2: `deadline_soon` to eligible students who have not applied."""
    from opportunities.models import Application, Opportunity

    today = today or datetime.date.today()
    horizon = today + datetime.timedelta(days=settings.OPPORTUNITIES["DEADLINE_NOTICE_DAYS"])
    total = 0
    postings = Opportunity.objects.filter(
        status=Opportunity.Status.OPEN, deadline__gte=today, deadline__lte=horizon
    )
    for opportunity in postings:
        applied = set(
            Application.objects.filter(opportunity=opportunity).values_list(
                "profile__user_id", flat=True
            )
        )
        total += _notify(
            opportunity, Notification.Kind.DEADLINE_SOON,
            (user for user, _ in eligible_students(opportunity) if user.id not in applied),
        )
    return total
