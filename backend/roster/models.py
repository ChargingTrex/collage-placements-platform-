"""
The student master list.

This is the source of truth the rest of the portal reads from: a student
account can only exist if the placement cell has already put that PRN and
college email on the roster. Profiles, eligibility filters and company-facing
search all hang off a `Student` row, never off self-declared data.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.deconstruct import deconstructible

from core.models import TimeStampedModel

@deconstructible
class PrnValidator:
    """Check a PRN against settings.IDENTITY["PRN_REGEX"], read on every call."""

    message = "PRN must be nine digits."

    def __call__(self, value) -> None:
        # Read the rule at call time so changing settings (or a test override)
        # takes effect without a restart. fullmatch, not search: "$" alone
        # also matches before a trailing newline, so "220200921\n" would pass.
        if not re.fullmatch(settings.IDENTITY["PRN_REGEX"], str(value)):
            raise ValidationError(self.message, code="invalid")

    def __eq__(self, other) -> bool:
        return isinstance(other, PrnValidator)

    def __hash__(self) -> int:
        return hash(PrnValidator)


# Keep this name: the Student.prn field and tests import it. To change the
# rule, change PRN_REGEX in settings, not this object.
PRN_VALIDATOR = PrnValidator()


def normalise_prn(value: str) -> str:
    return (value or "").strip().upper()


def normalise_email(value: str) -> str:
    return (value or "").strip().lower()


class Student(TimeStampedModel):
    """One row of the roster uploaded by the placement cell."""

    # The `student_id` of the shared spec: a UUID that every relation joins on
    # and that survives any change to the roster. PRN stays the human key.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    prn = models.CharField(
        max_length=32, unique=True, validators=[PRN_VALIDATOR],
        help_text="Permanent Registration Number.",
    )
    email = models.EmailField(
        unique=True, max_length=254, help_text="College-issued email address."
    )
    full_name = models.CharField(max_length=150)
    department = models.CharField(max_length=80)
    batch = models.PositiveIntegerField(
        validators=[MinValueValidator(1950), MaxValueValidator(2100)],
        help_text="Graduating year, e.g. 2026.",
    )
    cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        # Decimal bounds, not ints: DRF compares against the field's own type.
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))],
    )
    phone = models.CharField(max_length=20, blank=True)

    # Carried in the token so a page renders without a directory lookup. The
    # shared code list that governs these values is stream A-3's; until it
    # lands they are free text and an unknown value is not yet rejected.
    school = models.CharField(max_length=120, blank=True)
    programme = models.CharField(max_length=120, blank=True)
    year_of_study = models.PositiveSmallIntegerField(null=True, blank=True)

    # Cleared by the placement cell when a student leaves or is barred from
    # placements; blocks signup and hides the profile from companies.
    is_placement_eligible = models.BooleanField(default=True)

    class Meta:
        ordering = ["prn"]
        indexes = [
            models.Index(fields=["department", "batch"]),
            models.Index(fields=["batch"]),
        ]

    def __str__(self) -> str:
        return f"{self.prn} — {self.full_name}"

    def save(self, *args, **kwargs):
        self.prn = normalise_prn(self.prn)
        self.email = normalise_email(self.email)
        self.department = self.department.strip()
        return super().save(*args, **kwargs)

    @classmethod
    def match(cls, prn: str, email: str) -> "Student | None":
        """
        Return the roster row only when PRN *and* email identify the same
        student. A PRN that exists under a different email is not a match --
        that is the case the PRD wants blocked and flagged.
        """
        return cls.objects.filter(
            prn=normalise_prn(prn), email=normalise_email(email)
        ).first()


class FlaggedSignup(TimeStampedModel):
    """
    A signup attempt that failed roster matching.

    Kept rather than discarded so the placement cell can tell a typo apart
    from someone probing for a way in, and so a student whose roster row is
    genuinely missing has a trail an admin can act on.
    """

    class Reason(models.TextChoices):
        NO_SUCH_PRN = "no_such_prn", "PRN not on the roster"
        EMAIL_MISMATCH = "email_mismatch", "PRN is on the roster under a different email"
        PRN_MISMATCH = "prn_mismatch", "Email is on the roster under a different PRN"
        DOMAIN_NOT_ALLOWED = "domain_not_allowed", "Not a college email domain"
        NOT_ELIGIBLE = "not_eligible", "Roster row is marked not placement-eligible"
        ALREADY_REGISTERED = "already_registered", "An account already exists"

    class Status(models.TextChoices):
        OPEN = "open", "Awaiting review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    # UUID key, like Student, so API ids do not reveal how many flags exist.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    prn = models.CharField(max_length=32)
    email = models.EmailField(max_length=254)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    attempts = models.PositiveIntegerField(
        default=1, help_text="Times this PRN/email pair has been tried."
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN
    )
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_signups",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["prn", "email"], name="unique_flagged_prn_email"
            )
        ]
        indexes = [models.Index(fields=["status", "-updated_at"])]

    def __str__(self) -> str:
        return f"{self.prn} / {self.email} — {self.get_reason_display()}"

    @classmethod
    def record(cls, *, prn: str, email: str, reason: str) -> "FlaggedSignup":
        """
        Flag an attempt, collapsing repeats of the same pair into one row
        with a bumped counter so a retrying student does not bury the queue.
        """
        flagged, created = cls.objects.get_or_create(
            prn=normalise_prn(prn),
            email=normalise_email(email),
            defaults={"reason": reason},
        )
        if not created:
            flagged.attempts += 1
            flagged.reason = reason
            # A repeat attempt reopens a dismissed flag: the student is still
            # trying to get in, so it belongs back in front of an admin.
            if flagged.status == cls.Status.DISMISSED:
                flagged.status = cls.Status.OPEN
            flagged.save(update_fields=["attempts", "reason", "status", "updated_at"])
        return flagged
