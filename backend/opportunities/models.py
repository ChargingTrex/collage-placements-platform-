"""
Postings and applications.

An opportunity belongs to a `Company`, never to the recruiter who typed it
in, so two colleagues see the same board (the bug the Company model fixed for
shortlists). Applications are never deleted: withdrawing is a status.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from core.storage import application_resume_upload_path


class OpportunityQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        The postings `user` may see. The one visibility rule: every list,
        detail and action goes through it, so a posting outside the caller's
        scope is a 404 rather than something the UI hides.
        """
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_placement_admin:
            return self
        if user.is_company:
            if user.company_id is None:
                return self.none()
            return self.filter(company_id=user.company_id)
        if user.is_student:
            return self.filter(status=Opportunity.Status.OPEN)
        return self.none()


class Opportunity(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_REVIEW = "pending_review", "Waiting for the placement cell"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"

    class RoleType(models.TextChoices):
        INTERNSHIP = "internship", "Internship"
        FULL_TIME = "full_time", "Full-time"

    class SalaryPeriod(models.TextChoices):
        MONTH = "month", "Per month"
        YEAR = "year", "Per year"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="opportunities"
    )
    title = models.CharField(max_length=200)
    # The JD the engine scores students against.
    description = models.TextField()
    role_type = models.CharField(max_length=16, choices=RoleType.choices)
    location = models.CharField(max_length=160, blank=True)
    openings = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    required_skills = models.JSONField(default=list, blank=True)
    # Empty means every department.
    eligible_departments = models.JSONField(default=list, blank=True)
    min_cgpa = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))],
    )
    # Screening filters, not apply blocks (D28).
    min_experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    required_education_levels = models.JSONField(default=list, blank=True)

    salary_disclosed = models.BooleanField(default=False)
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    salary_period = models.CharField(max_length=8, choices=SalaryPeriod.choices, blank=True)
    salary_currency = models.CharField(max_length=3, default="INR")

    deadline = models.DateField()
    # 0-100 on the calibrated match score. Null falls back to settings.
    similarity_threshold = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)]
    )

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_opportunities",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_opportunities",
    )

    objects = OpportunityQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "deadline"])]

    def __str__(self) -> str:
        return f"{self.title} ({self.company.name})"


class ApplicationQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Admin: all. Recruiter: their company's postings'. Student: their own."""
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_placement_admin:
            return self
        if user.is_company:
            if user.company_id is None:
                return self.none()
            return self.filter(opportunity__company_id=user.company_id)
        if user.is_student:
            return self.filter(profile__user=user)
        return self.none()


class Application(TimeStampedModel):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="applications")
    profile = models.ForeignKey(
        "profiles.StudentProfile", on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.APPLIED)

    # Frozen from the roster at apply time, so a later programme change never
    # rewrites what a company was told or last year's figures.
    prn = models.CharField(max_length=32)
    full_name = models.CharField(max_length=150)
    department = models.CharField(max_length=80, blank=True)
    programme = models.CharField(max_length=120, blank=True)
    school = models.CharField(max_length=120, blank=True)
    batch = models.PositiveIntegerField(null=True, blank=True)
    year_of_study = models.PositiveSmallIntegerField(null=True, blank=True)
    cgpa_at_apply = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    # A copy, so editing or deleting the profile resume never changes what the
    # recruiter received. `resume_text` is the same copy's text, kept so
    # screening does not re-read a file.
    resume_snapshot = models.FileField(upload_to=application_resume_upload_path, max_length=255)
    resume_snapshot_filename = models.CharField(max_length=255, blank=True)
    resume_text = models.TextField(blank=True)

    # Scored once at apply time so an applicant list is not an N-way rescore.
    score = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    similarity = models.FloatField(default=0.0)
    eligible = models.BooleanField(default=True)
    eligibility_reasons = models.JSONField(default=list, blank=True)

    objects = ApplicationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["opportunity", "profile"], name="unique_application")
        ]

    def __str__(self) -> str:
        return f"{self.prn} -> {self.opportunity_id} ({self.status})"

    @property
    def applied_at(self):
        return self.created_at


class ApplicationEvent(models.Model):
    """The status history: who moved an application, from what, to what."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
