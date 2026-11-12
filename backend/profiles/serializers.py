"""Request/response shapes for the student profile API."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from rest_framework import serializers

from core.storage import (
    RESUME_EXTENSIONS,
    validate_marksheet,
    validate_resume,
    validate_transcript,
)
from profiles.models import (
    CareerPath,
    CompanyShortlist,
    EducationLevel,
    ExperienceEntry,
    ProfileSkill,
    ProjectEntry,
    StudentProfile,
    Visibility,
)


class StringListField(serializers.ListField):
    """A list of short, trimmed, de-duplicated strings (tech stack, skills used).

    Blanks are allowed past the child validator so a trailing empty chip from
    the UI is dropped here rather than rejected as a form error.
    """

    child = serializers.CharField(max_length=60, trim_whitespace=True, allow_blank=True)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        seen: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned.lower() not in {v.lower() for v in seen}:
                seen.append(cleaned)
        if len(seen) > 30:
            raise serializers.ValidationError("At most 30 entries.")
        return seen


class ProfileSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileSkill
        fields = ("id", "name", "slug", "category")
        read_only_fields = ("id", "slug")

    def validate_name(self, value: str) -> str:
        from profiles.models import slugify_skill

        if not slugify_skill(value):
            raise serializers.ValidationError("Enter a skill name.")
        return value.strip()


class ExperienceEntrySerializer(serializers.ModelSerializer):
    skills_used = StringListField(required=False)
    is_current = serializers.BooleanField(read_only=True)
    duration_months = serializers.IntegerField(read_only=True)

    class Meta:
        model = ExperienceEntry
        fields = (
            "id",
            "role",
            "organization",
            "kind",
            "start_date",
            "end_date",
            "location",
            "description",
            "skills_used",
            "is_current",
            "duration_months",
        )
        read_only_fields = ("id", "is_current", "duration_months")

    def validate(self, attrs):
        # On PATCH only one of the two dates may be present in the payload.
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "The end date cannot be before the start date."}
            )
        return attrs


class ProjectEntrySerializer(serializers.ModelSerializer):
    tech_stack = StringListField(required=False)

    class Meta:
        model = ProjectEntry
        fields = (
            "id",
            "title",
            "description",
            "tech_stack",
            "role",
            "team_size",
            "repo_url",
            "demo_url",
            "video_url",
            "started_on",
            "completed_on",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        started = attrs.get("started_on", getattr(self.instance, "started_on", None))
        completed = attrs.get("completed_on", getattr(self.instance, "completed_on", None))
        if started and completed and completed < started:
            raise serializers.ValidationError(
                {"completed_on": "The completion date cannot be before the start date."}
            )
        return attrs


class RosterFactsSerializer(serializers.Serializer):
    """The college's record. Read-only everywhere in this API."""

    prn = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    department = serializers.CharField(read_only=True)
    batch = serializers.IntegerField(read_only=True)
    cgpa = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True)


class OwnRosterFactsSerializer(RosterFactsSerializer):
    """Roster facts for the student and the placement cell: adds school and year.

    Companies keep the narrower base serializer; they get no new fields.
    """

    school = serializers.CharField(read_only=True)
    year_of_study = serializers.IntegerField(read_only=True)


def check_career_path(path: str, detail: str) -> str:
    """
    Return the detail to store for `path`, or raise.

    'other' must say what it is; every other path stores "" so a stale
    description never outlives the choice it explained.
    """
    if path == CareerPath.OTHER:
        detail = (detail or "").strip()
        if not detail:
            raise serializers.ValidationError(
                {"career_path_detail": "Say what the 'other' path is."}
            )
        return detail
    return ""


def check_personal_email(personal_email: str, college_email: str) -> None:
    # A second mailbox is the whole point: the college address stops working
    # after graduation.
    if personal_email and personal_email.strip().lower() == (college_email or "").strip().lower():
        raise serializers.ValidationError(
            {"personal_email": "Use an address different from your college email."}
        )


