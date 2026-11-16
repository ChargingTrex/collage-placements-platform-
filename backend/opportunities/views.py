"""
Opportunities API.

Authorisation is the queryset's (`Opportunity.objects.visible_to`) plus the
role gates below. A posting outside the caller's scope is a 404, so the route
never confirms it exists.
"""

from __future__ import annotations

import csv
import datetime
import logging
import statistics
from collections import Counter

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsCompany, IsCompanyOrAdmin, IsPlacementAdmin, IsStudent
from core.filters import ReportUnmatchedPrnsMixin
from core.models import AuditLog
from matching.engine import get_engine
from matching.throttling import MatchingThrottle
from notifications.services import notify_new_opportunity
from opportunities import services
from opportunities.eligibility import check_eligibility
from opportunities.filters import ApplicationFilter, OpportunityFilter
from opportunities.models import Application, ApplicationEvent, Opportunity
from opportunities.permissions import RecruiterHasCompany
from opportunities.scoring import score_for
from opportunities.serializers import (
    AdminApplicationSerializer,
    CompanyApplicationSerializer,
    OpportunitySerializer,
    PublicOpportunitySerializer,
    StudentApplicationSerializer,
)
from profiles import match
from profiles.views import audited_document, document_response, get_or_create_profile

logger = logging.getLogger(__name__)

APPLICANT_COLUMNS = [
    "prn", "full_name", "department", "programme", "school", "batch", "cgpa_at_apply",
    "status", "score", "applied_at", "email", "phone", "contact_available",
]


