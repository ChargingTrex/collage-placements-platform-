"""
Roster administration. Every endpoint here is placement-cell-admin only.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef
from django_filters import rest_framework as filters
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsPlacementAdmin
from core.filters import HumanKeyFilter, HumanKeyInFilter, ReportUnmatchedPrnsMixin
from core.models import AuditLog
from roster.importers import RosterFormatError, import_roster_csv
from roster.models import FlaggedSignup, Student
from roster.serializers import (
    FlaggedSignupReviewSerializer,
    FlaggedSignupSerializer,
    RosterUploadSerializer,
    StudentSerializer,
)


@api_view(["POST"])
@permission_classes([IsPlacementAdmin])
@parser_classes([MultiPartParser, FormParser])
def upload_roster(request):
    """
    Upload a roster CSV.

    Returns 200 when every row applied, 207 when some rows were rejected --
    the good rows are still saved, and `errors` names each bad row by its
    line number in the uploaded file.
    """
    serializer = RosterUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        result = import_roster_csv(
            serializer.validated_data["file"],
            dry_run=serializer.validated_data["dry_run"],
        )
    except RosterFormatError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not serializer.validated_data["dry_run"]:
        AuditLog.record(
            actor=request.user,
            action=AuditLog.Action.ROSTER_UPLOADED,
            target=serializer.validated_data["file"].name,
            **{k: v for k, v in result.as_dict().items() if k != "errors"},
        )

    return Response(
        {"dry_run": serializer.validated_data["dry_run"], **result.as_dict()},
        status=status.HTTP_200_OK if result.ok else status.HTTP_207_MULTI_STATUS,
    )


class StudentRosterFilter(filters.FilterSet):
    """Reconciliation first: PRN is how the placement cell finds one student."""

    prn = HumanKeyFilter(field_name="prn")
    prns = HumanKeyInFilter(field_name="prn")

    class Meta:
        model = Student
        fields = ["prn", "prns", "department", "batch", "is_placement_eligible"]


class StudentViewSet(ReportUnmatchedPrnsMixin, viewsets.ReadOnlyModelViewSet):
    """Browse the roster. Read-only over the API: rows change by CSV upload."""

    serializer_class = StudentSerializer
    permission_classes = [IsPlacementAdmin]
    prn_field = "prn"
    filterset_class = StudentRosterFilter
    search_fields = ["prn", "email", "full_name", "department"]
    ordering_fields = ["prn", "batch", "cgpa", "created_at"]

    def get_queryset(self):
        has_account = User.objects.filter(prn=OuterRef("prn"), is_active=True)
        return Student.objects.annotate(account_exists=Exists(has_account))


class FlaggedSignupViewSet(viewsets.ReadOnlyModelViewSet):
    """The review queue for signup attempts that failed roster matching."""

    serializer_class = FlaggedSignupSerializer
    permission_classes = [IsPlacementAdmin]
    queryset = FlaggedSignup.objects.select_related("reviewed_by")
    filterset_fields = ["status", "reason"]
    search_fields = ["prn", "email"]
    ordering_fields = ["updated_at", "attempts"]

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Mark a flagged attempt resolved or dismissed, with a note."""
        flagged = self.get_object()
        serializer = FlaggedSignupReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        flagged.status = serializer.validated_data["status"]
        flagged.admin_note = serializer.validated_data.get("admin_note", "")
        flagged.reviewed_by = request.user
        flagged.reviewed_at = timezone.now()
        flagged.save(
            update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"]
        )

        AuditLog.record(
            actor=request.user,
            action=AuditLog.Action.SIGNUP_REVIEWED,
            target=f"{flagged.prn} / {flagged.email}",
            status=flagged.status,
            note=flagged.admin_note,
        )
        return Response(FlaggedSignupSerializer(flagged).data)