class _BaseProfileSerializer(serializers.ModelSerializer):
    student = RosterFactsSerializer(read_only=True)
    skills = ProfileSkillSerializer(many=True, read_only=True)
    experience_entries = ExperienceEntrySerializer(many=True, read_only=True)
    projects = ProjectEntrySerializer(many=True, read_only=True)
    completion_percent = serializers.IntegerField(read_only=True)


class OwnProfileSerializer(_BaseProfileSerializer):
    """What the student sees and edits. Includes their own private fields."""

    student = OwnRosterFactsSerializer(read_only=True)
    completion_detail = serializers.DictField(read_only=True)
    resume_url = serializers.SerializerMethodField()
    transcript_url = serializers.SerializerMethodField()
    marksheet_10_url = serializers.SerializerMethodField()
    marksheet_12_url = serializers.SerializerMethodField()
    onboarding_completed = serializers.BooleanField(read_only=True)
    parsed_differs_from_confirmed = serializers.BooleanField(read_only=True)
    #: How many companies would still see this profile under "shortlisted
    #: only". Zero means that setting is silently identical to "hidden", which
    #: the student has no other way to find out.
    shortlisted_by_count = serializers.SerializerMethodField()
    verified_by_email = serializers.CharField(
        source="verified_by.email", read_only=True, default=None
    )

    class Meta:
        model = StudentProfile
        fields = (
            "id",
            "student_id",
            "student",
            "headline",
            "summary",
            "phone",
            "github_url",
            "linkedin_url",
            "website_url",
            "experience_years",
            "education_level",
            "visibility",
            "career_path",
            "career_path_detail",
            "also_attending_placements",
            "personal_email",
            "onboarding_completed",
            "onboarding_completed_at",
            "transcript_url",
            "transcript_filename",
            "transcript_prn",
            "transcript_school",
            "transcript_degree",
            "parsed_cgpa",
            "recomputed_cgpa",
            "confirmed_cgpa",
            "cgpa_matches_roster",
            "cgpa_review_status",
            "shortlisted_by_count",
            "is_verified",
            "verified_at",
            "verified_by_email",
            "skills",
            "experience_entries",
            "projects",
            "completion_percent",
            "completion_detail",
            "resume_url",
            "resume_filename",
            "resume_uploaded_at",
            "parsed_experience_years",
            "parsed_education_levels",
            "parsed_values_confirmed",
            "parsed_differs_from_confirmed",
            "marksheet_10_url",
            "marksheet_10_filename",
            "marksheet_10_uploaded_at",
            "marks_10_percentage",
            "marks_10_board",
            "marks_10_year",
            "marksheet_12_url",
            "marksheet_12_filename",
            "marksheet_12_uploaded_at",
            "marks_12_percentage",
            "marks_12_board",
            "marks_12_year",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "student_id",
            "student",
            "shortlisted_by_count",
            "is_verified",
            "verified_at",
            "verified_by_email",
            "skills",
            "experience_entries",
            "projects",
            "completion_percent",
            "completion_detail",
            "resume_url",
            "resume_filename",
            "resume_uploaded_at",
            "parsed_experience_years",
            "parsed_education_levels",
            "parsed_differs_from_confirmed",
            "onboarding_completed",
            "onboarding_completed_at",
            "transcript_url",
            "transcript_filename",
            "transcript_prn",
            "transcript_school",
            "transcript_degree",
            "parsed_cgpa",
            "recomputed_cgpa",
            "confirmed_cgpa",
            "cgpa_matches_roster",
            "cgpa_review_status",
            # The marks themselves are the student's own statement and stay
            # writable; only the files and their metadata are set by upload.
            "marksheet_10_url",
            "marksheet_10_filename",
            "marksheet_10_uploaded_at",
            "marksheet_12_url",
            "marksheet_12_filename",
            "marksheet_12_uploaded_at",
            "updated_at",
        )

    # Documents are served by audited API routes, never from /media/, so the
    # URL we hand out is the route, not the storage path.
    def get_resume_url(self, profile: StudentProfile) -> str | None:
        if not profile.resume:
            return None
        return reverse("my-resume-file")

    def get_transcript_url(self, profile: StudentProfile) -> str | None:
        if not profile.transcript:
            return None
        return reverse("my-transcript-file")

    def get_marksheet_10_url(self, profile: StudentProfile) -> str | None:
        return self._marksheet_url(profile, "10")

    def get_marksheet_12_url(self, profile: StudentProfile) -> str | None:
        return self._marksheet_url(profile, "12")

    def _marksheet_url(self, profile: StudentProfile, level: str) -> str | None:
        if not getattr(profile, f"marksheet_{level}"):
            return None
        return reverse("my-marksheet-file", args=[level])

    def validate_personal_email(self, value: str) -> str:
        return value.strip()

    def validate(self, attrs):
        profile = self.instance
        path = attrs.get("career_path", profile.career_path)
        detail = attrs.get("career_path_detail", profile.career_path_detail)
        attrs["career_path_detail"] = check_career_path(path, detail)
        if "personal_email" in attrs:
            check_personal_email(attrs["personal_email"], profile.student.email)
        return attrs

    def get_shortlisted_by_count(self, profile: StudentProfile) -> int:
        # A list annotates it on the page query (`with_shortlist_count`);
        # a single profile is one COUNT either way.
        annotated = getattr(profile, "shortlist_total", None)
        return annotated if annotated is not None else profile.shortlisted_by.count()

    def update(self, instance, validated_data):
        # Editing either pre-filled field is the student confirming it, which
        # is what stops the next upload from overwriting their correction.
        if "experience_years" in validated_data or "education_level" in validated_data:
            instance.parsed_values_confirmed = True
        return super().update(instance, validated_data)


