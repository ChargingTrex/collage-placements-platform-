"""
Student profile API.

Three audiences, three routes, three serializers:

    /api/profiles/me              the student's own profile and its children
    /api/profiles/students        the company-facing browse/filter view
    /api/profiles/admin           the placement cell's view and verification

Authorization is enforced by the queryset (`StudentProfile.objects.visible_to`)
and by `get_object` on the child entries, not by what the UI chooses to render.
"""

from __future__ import annotations

import csv
import mimetypes
from decimal import Decimal

from django.http import FileResponse, Http404, HttpResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.filters import ReportUnmatchedPrnsMixin
from accounts.permissions import IsCompany, IsCompanyOrAdmin, IsPlacementAdmin, IsStudent
from core.models import AuditLog
from matching.engine import ResumeParseError, get_engine
from matching.serializers import JobDescriptionSerializer
from matching.transcripts import parse_transcript
from matching.throttling import MatchingThrottle
from profiles import analysis as analysis_service
from profiles import match as match_service
from profiles.filters import AdminProfileFilter, StudentProfileFilter
from profiles.models import (
    CareerPath,
    CgpaReview,
    CompanyShortlist,
    ExperienceEntry,
    ProfileSkill,
    ProjectEntry,
    ResumeAnalysis,
    StudentProfile,
)
from profiles.serializers import (
    AdminProfileDetailSerializer,
    AdminProfileSerializer,
    CgpaReviewSerializer,
    CompanyProfileSerializer,
    ConfirmCgpaSerializer,
    ConfirmParsedSerializer,
    ExperienceEntrySerializer,
    OnboardingSerializer,
    OwnProfileSerializer,
    ProfileSkillSerializer,
    ProjectEntrySerializer,
    ResumeUploadSerializer,
    ShortlistSerializer,
    MarksheetUploadSerializer,
    TranscriptUploadSerializer,
    VerificationSerializer,
    VisibilitySerializer,
)


def get_or_create_profile(user) -> StudentProfile:
    """
    The profile behind a verified student account.

    Created on demand rather than at signup so a roster row that arrives late
    still produces a working profile the first time the student opens it.
    """
    from roster.models import Student

    profile = StudentProfile.objects.filter(user=user).first()
    if profile:
        return profile

    student = get_object_or_404(Student, prn=user.prn)
    profile, _ = StudentProfile.objects.get_or_create(
        user=user, student=student, defaults={"phone": student.phone}
    )
    return profile


def document_response(profile: StudentProfile, field: str) -> FileResponse:
    """
    Stream a stored document under its original filename, or 404.

    Every document leaves through here (and an audited route) rather than a
    /media/ link, so access can be checked and logged each time.
    """
    stored = getattr(profile, field)
    if not stored:
        raise Http404("No such document.")
    name = getattr(profile, f"{field}_filename") or stored.name.rsplit("/", 1)[-1]
    try:
        handle = stored.open("rb")
    except FileNotFoundError as exc:
        raise Http404("No such document.") from exc
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return FileResponse(handle, filename=name, content_type=content_type)


def audited_document(request, profile: StudentProfile, field: str) -> FileResponse:
    """`document_response` plus the audit row for someone else opening it."""
    response = document_response(profile, field)
    AuditLog.record(
        actor=request.user,
        action=AuditLog.Action.DOCUMENT_ACCESSED,
        target=profile.prn,
        document=field,
        route=request.path,
    )
    return response


# --- the student's own profile ---------------------------------------------


