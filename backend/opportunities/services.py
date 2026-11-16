"""Apply, withdraw and status moves. Views stay thin; the rules live here."""

from __future__ import annotations

import datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from core.models import AuditLog
from opportunities.eligibility import check_eligibility
from opportunities.models import Application, ApplicationEvent, Opportunity
from opportunities.scoring import score_for
from profiles.models import CompanyShortlist

# Statuses a company may move an application to, from each status.
TRANSITIONS = {
    Application.Status.APPLIED: {Application.Status.SHORTLISTED, Application.Status.REJECTED},
    Application.Status.SHORTLISTED: {Application.Status.INTERVIEW, Application.Status.REJECTED},
    Application.Status.INTERVIEW: {Application.Status.OFFER, Application.Status.REJECTED},
}
# A student may withdraw until a decision is final.
WITHDRAWABLE = {
    Application.Status.APPLIED, Application.Status.SHORTLISTED, Application.Status.INTERVIEW,
}
# Statuses where an application still keeps its company able to see the student.
LIVE = set(Application.Status) - {Application.Status.WITHDRAWN}


class ApplyRefused(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason, self.detail = reason, detail


class BadTransition(Exception):
    pass


def has_active_application(company, profile) -> bool:
    """Whether the student has a non-withdrawn application to this company."""
    return Application.objects.filter(
        opportunity__company=company, profile=profile, status__in=LIVE
    ).exists()


def _event(application, actor, from_status, to_status, note=""):
    ApplicationEvent.objects.create(
        application=application, actor=actor, from_status=from_status,
        to_status=to_status, note=note,
    )


def apply(opportunity: Opportunity, profile, actor) -> Application:
    """Create the application, or raise `ApplyRefused` with a reason code."""
    student = profile.student

    if opportunity.status != Opportunity.Status.OPEN:
        raise ApplyRefused("not_open", "This posting is not open for applications.")
    if opportunity.deadline < datetime.date.today():
        raise ApplyRefused("deadline_passed", "The deadline for this posting has passed.")
    # Withdrawn applications count: the unique constraint allows one per pair.
    if Application.objects.filter(opportunity=opportunity, profile=profile).exists():
        raise ApplyRefused("already_applied", "You have already applied to this posting.")
    if not profile.resume:
        raise ApplyRefused("no_resume", "Upload a resume before applying.")

    # D28: department and roster CGPA block; experience and education do not.
    eligible, reasons = check_eligibility(opportunity, student)
    if not eligible:
        raise ApplyRefused("not_eligible", " ".join(reasons))

    try:
        with profile.resume.open("rb") as handle:
            resume_bytes = handle.read()
    except FileNotFoundError as exc:
        raise ApplyRefused("no_resume", "Your resume file is missing; upload it again.") from exc

    # Scored here, once, so the applicant list is not a rescore per row and a
    # later edit to the profile cannot change what the company ranked.
    scored = score_for(profile, opportunity)

    name = profile.resume_filename or Path(profile.resume.name).name
    # The roster facts are frozen on the row: a later programme or CGPA change
    # must not rewrite what the company was shown or last year's figures.
    application = Application(
        opportunity=opportunity, profile=profile, status=Application.Status.APPLIED,
        prn=student.prn, full_name=student.full_name, department=student.department,
        programme=student.programme, school=student.school, batch=student.batch,
        year_of_study=student.year_of_study, cgpa_at_apply=student.cgpa,
        resume_snapshot_filename=name, resume_text=profile.resume_text,
        score=scored["score"], similarity=scored["similarity"],
        eligible=True, eligibility_reasons=[],
    )
    try:
        with transaction.atomic():
            # A copy, so replacing or deleting the profile resume afterwards
            # never changes the file the recruiter was sent.
            application.resume_snapshot.save(name, ContentFile(resume_bytes), save=False)
            application.save()
            _event(application, actor, "", Application.Status.APPLIED)
            # D27: applying is the student's consent to be seen by this
            # company, and a "shortlisted only" profile is otherwise invisible
            # to a company that has never shortlisted it. An existing manual
            # row stays manual: the recruiter's pick outranks the grant.
            CompanyShortlist.objects.get_or_create(
                company=opportunity.company, profile=profile,
                defaults={"source": CompanyShortlist.Source.APPLICATION},
            )
    except IntegrityError as exc:  # a double submit that raced the check
        raise ApplyRefused("already_applied", "You have already applied to this posting.") from exc

    AuditLog.record(
        actor=actor, action=AuditLog.Action.APPLICATION_CREATED,
        target=application.prn, opportunity=str(opportunity.id),
    )
    return application


@transaction.atomic
def withdraw(application: Application, actor) -> Application:
    if application.status not in WITHDRAWABLE:
        raise BadTransition(f"A {application.status} application cannot be withdrawn.")
    previous = application.status
    application.status = Application.Status.WITHDRAWN
    application.save(update_fields=["status", "updated_at"])
    _event(application, actor, previous, Application.Status.WITHDRAWN)

    # D27: drop the visibility grant, but only the one applying made, and only
    # when no other live application to this company still justifies it.
    company = application.opportunity.company
    if not has_active_application(company, application.profile):
        CompanyShortlist.objects.filter(
            company=company, profile=application.profile,
            source=CompanyShortlist.Source.APPLICATION,
        ).delete()

    AuditLog.record(
        actor=actor, action=AuditLog.Action.APPLICATION_WITHDRAWN,
        target=application.prn, opportunity=str(application.opportunity_id),
    )
    return application


@transaction.atomic
def change_status(application: Application, to: str, actor, note: str = "") -> Application:
    allowed = TRANSITIONS.get(application.status, set())
    if to not in allowed:
        raise BadTransition(f"An application cannot move from {application.status} to {to}.")
    previous = application.status
    application.status = to
    application.save(update_fields=["status", "updated_at"])
    _event(application, actor, previous, to, note)
    AuditLog.record(
        actor=actor, action=AuditLog.Action.APPLICATION_STATUS_CHANGED,
        target=application.prn, opportunity=str(application.opportunity_id),
        from_status=previous, to_status=to,
    )
    return application