class CompanyProfileSerializer(_BaseProfileSerializer):
    """
    What a company sees.

    Deliberately narrower than the student's own view: no resume text, no
    parser internals, and contact details only once the profile is verified,
    so an unverified profile cannot be scraped for phone numbers.
    """

    prn = serializers.CharField(read_only=True)
    contact = serializers.SerializerMethodField()
    resume_url = serializers.SerializerMethodField()
    is_shortlisted = serializers.SerializerMethodField()
    # Not the student's own figure: that one counts career_path, which
    # companies must not be able to infer (see company_completion_percent).
    completion_percent = serializers.IntegerField(
        source="company_completion_percent", read_only=True
    )

    class Meta:
        model = StudentProfile
        fields = (
            "id",
            # The identifier a client addresses this profile by. PRN is for
            # display and reconciliation; it is not a path parameter.
            "student_id",
            "prn",
            "student",
            "headline",
            "summary",
            "experience_years",
            "education_level",
            "is_verified",
            "verified_at",
            "skills",
            "experience_entries",
            "projects",
            "completion_percent",
            "contact",
            "resume_url",
            "is_shortlisted",
            "updated_at",
        )
        read_only_fields = fields

    def get_contact(self, profile: StudentProfile) -> dict | None:
        if not profile.is_verified:
            return None
        return {"email": profile.student.email, "phone": profile.phone}

    def get_resume_url(self, profile: StudentProfile) -> str | None:
        # The company route re-checks visibility and audits each open; a
        # direct /media/ link would bypass both. There is deliberately no
        # transcript equivalent: companies never see transcripts.
        if not profile.resume:
            return None
        return reverse("company-profile-resume", args=[profile.student_id])

    def get_is_shortlisted(self, profile: StudentProfile) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated or not request.user.is_company:
            return False
        return CompanyShortlist.objects.filter(
            company=request.user.company_id, profile=profile
        ).exists()