class MyProfileView(APIView):
    """GET and PATCH the signed-in student's profile."""

    permission_classes = [IsStudent]

    def get(self, request):
        profile = get_or_create_profile(request.user)
        return Response(self._payload(profile, request))

    def patch(self, request):
        profile = get_or_create_profile(request.user)
        serializer = OwnProfileSerializer(
            profile, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Headline, summary and confirmed values feed the vector and its filters.
        analysis_service.mark_needs_reindex(profile.pk)
        return Response(self._payload(serializer.instance, request))

    @staticmethod
    def _payload(profile: StudentProfile, request) -> dict:
        data = OwnProfileSerializer(profile, context={"request": request}).data
        # Serializer fields cannot call a method, so the completion breakdown
        # is attached here.
        data["completion_detail"] = profile.completion_detail()
        data["categories"] = match_service.profile_categories(profile)
        return data


class MyVisibilityView(APIView):
    """Change who can see this profile."""

    permission_classes = [IsStudent]

    def put(self, request):
        profile = get_or_create_profile(request.user)
        serializer = VisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile.visibility = serializer.validated_data["visibility"]
        profile.save(update_fields=["visibility", "updated_at"])
        return Response({"visibility": profile.visibility})


class MyResumeView(APIView):
    """
    Upload a resume and get back what the matching engine read from it.

    The extracted values pre-fill the profile but are returned separately as
    `suggestion`, so the UI can show the student what changed and let them
    correct it before it counts.
    """

    permission_classes = [IsStudent]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        profile = get_or_create_profile(request.user)
        serializer = ResumeUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]

        engine = get_engine()
        try:
            extracted = engine.parse_resume(upload, upload.name)
        except ResumeParseError as exc:
            # Nothing is stored: a resume we cannot read must not replace one
            # we could.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        upload.seek(0)
        profile.resume.save(upload.name, upload, save=False)
        profile.resume_filename = upload.name
        suggestion = profile.apply_parsed_resume(extracted)
        profile.save()
        # The full reading (LLM, vector) is slow, so it waits for
        # `POST me/resume/analyze`; the upload only says it is due.
        analysis = analysis_service.mark_pending(profile)

        AuditLog.record(
            actor=request.user,
            action=AuditLog.Action.RESUME_PARSED,
            target=profile.prn,
            filename=upload.name,
            **extracted.as_dict(),
        )

        return Response(
            {
                "suggestion": suggestion,
                "analysis": analysis_service.analysis_payload(profile, analysis),
                "profile": MyProfileView._payload(profile, request),
            },
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        profile = get_or_create_profile(request.user)
        analysis_service.forget(profile)
        if profile.resume:
            profile.resume.delete(save=False)
        profile.resume = None
        profile.resume_filename = ""
        profile.resume_text = ""
        profile.resume_uploaded_at = None
        profile.parsed_experience_years = None
        profile.parsed_education_levels = []
        profile.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyResumeFileView(APIView):
    """The student re-opens their own resume."""

    permission_classes = [IsStudent]

    def get(self, request):
        return document_response(get_or_create_profile(request.user), "resume")


class MyTranscriptFileView(APIView):
    """The student re-opens their own transcript."""

    permission_classes = [IsStudent]

    def get(self, request):
        return document_response(get_or_create_profile(request.user), "transcript")


class MyMarksheetView(APIView):
    """
    The student's 10th or 12th marksheet file.

    Nothing is parsed out of it, unlike the transcript: the marks beside it
    are the student's own statement, edited through `PATCH me` like any other
    self-reported field. This endpoint only moves the file.
    """

    permission_classes = [IsStudent]

    def post(self, request, level):
        profile = get_or_create_profile(request.user)
        serializer = MarksheetUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]

        field = f"marksheet_{level}"
        stored = getattr(profile, field)
        previous = stored.name if stored else None

        stored.save(upload.name, upload, save=False)
        setattr(profile, f"{field}_filename", upload.name)
        setattr(profile, f"{field}_uploaded_at", timezone.now())
        profile.save(update_fields=[field, f"{field}_filename", f"{field}_uploaded_at", "updated_at"])

        # Only once the new one is safely saved, as the transcript upload does.
        if previous and previous != getattr(profile, field).name:
            getattr(profile, field).storage.delete(previous)

        return Response(MyProfileView._payload(profile, request), status=status.HTTP_201_CREATED)

    def delete(self, request, level):
        profile = get_or_create_profile(request.user)
        field = f"marksheet_{level}"
        stored = getattr(profile, field)
        if stored:
            stored.delete(save=False)
        setattr(profile, field, None)
        setattr(profile, f"{field}_filename", "")
        setattr(profile, f"{field}_uploaded_at", None)
        profile.save(update_fields=[field, f"{field}_filename", f"{field}_uploaded_at", "updated_at"])
        return Response(MyProfileView._payload(profile, request))


