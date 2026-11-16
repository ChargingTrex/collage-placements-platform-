"""
In-app notifications (D26): a minimal slice.

One row per (recipient, kind, opportunity). The unique constraint is what makes
both triggers idempotent: sending twice is a no-op, not a duplicate.
"""

import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        NEW_OPPORTUNITY = "new_opportunity", "A new opportunity you can apply to"
        DEADLINE_SOON = "deadline_soon", "An opportunity's deadline is close"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    opportunity = models.ForeignKey(
        "opportunities.Opportunity", on_delete=models.CASCADE, related_name="notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "kind", "opportunity"], name="unique_notification"
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} -> {self.recipient_id}"