class AdminProfileSerializer(OwnProfileSerializer):
    """
    The admin view: everything the student sees, plus the visibility state
    and the preliminary verification flags.

    The flags are the only place resume-vs-form-vs-roster disagreements
    surface, and this is the only serializer that carries them. They are
    advice for the admin: `mark_verified` never looks at them.
    """

    verification_checks = serializers.SerializerMethodField()
    warning_count = serializers.SerializerMethodField()

    def get_resume_url(self, profile: StudentProfile) -> str | None:
        if not profile.resume:
            return None
        return reverse("admin-profile-resume", args=[profile.student_id])

    def get_transcript_url(self, profile: StudentProfile) -> str | None:
        if not profile.transcript:
            return None
        return reverse("admin-profile-transcript", args=[profile.student_id])

    def _marksheet_url(self, profile: StudentProfile, level: str) -> str | None:
        # The audited admin route, not the student's own: every open by
        # someone other than the student writes a document_accessed row.
        if not getattr(profile, f"marksheet_{level}"):
            return None
        return reverse("admin-profile-marksheet", args=[profile.student_id, level])

    class Meta(OwnProfileSerializer.Meta):
        fields = OwnProfileSerializer.Meta.fields + ("user", "verification_checks", "warning_count")
        read_only_fields = fields

    def _flags(self, profile: StudentProfile) -> list:
        """Computed once per profile per render: both fields read them."""
        from profiles.verification import verification_checks

        cache = self.__dict__.setdefault("_flag_cache", {})
        if profile.pk not in cache:
            cache[profile.pk] = verification_checks(profile)
        return cache[profile.pk]

    def get_verification_checks(self, profile: StudentProfile) -> list[dict]:
        return [flag.as_dict() for flag in self._flags(profile)]

    def get_warning_count(self, profile: StudentProfile) -> int:
        from profiles.verification import warning_count

        return warning_count(self._flags(profile))


class AdminProfileDetailSerializer(AdminProfileSerializer):
    """One profile for an admin: also what the resume says about age, DOB, CGPA and contacts."""

    resume_facts_admin = serializers.SerializerMethodField()
    cgpa_sources = serializers.SerializerMethodField()

    class Meta(AdminProfileSerializer.Meta):
        fields = AdminProfileSerializer.Meta.fields + ("resume_facts_admin", "cgpa_sources")
        read_only_fields = fields

    def get_resume_facts_admin(self, profile: StudentProfile) -> dict | None:
        from profiles.verification import resume_facts_admin

        return resume_facts_admin(profile)

    def get_cgpa_sources(self, profile: StudentProfile) -> dict:
        from profiles.verification import cgpa_sources

        return cgpa_sources(profile)


class ResumeUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, upload):
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_resume(upload)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return upload

    @staticmethod
    def allowed_extensions() -> list[str]:
        return sorted(RESUME_EXTENSIONS)


class TranscriptUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, upload):
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_transcript(upload)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return upload


class MarksheetUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, upload):
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_marksheet(upload)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return upload


class ConfirmCgpaSerializer(serializers.Serializer):
    cgpa = serializers.DecimalField(
        max_digits=4, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("10")
    )


class CgpaReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["resolved"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class OnboardingSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    career_path = serializers.ChoiceField(choices=CareerPath.choices)
    career_path_detail = serializers.CharField(
        required=False, allow_blank=True, max_length=200
    )
    also_attending_placements = serializers.BooleanField(required=False)
    personal_email = serializers.EmailField(required=False, allow_blank=True)
    headline = serializers.CharField(required=False, allow_blank=True, max_length=120)
    summary = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        attrs["career_path_detail"] = check_career_path(
            attrs["career_path"], attrs.get("career_path_detail", "")
        )
        check_personal_email(
            attrs.get("personal_email", ""), self.context["profile"].student.email
        )
        return attrs


class VisibilitySerializer(serializers.Serializer):
    visibility = serializers.ChoiceField(choices=Visibility.choices)


class VerificationSerializer(serializers.Serializer):
    is_verified = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ShortlistSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ConfirmParsedSerializer(serializers.Serializer):
    """Accept or correct what the parser read off the resume."""

    experience_years = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=Decimal("0"), max_value=Decimal("50")
    )
    education_level = serializers.ChoiceField(
        choices=EducationLevel.choices, allow_blank=True
    )