class MyMarksheetFileView(APIView):
    """The student re-opens their own marksheet."""

    permission_classes = [IsStudent]

    def get(self, request, level):
        return document_response(get_or_create_profile(request.user), f"marksheet_{level}")


CGPA_ROSTER_TOLERANCE = Decimal("0.05")


class MyTranscriptView(APIView):
    """
    Upload the official transcript; read it; cross-check the CGPA.

    The transcript's PRN is the binding check: a transcript that names someone
    else is refused outright. The CGPA checks only open a review for an admin;
    they never block the upload.
    """

    permission_classes = [IsStudent]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        profile = get_or_create_profile(request.user)
        serializer = TranscriptUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]

        facts = parse_transcript(upload)
        upload.seek(0)

        from roster.models import normalise_prn

        if facts.prn and normalise_prn(facts.prn) != normalise_prn(profile.prn):
            # Refused before anything is saved: keeping a stranger's transcript
            # on file, even unlinked, is a privacy problem of its own. The audit
            # row is the only trace.
            AuditLog.record(
                actor=request.user,
                action=AuditLog.Action.TRANSCRIPT_PRN_MISMATCH,
                target=profile.prn,
                transcript_prn=facts.prn,
                filename=upload.name,
            )
            return Response(
                {
                    "detail": "The PRN on this transcript is not yours. Upload your own transcript.",
                    "reason": "prn_mismatch",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = profile.transcript.name if profile.transcript else None
        profile.transcript.save(upload.name, upload, save=False)
        profile.transcript_filename = upload.name
        profile.transcript_uploaded_at = timezone.now()
        profile.transcript_prn = facts.prn
        profile.transcript_school = facts.school
        profile.transcript_degree = facts.degree
        profile.parsed_cgpa = facts.printed_cgpa
        profile.recomputed_cgpa = facts.recomputed_cgpa
        # A new transcript makes any earlier confirmation stale.
        profile.confirmed_cgpa = None

        # Compared against, never written to: Student.cgpa is the registrar's
        # figure. A student-supplied transcript may only raise a flag for the
        # placement cell, otherwise anyone could edit their own eligibility.
        roster = profile.student.cgpa
        printed = facts.printed_cgpa
        reasons = []
        if printed is None:
            profile.cgpa_matches_roster = None
            reasons.append("no_cgpa_read")
        else:
            if roster is not None:
                profile.cgpa_matches_roster = abs(printed - roster) <= CGPA_ROSTER_TOLERANCE
                if not profile.cgpa_matches_roster:
                    reasons.append("differs_from_roster")
            else:
                profile.cgpa_matches_roster = None
            if facts.agrees is False:
                reasons.append("differs_from_recomputed")
        profile.cgpa_review_status = CgpaReview.OPEN if reasons else CgpaReview.NOT_NEEDED
        profile.save()

        if previous and previous != profile.transcript.name:
            profile.transcript.storage.delete(previous)

        if reasons:
            AuditLog.record(
                actor=request.user,
                action=AuditLog.Action.CGPA_MISMATCH_FLAGGED,
                target=profile.prn,
                reasons=reasons,
                printed=str(printed) if printed is not None else None,
                recomputed=(
                    str(facts.recomputed_cgpa) if facts.recomputed_cgpa is not None else None
                ),
                roster=str(roster) if roster is not None else None,
            )
        return Response(MyProfileView._payload(profile, request), status=status.HTTP_201_CREATED)


class MyConfirmCgpaView(APIView):
    """The student states their CGPA after a flag. Stored beside, not over, the others."""

    permission_classes = [IsStudent]

    def post(self, request):
        profile = get_or_create_profile(request.user)
        serializer = ConfirmCgpaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile.confirmed_cgpa = serializer.validated_data["cgpa"]
        profile.save(update_fields=["confirmed_cgpa", "updated_at"])
        return Response(MyProfileView._payload(profile, request))


def onboarding_payload(profile: StudentProfile) -> dict:
    student = profile.student
    return {
        "completed": profile.onboarding_completed,
        "dismissed": profile.onboarding_dismissed_at is not None,
        "student": {
            "prn": student.prn,
            "full_name": student.full_name,
            "email": student.email,
            "department": student.department,
            "school": student.school,
            "batch": student.batch,
            "year_of_study": student.year_of_study,
        },
        "phone": profile.phone,
        "personal_email": profile.personal_email,
        "career_path": profile.career_path,
        "career_path_detail": profile.career_path_detail,
        "also_attending_placements": profile.also_attending_placements,
        "headline": profile.headline,
        "summary": profile.summary,
    }


class MyOnboardingView(APIView):
    """The first-login form: roster facts read-only, a few fields to fill in."""

    permission_classes = [IsStudent]

    def get(self, request):
        return Response(onboarding_payload(get_or_create_profile(request.user)))

    def post(self, request):
        profile = get_or_create_profile(request.user)
        serializer = OnboardingSerializer(data=request.data, context={"profile": profile})
        serializer.is_valid(raise_exception=True)
        for key, value in serializer.validated_data.items():
            setattr(profile, key, value)
        profile.onboarding_completed_at = timezone.now()
        profile.save()
        analysis_service.mark_needs_reindex(profile.pk)
        return Response(onboarding_payload(profile))


class MyOnboardingDismissView(APIView):
    """'Later': hide the prompt without completing it."""

    permission_classes = [IsStudent]

    def post(self, request):
        profile = get_or_create_profile(request.user)
        profile.onboarding_dismissed_at = timezone.now()
        profile.save(update_fields=["onboarding_dismissed_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyResumeAnalyzeView(APIView):
    """
    Run the full reading of the student's resume: LLM, vector, suggestions.

    Idempotent on the resume text: asking again for a current analysis
    returns it without re-running the model. A reading that fell back to
    regex (model down, time budget spent) says `retryable`, and asking again
    retries. `manage.py analyze_resumes` is the backfill path.
    """

    permission_classes = [IsStudent]
    throttle_classes = [MatchingThrottle]

    def post(self, request):
        profile = get_or_create_profile(request.user)
        if not profile.has_resume:
            return Response(
                {"detail": "Upload a resume first."}, status=status.HTTP_400_BAD_REQUEST
            )
        analysis, _ = analysis_service.analyse(profile, actor=request.user)
        return Response(analysis_service.analysis_payload(profile, analysis))


class MyResumeAnalysisView(APIView):
    """The latest reading, for the frontend to poll while it is pending."""

    permission_classes = [IsStudent]

    def get(self, request):
        profile = get_or_create_profile(request.user)
        analysis = ResumeAnalysis.objects.filter(profile=profile).first()
        if analysis is None:
            return Response(
                {"detail": "No resume analysis yet."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(analysis_service.analysis_payload(profile, analysis))


class MyMatchView(APIView):
    """
    The student's own match against a JD they paste: score, breakdown and
    the skills they are missing. Their own profile whatever its visibility.
    """

    permission_classes = [IsStudent]
    throttle_classes = [MatchingThrottle]

    def post(self, request):
        serializer = JobDescriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_or_create_profile(request.user)
        job = match_service.read_job(serializer.validated_data["jd_text"])
        score = match_service.score_profile(profile, job)
        return Response({"match": score.as_dict(), "job": job.summary()})


class ConfirmParsedValuesView(APIView):
    """Accept or correct the values the parser pre-filled."""

    permission_classes = [IsStudent]

    def post(self, request):
        profile = get_or_create_profile(request.user)
        serializer = ConfirmParsedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile.experience_years = serializer.validated_data["experience_years"]
        profile.education_level = serializer.validated_data["education_level"]
        profile.parsed_values_confirmed = True
        profile.save(
            update_fields=[
                "experience_years",
                "education_level",
                "parsed_values_confirmed",
                "updated_at",
            ]
        )
        analysis_service.mark_needs_reindex(profile.pk)
        return Response(MyProfileView._payload(profile, request))


class OwnedEntryViewSet(viewsets.ModelViewSet):
    """
    Base for the child collections a student owns.

    The queryset is scoped to the signed-in student's own profile, so editing
    or deleting another student's entry is a 404 rather than a permission
    message that confirms the entry exists.
    """

    permission_classes = [IsStudent]
    model = None

    def get_queryset(self):
        profile = get_or_create_profile(self.request.user)
        return self.model.objects.filter(profile=profile)

    def perform_create(self, serializer):
        serializer.save(profile=get_or_create_profile(self.request.user))


class ExperienceViewSet(OwnedEntryViewSet):
    serializer_class = ExperienceEntrySerializer
    model = ExperienceEntry


class ProjectViewSet(OwnedEntryViewSet):
    serializer_class = ProjectEntrySerializer
    model = ProjectEntry


class SkillViewSet(OwnedEntryViewSet):
    serializer_class = ProfileSkillSerializer
    model = ProfileSkill

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Adding a skill twice is a no-op, not an error: the student meant to
        # have it, and it is there.
        from profiles.models import slugify_skill

        profile = get_or_create_profile(request.user)
        existing = ProfileSkill.objects.filter(
            profile=profile, slug=slugify_skill(serializer.validated_data["name"])
        ).first()
        if existing:
            return Response(ProfileSkillSerializer(existing).data, status=status.HTTP_200_OK)

        serializer.save(profile=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LogIdentityReadMixin:
    """
    Write an audit row when someone other than the student opens a profile.

    Only detail reads log; lists and the student's own `/profiles/me` do not.
    """

    def retrieve(self, request, *args, **kwargs):
        # get_object raises 404 for hidden/absent profiles before we log.
        profile = self.get_object()
        AuditLog.record(
            actor=request.user,
            action=AuditLog.Action.IDENTITY_ACCESSED,
            target=profile.prn,
            route=request.path,
        )
        return Response(self.get_serializer(profile).data)


# --- company-facing browse --------------------------------------------------


class CompanyProfileViewSet(
    LogIdentityReadMixin, ReportUnmatchedPrnsMixin, viewsets.ReadOnlyModelViewSet
):
    """
    Browse and filter student profiles.

    `visible_to` is applied first, so a hidden profile is not merely absent
    from the list -- it is absent from every query this viewset can make.
    """

    serializer_class = CompanyProfileSerializer
    permission_classes = [IsCompanyOrAdmin]
    prn_field = "student__prn"
    filterset_class = StudentProfileFilter
    search_fields = [
        "student__full_name",
        "student__prn",
        "headline",
        "summary",
        "skills__name",
        "projects__title",
    ]
    ordering_fields = ["student__cgpa", "experience_years", "updated_at"]
    ordering = ["-is_verified", "-student__cgpa"]
    # Addressed by the STUDENT's uuid, not the profile row's. That is the
    # identifier a platform token carries as `student_id`, so a caller holding
    # a token can build this URL without a lookup. PRN stays reachable as
    # ?prn=, which is what reconciliation needs.
    lookup_field = "student_id"

    def get_queryset(self):
        return (
            StudentProfile.objects.visible_to(self.request.user).with_related().distinct()
        )

    @action(detail=True, methods=["get"])
    def resume(self, request, student_id=None):
        """The resume of a profile this caller may see (`get_object` is `visible_to`)."""
        return audited_document(request, self.get_object(), "resume")

    @action(detail=True, methods=["get"])
    def transcript(self, request, student_id=None):
        # Companies never see transcripts, whatever the visibility or
        # verification: it holds grades the student shared only with the
        # placement cell. 404, not 403, so the route does not confirm a
        # transcript exists.
        raise Http404("No such document.")

    @action(detail=True, methods=["post", "delete"], permission_classes=[IsCompany])
    def shortlist(self, request, student_id=None):
        """Add or remove this student from the company's shortlist."""
        profile = self.get_object()

        company = request.user.company
        if company is None:
            return Response(
                {"detail": "This recruiter account is not linked to a company."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.method == "DELETE":
            CompanyShortlist.objects.filter(company=company, profile=profile).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = ShortlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CompanyShortlist.objects.update_or_create(
            company=company,
            profile=profile,
            defaults={"note": serializer.validated_data.get("note", "")},
        )
        return Response({"shortlisted": True}, status=status.HTTP_201_CREATED)


def build_outcomes(batch: int | None) -> dict:
    """
    Career-path counts per school, for roster students who have an account.

    Counting accounts, not profiles: a profile row is only created on first
    visit, so a student who never opened it would otherwise vanish from the
    totals. No profile means no path chosen, which is `undecided`, and that
    keeps the totals equal to the number of students the cell is tracking.
    """
    from accounts.models import Role, User
    from roster.models import Student
    from roster.reference import SCHOOLS

    students = Student.objects.filter(
        prn__in=User.objects.filter(role=Role.STUDENT).values("prn")
    )
    if batch is not None:
        students = students.filter(batch=batch)

    values = [value for value, _ in CareerPath.choices]
    rows: dict[str, dict] = {}
    totals = dict.fromkeys(values, 0)
    verified = attending = grand = 0
    for school, path, is_verified, attends in students.values_list(
        "school",
        "profile__career_path",
        "profile__is_verified",
        "profile__also_attending_placements",
    ):
        # A blank or unrecognised school still has to be counted somewhere.
        key = school if school in SCHOOLS else "unassigned"
        path = path if path in totals else CareerPath.UNDECIDED
        row = rows.setdefault(
            key,
            {
                "school": key,
                "school_name": SCHOOLS.get(key, "Unassigned"),
                "counts": dict.fromkeys(values, 0),
                "total": 0,
            },
        )
        row["counts"][path] += 1
        row["total"] += 1
        totals[path] += 1
        grand += 1
        verified += bool(is_verified)
        attending += bool(attends)

    order = [k for k in SCHOOLS if k in rows] + (["unassigned"] if "unassigned" in rows else [])
    return {
        "batch": batch,
        "paths": [{"value": v, "label": label} for v, label in CareerPath.choices],
        "rows": [rows[k] for k in order],
        "totals": totals,
        "grand_total": grand,
        "also_attending_placements": attending,
        "verified": verified,
    }


# --- admin ------------------------------------------------------------------


class AdminProfileViewSet(
    LogIdentityReadMixin, ReportUnmatchedPrnsMixin, viewsets.ReadOnlyModelViewSet
):
    """Every profile, whatever its visibility, plus verification."""

    serializer_class = AdminProfileSerializer
    permission_classes = [IsPlacementAdmin]
    prn_field = "student__prn"
    filterset_class = AdminProfileFilter
    search_fields = ["student__full_name", "student__prn", "student__email"]
    ordering_fields = ["student__prn", "updated_at", "is_verified"]
    lookup_field = "student_id"

    def get_queryset(self):
        # The analysis and the shortlist count ride the same query: every
        # row reads both. `stats` aggregates, so it gets no annotation.
        profiles = StudentProfile.objects.with_related().select_related("analysis")
        return profiles if self.action == "stats" else profiles.with_shortlist_count()

    def get_serializer_class(self):
        if self.action in ("retrieve", "verification", "cgpa_review"):
            return AdminProfileDetailSerializer
        return AdminProfileSerializer

    @action(detail=True, methods=["post"])
    def verification(self, request, student_id=None):
        """Mark a profile verified, or revoke it."""
        profile = self.get_object()
        serializer = VerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["is_verified"]:
            profile.mark_verified(request.user)
            action_name = AuditLog.Action.PROFILE_VERIFIED
        else:
            profile.revoke_verification()
            action_name = AuditLog.Action.PROFILE_UNVERIFIED

        AuditLog.record(
            actor=request.user,
            action=action_name,
            target=profile.prn,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(self.get_serializer(profile).data)

    @action(detail=True, methods=["get"])
    def resume(self, request, student_id=None):
        return audited_document(request, self.get_object(), "resume")

    @action(detail=True, methods=["get"])
    def transcript(self, request, student_id=None):
        return audited_document(request, self.get_object(), "transcript")

    @action(
        detail=True,
        methods=["get"],
        url_path=r"marksheet/(?P<level>10|12)",
        url_name="marksheet",
    )
    def marksheet(self, request, student_id=None, level=None):
        """A school marksheet, audited like every other document an admin opens."""
        return audited_document(request, self.get_object(), f"marksheet_{level}")

    @action(detail=True, methods=["post"], url_path="cgpa-review", url_name="cgpa-review")
    def cgpa_review(self, request, student_id=None):
        """Close an open CGPA review once the admin has checked the paper copy."""
        profile = self.get_object()
        serializer = CgpaReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile.cgpa_review_status = CgpaReview.RESOLVED
        profile.save(update_fields=["cgpa_review_status", "updated_at"])
        AuditLog.record(
            actor=request.user,
            action=AuditLog.Action.CGPA_REVIEW_RESOLVED,
            target=profile.prn,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(self.get_serializer(profile).data)

    def _outcomes(self, request) -> dict:
        # Runs the shared filter backends so an unknown query parameter is a
        # 400 here too; `batch` is a StudentProfileFilter field.
        self.filter_queryset(StudentProfile.objects.none())
        raw = request.query_params.get("batch")
        batch = None
        if raw not in (None, ""):
            try:
                batch = int(raw)
            except ValueError:
                raise ValidationError({"batch": "Enter a graduating year, e.g. 2026."})
        return build_outcomes(batch)

    @action(detail=False, methods=["get"])
    def outcomes(self, request):
        """Career-path counts per school (R3)."""
        return Response(self._outcomes(request))

    @action(detail=False, methods=["get"], url_path="outcomes/export", url_name="outcomes-export")
    def outcomes_export(self, request):
        body = self._outcomes(request)
        values = [p["value"] for p in body["paths"]]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="career-outcomes.csv"'
        writer = csv.writer(response)
        writer.writerow(["school", *values, "total"])
        for row in body["rows"]:
            writer.writerow([row["school"], *(row["counts"][v] for v in values), row["total"]])
        writer.writerow(["total", *(body["totals"][v] for v in values), body["grand_total"]])
        return response

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Aggregates behind the PRD's profile-completion metric."""
        profiles = self.get_queryset()
        total = profiles.count()
        completions = [profile.completion_percent for profile in profiles]
        return Response(
            {
                "profiles": total,
                "verified": profiles.filter(is_verified=True).count(),
                "with_resume": profiles.exclude(Q(resume="") | Q(resume=None)).count(),
                "onboarding_completed": profiles.filter(
                    onboarding_completed_at__isnull=False
                ).count(),
                "fully_complete": sum(1 for value in completions if value == 100),
                "average_completion_percent": round(sum(completions) / total) if total else 0,
                "visibility": {
                    choice: profiles.filter(visibility=choice).count()
                    for choice in profiles.values_list("visibility", flat=True).distinct()
                },
            }
        )
