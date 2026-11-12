"""Shared model building blocks and the admin audit trail."""

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Every domain model carries creation/update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """
    Append-only record of admin actions.

    The PRD's auditability requirement: verifying a profile, uploading a
    roster or opportunity, and editing the certification catalog all land
    here. Written through `AuditLog.record(...)` rather than signals so the
    call site names the action explicitly.
    """

    class Action(models.TextChoices):
        ROSTER_UPLOADED = "roster_uploaded", "Roster uploaded"
        SIGNUP_FLAGGED = "signup_flagged", "Signup flagged for review"
        SIGNUP_REVIEWED = "signup_reviewed", "Flagged signup reviewed"
        PROFILE_VERIFIED = "profile_verified", "Profile verified"
        PROFILE_UNVERIFIED = "profile_unverified", "Profile verification revoked"
        RESUME_PARSED = "resume_parsed", "Resume parsed"
        RESUME_ANALYSED = "resume_analysed", "Resume analysed"
        SESSIONS_REVOKED = "sessions_revoked", "Sessions revoked"
        IDENTITY_ACCESSED = "identity_accessed", "Student identity record read"
        DOCUMENT_ACCESSED = "document_accessed", "Student document read"
        TRANSCRIPT_PRN_MISMATCH = "transcript_prn_mismatch", "Transcript names a different PRN"
        CGPA_MISMATCH_FLAGGED = "cgpa_mismatch_flagged", "Transcript CGPA flagged for review"
        CGPA_REVIEW_RESOLVED = "cgpa_review_resolved", "CGPA review resolved"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=64, choices=Action.choices)
    target = models.CharField(
        max_length=255, blank=True, help_text="Human-readable subject of the action."
    )
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_action_display()} :: {self.target}"

    @classmethod
    def record(cls, *, actor=None, action: str, target: str = "", **detail) -> "AuditLog":
        return cls.objects.create(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            target=target,
            detail=detail,
        )