def _cell(value: str) -> str:
    """Stop a spreadsheet reading a student-typed name as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def mark_open(opportunity: Opportunity, admin) -> None:
    """
    Everything that happens when a posting reaches `open`, however it got
    there (admin approval or admin creation).
    """
    opportunity.status = Opportunity.Status.OPEN
    opportunity.approved_by = admin
    opportunity.approved_at = timezone.now()
    opportunity.rejection_reason = ""
    opportunity.save()
    # The JD feeds the role categories (a no-op with the LLM off); a by-product
    # must never block opening the posting.
    try:
        match.read_job(opportunity.description, record=True)
    except Exception:  # noqa: BLE001
        logger.exception("Could not record the JD for opportunity %s", opportunity.id)
    # D26 trigger 1: eligibility only, no scoring inside the request.
    notify_new_opportunity(opportunity)


class OpportunityViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    filterset_class = OpportunityFilter
    search_fields = ["title", "description", "company__name"]
    ordering_fields = ["created_at", "deadline", "title"]
    permission_classes = [RecruiterHasCompany]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        gates = {
            "create": [IsCompanyOrAdmin],
            "partial_update": [IsCompanyOrAdmin],
            "destroy": [IsCompanyOrAdmin],
            "submit": [IsCompany],
            "approve": [IsPlacementAdmin],
            "reject": [IsPlacementAdmin],
            "close": [IsCompanyOrAdmin],
            "feed": [IsStudent],
            "apply": [IsStudent],
            "screen": [IsCompanyOrAdmin],
            "applicants_export": [IsCompanyOrAdmin],
            "stats": [IsPlacementAdmin],
        }
        extra = gates.get(self.action, [])
        return [IsAuthenticated(), RecruiterHasCompany(), *(gate() for gate in extra)]

    def get_queryset(self):
        return Opportunity.objects.visible_to(self.request.user).select_related("company")

    def get_serializer_class(self):
        user = self.request.user
        if user.is_authenticated and user.is_student:
            return PublicOpportunitySerializer
        return OpportunitySerializer

    # --- create / edit / delete -------------------------------------------

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_placement_admin:
            company = serializer.validated_data.get("company")
            if company is None:
                raise ValidationError({"company": "An admin must name the company."})
            # Admin-created postings open at once (D28): the placement cell is
            # the approver, so there is no one to wait for.
            opportunity = serializer.save(created_by=user, status=Opportunity.Status.DRAFT)
            mark_open(opportunity, user)
        else:
            # A recruiter's posting waits for approval, and is always their
            # own company's whatever the body says.
            opportunity = serializer.save(
                created_by=user, company=user.company, status=Opportunity.Status.DRAFT
            )
        AuditLog.record(
            actor=user, action=AuditLog.Action.OPPORTUNITY_CREATED,
            target=str(opportunity.id), status=opportunity.status,
        )

    def perform_update(self, serializer):
        opportunity = serializer.instance
        editable = (
            {Opportunity.Status.DRAFT, Opportunity.Status.REJECTED}
            if self.request.user.is_company
            else set(Opportunity.Status) - {Opportunity.Status.CLOSED}
        )
        if opportunity.status not in editable:
            raise ValidationError({"detail": f"A {opportunity.status} posting cannot be edited."})
        # The company is fixed at creation.
        serializer.save(company=opportunity.company)

    def perform_destroy(self, instance):
        if instance.status != Opportunity.Status.DRAFT:
            raise ValidationError({"detail": "Only a draft can be deleted."})
        instance.delete()

    # --- lifecycle ----------------------------------------------------------

    def _move(self, request, pk, *, allowed, to, audit, **fields):
        opportunity = self.get_object()
        if opportunity.status not in allowed:
            raise ValidationError(
                {"detail": f"A {opportunity.status} posting cannot move to {to}."}
            )
        opportunity.status = to
        for name, value in fields.items():
            setattr(opportunity, name, value)
        opportunity.save()
        AuditLog.record(actor=request.user, action=audit, target=str(opportunity.id), to=to)
        return opportunity

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        opportunity = self._move(
            request, pk,
            allowed={Opportunity.Status.DRAFT, Opportunity.Status.REJECTED},
            to=Opportunity.Status.PENDING_REVIEW,
            audit=AuditLog.Action.OPPORTUNITY_SUBMITTED,
            submitted_at=timezone.now(),
        )
        return Response(self.get_serializer(opportunity).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        opportunity = self.get_object()
        if opportunity.status != Opportunity.Status.PENDING_REVIEW:
            raise ValidationError({"detail": f"A {opportunity.status} posting cannot be approved."})
        mark_open(opportunity, request.user)
        AuditLog.record(
            actor=request.user, action=AuditLog.Action.OPPORTUNITY_APPROVED,
            target=str(opportunity.id),
        )
        return Response(self.get_serializer(opportunity).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            raise ValidationError({"reason": "Say why, so the company can fix it."})
        opportunity = self._move(
            request, pk,
            allowed={Opportunity.Status.PENDING_REVIEW},
            to=Opportunity.Status.REJECTED,
            audit=AuditLog.Action.OPPORTUNITY_REJECTED,
            rejection_reason=reason,
        )
        return Response(self.get_serializer(opportunity).data)

    # --- the student side ---------------------------------------------------

    @action(detail=False, methods=["get"])
    def feed(self, request):
        """Open postings, best match first. Scores come from the shared cache."""
        profile = get_or_create_profile(request.user)
        postings = self.filter_queryset(
            self.get_queryset().filter(
                status=Opportunity.Status.OPEN, deadline__gte=datetime.date.today()
            )
        )
        applications = {
            a.opportunity_id: a.status for a in Application.objects.filter(profile=profile)
        }
        student = profile.student
        rows = []
        for posting in postings:
            scored = score_for(profile, posting)
            eligible, reasons = check_eligibility(posting, student)
            row = PublicOpportunitySerializer(posting, context={"request": request}).data
            row.update(
                score=scored["score"],
                components=scored["components"],
                matched_skills=scored["matched_skills"],
                missing_skills=scored["missing_skills"],
                # Eligibility is a flag beside the score, never part of it.
                eligible=eligible,
                eligibility_reasons=reasons,
                has_applied=posting.id in applications,
                application_status=applications.get(posting.id),
            )
            rows.append(row)
        rows.sort(key=lambda r: (-r["score"], r["deadline"], r["title"]))
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(page)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        # Not `get_object`: a student's queryset is open postings only, but a
        # posting that closed since they saw it should say "not_open", not 404.
        opportunity = get_object_or_404(Opportunity.objects.select_related("company"), pk=pk)
        profile = get_or_create_profile(request.user)
        try:
            application = services.apply(opportunity, profile, request.user)
        except services.ApplyRefused as refusal:
            return Response(
                {"detail": refusal.detail, "reason": refusal.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            StudentApplicationSerializer(application, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        opportunity = self._move(
            request, pk,
            allowed={Opportunity.Status.OPEN},
            to=Opportunity.Status.CLOSED,
            audit=AuditLog.Action.OPPORTUNITY_CLOSED,
        )
        return Response(self.get_serializer(opportunity).data)


    # --- company tools ------------------------------------------------------

    @action(detail=True, methods=["post"], throttle_classes=[MatchingThrottle])
    def screen(self, request, pk=None):
        """
        Bulk-screen the applicants' resume snapshots (not their current
        resumes). Request value wins over the posting's, which wins over settings.
        """
        opportunity = self.get_object()
        data = request.data if hasattr(request.data, "get") else {}

        threshold = data.get("threshold")
        if threshold is None:
            threshold = opportunity.similarity_threshold
        if threshold is None:
            threshold = settings.SUGGESTIONS["MIN_SCORE"]
        min_years = data.get("min_experience_years")
        if min_years is None:
            min_years = opportunity.min_experience_years
        levels = data.get("required_education_levels")
        if levels is None:
            levels = opportunity.required_education_levels
        try:
            threshold = float(threshold)
            min_years = None if min_years is None else float(min_years)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"detail": "threshold and min_experience_years must be numbers."}) from exc
        if not 0 <= threshold <= 100:
            raise ValidationError({"threshold": "Between 0 and 100."})
        if not isinstance(levels, list):
            raise ValidationError({"required_education_levels": "A list of levels."})

        applications = list(opportunity.applications.exclude(status=Application.Status.WITHDRAWN))
        by_id = {str(a.id): a for a in applications}
        engine = get_engine()
        # The threshold is on the calibrated 0-100 scale, so one figure means
        # the same on every backend. The engine cuts on its raw similarity, so
        # map the figure back through the engine's own calibration bounds.
        bounds = settings.MATCH_SCORE["CALIBRATION"].get(engine.backend_name) or {
            "FLOOR": 0.0, "CEILING": 1.0,
        }
        raw_cut = bounds["FLOOR"] + (threshold / 100) * (bounds["CEILING"] - bounds["FLOOR"])
        result = engine.screen(
            {key: a.resume_text for key, a in by_id.items()},
            opportunity.description,
            similarity_threshold=raw_cut,
            min_experience_years=min_years,
            required_education=levels or None,
        )

        def row(item, reason=""):
            application = by_id[item.identifier]
            return {
                "application_id": item.identifier,
                "prn": application.prn,
                "full_name": application.full_name,
                "score": application.score,
                "experience_years": item.extracted.experience_years,
                "education_levels": sorted(item.extracted.education_levels),
                "reasons": [reason] if reason else [],
            }

        return Response(
            {
                "shortlisted": [row(i) for i in result.ranked],
                "below_threshold": [row(i, f"Below the {threshold:g} cut.") for i in result.below_threshold],
                "filtered_out": [row(i, i.excluded_by) for i in result.excluded],
            }
        )

    @action(detail=True, methods=["get"], url_path="applicants/export", url_name="applicants-export")
    def applicants_export(self, request, pk=None):
        opportunity = self.get_object()
        applications = list(
            opportunity.applications.select_related("profile__student").order_by("-score", "prn")
        )
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="applicants-{opportunity.id}.csv"'
        writer = csv.writer(response)
        writer.writerow(APPLICANT_COLUMNS)
        for a in applications:
            verified = a.profile.is_verified
            writer.writerow([
                a.prn, _cell(a.full_name), _cell(a.department), _cell(a.programme),
                _cell(a.school), a.batch if a.batch is not None else "",
                "" if a.cgpa_at_apply is None else a.cgpa_at_apply, a.status, a.score,
                a.created_at.isoformat(),
                a.profile.student.email if verified else "",
                a.profile.phone if verified else "",
                "true" if verified else "false",
            ])
        AuditLog.record(
            actor=request.user, action=AuditLog.Action.APPLICATIONS_EXPORTED,
            target=str(opportunity.id), count=len(applications),
        )
        return response

    @action(detail=False, methods=["get"])
    def stats(self, request):
        opportunities = Counter(Opportunity.objects.values_list("status", flat=True))
        by_status, per = Counter(), {}
        for o in Opportunity.objects.select_related("company"):
            per[o.id] = {
                "id": o.id, "title": o.title, "company": o.company.name,
                "applicants": 0, "by_status": Counter(),
            }
        for opportunity_id, state in Application.objects.values_list("opportunity_id", "status"):
            by_status[state] += 1
            per[opportunity_id]["applicants"] += 1
            per[opportunity_id]["by_status"][state] += 1
        first = {}
        events = (
            ApplicationEvent.objects.filter(to_status=Application.Status.SHORTLISTED)
            .select_related("application").order_by("created_at")
        )
        for event in events:
            first.setdefault(event.application_id, event)
        hours = [
            (e.created_at - e.application.created_at).total_seconds() / 3600 for e in first.values()
        ]
        return Response({
            "opportunities_by_status": dict(opportunities),
            "applications_by_status": dict(by_status),
            "per_opportunity": [
                {**row, "by_status": dict(row["by_status"])}
                for row in sorted(per.values(), key=lambda r: (r["company"], r["title"]))
            ],
            "median_hours_to_shortlist": float(statistics.median(hours)) if hours else None,
        })


class ApplicationViewSet(
    ReportUnmatchedPrnsMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Applications, scoped by `Application.objects.visible_to`."""

    filterset_class = ApplicationFilter
    prn_field = "prn"
    ordering_fields = ["created_at", "score", "prn"]
    ordering = ["-created_at"]

    def get_permissions(self):
        gates = {"withdraw": [IsStudent], "set_status": [IsCompanyOrAdmin]}
        return [
            IsAuthenticated(), RecruiterHasCompany(),
            *(gate() for gate in gates.get(self.action, [])),
        ]

    def get_queryset(self):
        return (
            Application.objects.visible_to(self.request.user)
            .select_related("opportunity", "profile__student")
            .prefetch_related("profile__skills", "events")
        )

    def get_serializer_class(self):
        user = self.request.user
        if user.is_placement_admin:
            return AdminApplicationSerializer
        if user.is_student:
            return StudentApplicationSerializer
        return CompanyApplicationSerializer

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        application = self.get_object()
        try:
            services.withdraw(application, request.user)
        except services.BadTransition as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["post"], url_path="status", url_name="status")
    def set_status(self, request, pk=None):
        application = self.get_object()
        to = str(request.data.get("status") or "")
        try:
            services.change_status(
                application, to, request.user, str(request.data.get("note") or "")[:500]
            )
        except services.BadTransition as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["get"])
    def resume(self, request, pk=None):
        """The resume as it was at apply time, never the profile's current one."""
        application = self.get_object()
        if request.user.is_student:
            return document_response(application, "resume_snapshot")
        return audited_document(request, application, "resume_snapshot")
