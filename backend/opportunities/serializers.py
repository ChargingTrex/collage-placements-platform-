"""Opportunity and application payloads. Company payloads are allow-lists."""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.reverse import reverse

from accounts.models import Company
from matching.extractors import EDUCATION_ORDER
from opportunities.models import Application, ApplicationEvent, Opportunity
from profiles.models import slugify_skill

PUBLIC_FIELDS = [
    "id", "company", "company_name", "title", "description", "role_type", "location",
    "openings", "required_skills", "eligible_departments", "min_cgpa",
    "min_experience_years", "required_education_levels", "salary_disclosed",
    "salary_min", "salary_max", "salary_period", "salary_currency", "deadline", "status",
    "created_at", "updated_at",
]
# What the owning company and the placement cell also see.
OWNER_FIELDS = PUBLIC_FIELDS + [
    "similarity_threshold", "submitted_at", "approved_by", "approved_at",
    "rejection_reason", "created_by",
]


class OpportunitySerializer(serializers.ModelSerializer):
    """Owner company and admin: every field, with the review trail."""

    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all(), required=False)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Opportunity
        fields = OWNER_FIELDS
        read_only_fields = [
            "id", "status", "submitted_at", "approved_by", "approved_at",
            "rejection_reason", "created_by", "created_at", "updated_at",
        ]

    def validate_required_skills(self, value):
        slugs = [slugify_skill(str(name)) for name in value or []]
        return list(dict.fromkeys(slug for slug in slugs if slug))

    def validate_eligible_departments(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise serializers.ValidationError("A list of department or programme names.")
        return [v.strip() for v in value]

    def validate_required_education_levels(self, value):
        if not isinstance(value, list) or any(v not in EDUCATION_ORDER for v in value):
            raise serializers.ValidationError(f"Each level must be one of {', '.join(EDUCATION_ORDER)}.")
        return value

    def validate_similarity_threshold(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError("Between 0 and 100.")
        return value

    def validate(self, attrs):
        current = self.instance
        get = lambda name: attrs.get(name, getattr(current, name, None))  # noqa: E731
        low, high = get("salary_min"), get("salary_max")
        if low is not None and high is not None and high < low:
            raise serializers.ValidationError({"salary_max": "Must not be below the minimum."})
        if not get("salary_disclosed"):
            # "Not disclosed" is a real state, not a zero.
            attrs.update(salary_min=None, salary_max=None)
        return attrs


class PublicOpportunitySerializer(OpportunitySerializer):
    """What a student sees: no review trail, no internal threshold."""

    class Meta(OpportunitySerializer.Meta):
        fields = PUBLIC_FIELDS
        read_only_fields = PUBLIC_FIELDS


# --- applications ------------------------------------------------------------


class ApplicationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationEvent
        fields = ["id", "from_status", "to_status", "note", "created_at"]


class CompanyApplicationSerializer(serializers.ModelSerializer):
    """
    The company-facing application: an allow-list.

    Nothing from the profile beyond what is named here: no marksheets, no
    student-typed or transcript CGPA, no career path. Contact details only
    when the placement cell verified the profile.
    """

    applied_at = serializers.DateTimeField(read_only=True)
    opportunity = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    resume_url = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()
    contact_available = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id", "status", "applied_at", "score", "similarity", "eligible",
            "eligibility_reasons", "opportunity", "prn", "full_name", "department",
            "programme", "school", "batch", "year_of_study", "cgpa_at_apply",
            "skills", "resume_url", "contact", "contact_available",
        ]
        read_only_fields = fields

    def get_opportunity(self, application):
        return {"id": application.opportunity_id, "title": application.opportunity.title}

    def get_skills(self, application):
        return [skill.name for skill in application.profile.skills.all()]

    def get_resume_url(self, application):
        return reverse("application-resume", args=[application.id])

    def get_contact(self, application):
        profile = application.profile
        if not profile.is_verified:
            return None
        return {"email": profile.student.email, "phone": profile.phone}

    def get_contact_available(self, application):
        return application.profile.is_verified


class StudentApplicationSerializer(CompanyApplicationSerializer):
    """The student's own: the same facts, the history, and the full posting."""

    events = ApplicationEventSerializer(many=True, read_only=True)

    class Meta(CompanyApplicationSerializer.Meta):
        fields = CompanyApplicationSerializer.Meta.fields + ["events"]
        read_only_fields = fields

    def get_opportunity(self, application):
        # A closed posting leaves the feed but stays readable here.
        return PublicOpportunitySerializer(application.opportunity, context=self.context).data


class AdminApplicationSerializer(CompanyApplicationSerializer):
    profile_student_id = serializers.UUIDField(source="profile.student_id", read_only=True)

    class Meta(CompanyApplicationSerializer.Meta):
        fields = CompanyApplicationSerializer.Meta.fields + ["profile_student_id"]
        read_only_fields = fields
