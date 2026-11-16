"""
The placement cell's directory of every account (WEEKEND_DEMO_PLAN P1, P2).

    GET /api/auth/admin/users            every login, any role, paginated
    GET /api/auth/admin/users/summary    counts by role and status

Read-only, placement admins only. A listing is identity data beyond the
reader's own record, so each one writes an `identity_accessed` audit row
naming the human keys it showed (G15). The summary shows counts and no
identities, and -- like the unaudited profile `stats` -- writes none.

School and batch live on the roster, not the account. They are read through
the profile's UUID join where a profile exists, and by PRN otherwise: a
student who signed up but never opened their profile has no profile row yet,
and the school filter must not lose them.
"""

from __future__ import annotations

from django.db.models import Count, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django_filters import rest_framework as filters
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role, Status, User
from accounts.permissions import IsPlacementAdmin
from core.filters import (
    HumanKeyFilter,
    HumanKeyInFilter,
    RejectUnknownQueryParams,
    ReportUnmatchedPrnsMixin,
)
from core.models import AuditLog


def directory_queryset():
    """Every account, with the roster and profile facts a row shows."""
    from roster.models import Student

    by_prn = Student.objects.filter(prn=OuterRef("prn"))
    return User.objects.select_related("company", "profile").annotate(
        roster_school=Coalesce(
            F("profile__student__school"), Subquery(by_prn.values("school")[:1])
        ),
        roster_batch=Coalesce(
            F("profile__student__batch"), Subquery(by_prn.values("batch")[:1])
        ),
    )


class UserDirectoryFilter(filters.FilterSet):
    # Choice filters, so a misspelt role is a 400 rather than an empty page
    # that reads as "there are no recruiters".
    role = filters.ChoiceFilter(choices=Role.choices)
    status = filters.ChoiceFilter(choices=Status.choices)
    prn = HumanKeyFilter(field_name="prn")
    prns = HumanKeyInFilter(field_name="prn")
    admin_id = HumanKeyFilter(field_name="admin_id")
    company_id = HumanKeyFilter(field_name="company__company_id")
    school = filters.CharFilter(field_name="roster_school", lookup_expr="iexact")
    batch = filters.NumberFilter(field_name="roster_batch")

    class Meta:
        model = User
        fields = [
            "role", "status", "prn", "prns", "admin_id", "company_id", "school", "batch",
        ]


class DirectoryRowSerializer(serializers.ModelSerializer):
    """
    One account as the users page shows it.

    Deliberately thin: no CGPA, phone or resume facts. Those stay on the
    profile endpoints, where reading them is audited per student.
    """

    human_key = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display")
    company = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()
    profile_verified = serializers.SerializerMethodField()
    onboarding_completed = serializers.SerializerMethodField()
    student_id = serializers.SerializerMethodField()
    school = serializers.SerializerMethodField()
    school_name = serializers.SerializerMethodField()
    batch = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "display_name",
            "email",
            "role",
            "human_key",
            "prn",
            "admin_id",
            "company",
            "status",
            "status_display",
            "is_active",
            "is_verified",
            "profile_verified",
            "onboarding_completed",
            "student_id",
            "school",
            "school_name",
            "batch",
            "last_login",
            "date_joined",
        )
        read_only_fields = fields

    @staticmethod
    def _profile(user: User):
        # Reverse one-to-one: raises rather than returning None when absent.
        try:
            return user.profile
        except User.profile.RelatedObjectDoesNotExist:
            return None

    def get_human_key(self, user: User) -> str | None:
        if user.is_student:
            return user.prn
        if user.is_placement_admin:
            return user.admin_id
        # A recruiter has no key of their own; the organisation's CMP- id is
        # what an export or a log line names them by.
        return user.company.company_id if user.company else None

    def get_company(self, user: User) -> dict | None:
        if user.company is None:
            return None
        return {
            "id": str(user.company.id),
            "company_id": user.company.company_id,
            "name": user.company.name,
        }

    def get_is_verified(self, user: User) -> bool | None:
        # Email ownership, which only students prove (by OTP at signup).
        # Admin and recruiter logins are provisioned by staff and never pass
        # through verification, so "unverified" would be a false alarm.
        return user.email_verified_at is not None if user.is_student else None

    def get_profile_verified(self, user: User) -> bool | None:
        if not user.is_student:
            return None
        profile = self._profile(user)
        return bool(profile and profile.is_verified)

    def get_onboarding_completed(self, user: User) -> bool | None:
        if not user.is_student:
            return None
        profile = self._profile(user)
        return bool(profile and profile.onboarding_completed_at)

    def get_student_id(self, user: User) -> str | None:
        # Only when a profile exists: the admin detail page is addressed by it
        # and answers 404 otherwise.
        profile = self._profile(user) if user.is_student else None
        return str(profile.student_id) if profile else None

    def get_school(self, user: User) -> str | None:
        return (getattr(user, "roster_school", None) or None) if user.is_student else None

    def get_school_name(self, user: User) -> str | None:
        from roster.reference import SCHOOLS

        school = self.get_school(user)
        return SCHOOLS.get(school, school) if school else None

    def get_batch(self, user: User) -> int | None:
        return getattr(user, "roster_batch", None) if user.is_student else None


class UserDirectoryView(ReportUnmatchedPrnsMixin, generics.ListAPIView):
    """Every account, filterable by role, status, human key, school and batch."""

    permission_classes = [IsPlacementAdmin]
    serializer_class = DirectoryRowSerializer
    filterset_class = UserDirectoryFilter
    search_fields = [
        "full_name", "email", "prn", "admin_id", "company__company_id", "company__name",
    ]
    ordering_fields = ["full_name", "email", "role", "status", "last_login", "date_joined"]
    ordering = ["role", "full_name", "email"]

    def get_queryset(self):
        return directory_queryset()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # Once, here, after the page is built: the unmatched-PRN report runs
        # the filtered query a second time, and logging in get_queryset would
        # write two rows for one look.
        results = response.data.get("results", [])
        AuditLog.record(
            actor=request.user,
            action=AuditLog.Action.IDENTITY_ACCESSED,
            target="user directory",
            route=request.path,
            query={key: request.query_params.get(key) for key in request.query_params},
            count=response.data.get("count", len(results)),
            keys=[row["human_key"] for row in results if row["human_key"]],
        )
        return response


class UserDirectorySummaryView(APIView):
    """Counts by role and status, plus the school and batch filter options."""

    permission_classes = [IsPlacementAdmin]

    def get(self, request):
        from roster.models import Student
        from roster.reference import SCHOOLS

        # No filters here, so any parameter is a typo; D12 says 400.
        RejectUnknownQueryParams().filter_queryset(request, User.objects.none(), self)

        users = User.objects.all()
        by_role = dict.fromkeys(Role.values, 0)
        by_role.update(dict(users.values_list("role").annotate(n=Count("id")).order_by()))
        by_status = dict.fromkeys(Status.values, 0)
        by_status.update(dict(users.values_list("status").annotate(n=Count("id")).order_by()))

        student_prns = users.filter(role=Role.STUDENT).values("prn")
        batches = sorted(
            Student.objects.filter(prn__in=student_prns)
            .values_list("batch", flat=True).distinct()
        )
        return Response(
            {
                "total": users.count(),
                "by_role": by_role,
                "by_status": by_status,
                "schools": [{"key": key, "name": name} for key, name in SCHOOLS.items()],
                "batches": batches,
            }
        )
