"""
"The company's shortlist" (D27), as a queryset condition.

> profiles `visible_to(company)` ∩ (manual rows ∪ profiles with an application
> to one of the company's opportunities at shortlisted, interview or offer)

An application row alone is not a pick: it only grants visibility. Everything
that asks "is this profile on the company's shortlist?" goes through here, so
the Shortlist page, `?shortlisted=true`, `is_shortlisted` and the exports
cannot disagree. This returns the second half (the picks); callers intersect it
with `StudentProfile.objects.visible_to(user)`.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q

from opportunities.models import Application
from profiles.models import CompanyShortlist

#: Application statuses that count as the company having picked the student.
PICK_STATUSES = (
    Application.Status.SHORTLISTED,
    Application.Status.INTERVIEW,
    Application.Status.OFFER,
)


def shortlist_condition(company_id) -> Q:
    """A `Q` on `StudentProfile`: manual rows, or a picked application."""
    manual = CompanyShortlist.objects.filter(
        company=company_id, profile=OuterRef("pk"), source=CompanyShortlist.Source.MANUAL
    )
    picked = Application.objects.filter(
        opportunity__company=company_id, profile=OuterRef("pk"), status__in=PICK_STATUSES
    )
    return Q(Exists(manual)) | Q(Exists(picked))
