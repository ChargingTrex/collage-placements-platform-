"""
Company-facing profile search.

The PRD's filter set: department, skills, CGPA range, project keywords, plus
verification status and the role category a profile was sorted into. Skills
are matched on their slug so "Node.js" and "nodejs" are the same filter.
"""

from __future__ import annotations

from django.db.models import Q
from django_filters import rest_framework as filters

from core.filters import HumanKeyFilter, HumanKeyInFilter
from profiles.models import CareerPath, StudentProfile, slugify_skill


class CsvCharFilter(filters.CharFilter):
    """`?skills=python,django` -> every named skill must be present."""

    def filter(self, queryset, value):
        if not value:
            return queryset
        slugs = [slugify_skill(part) for part in value.split(",")]
        for slug in filter(None, slugs):
            # Chained rather than `__in`: asking for python AND django should
            # not return a profile that only has one of them.
            queryset = queryset.filter(skills__slug=slug)
        return queryset.distinct()


class ProjectKeywordFilter(filters.CharFilter):
    """Free text across project titles, descriptions and tech stacks."""

    def filter(self, queryset, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(projects__title__icontains=value)
            | Q(projects__description__icontains=value)
            | Q(projects__tech_stack__icontains=value)
        ).distinct()


class RoleCategoryFilter(filters.CharFilter):
    """
    `?category=Backend Engineer`: profiles sorted into that role, any case.

    Matched in Python over the stored category lists rather than with a
    JSON lookup, which SQLite and Postgres do not read alike. A roster is
    thousands of rows, not millions.
    """

    def filter(self, queryset, value):
        wanted = (value or "").strip().lower()
        if not wanted:
            return queryset
        from profiles.models import ResumeAnalysis

        ids = [
            profile_id
            for profile_id, names in ResumeAnalysis.objects.values_list("profile_id", "categories")
            if any(isinstance(name, str) and name.lower() == wanted for name in names or [])
        ]
        return queryset.filter(pk__in=ids)


class StudentProfileFilter(filters.FilterSet):
    # PRN is no longer a path parameter (G2), so it has to be a first-class
    # filter -- otherwise reconciling a profile against a roster export means
    # paging the whole list.
    prn = HumanKeyFilter(field_name="student__prn")
    prns = HumanKeyInFilter(field_name="student__prn")
    # The admin who verified the profile, by ADM-nnnn (matched upper-cased).
    verified_by = HumanKeyFilter(field_name="verified_by__admin_id")

    department = filters.CharFilter(field_name="student__department", lookup_expr="iexact")
    batch = filters.NumberFilter(field_name="student__batch")
    cgpa_min = filters.NumberFilter(field_name="student__cgpa", lookup_expr="gte")
    cgpa_max = filters.NumberFilter(field_name="student__cgpa", lookup_expr="lte")
    skills = CsvCharFilter()
    project_keyword = ProjectKeywordFilter()
    verified = filters.BooleanFilter(field_name="is_verified")
    min_experience_years = filters.NumberFilter(
        field_name="experience_years", lookup_expr="gte"
    )
    education_level = filters.CharFilter(field_name="education_level", lookup_expr="iexact")
    category = RoleCategoryFilter()

    class Meta:
        model = StudentProfile
        fields = [
            "prn",
            "prns",
            "department",
            "batch",
            "cgpa_min",
            "cgpa_max",
            "skills",
            "project_keyword",
            "verified",
            "verified_by",
            "min_experience_years",
            "education_level",
            "category",
        ]


class AdminProfileFilter(StudentProfileFilter):
    """
    The company filter set plus the two the outcomes dashboard drills on.

    These live here and not on `StudentProfileFilter` because that one is
    shared with the company-facing list. `career_path` is placement-cell
    planning data: a recruiter who could filter on it would learn which
    students are preparing for UPSC or leaving for a master's, which is the
    inference `company_completion_percent` exists to prevent. Keeping it on
    the admin subclass means the company list rejects it as an unknown
    parameter, the same as any other typo.
    """

    # Validated against the choices, so a typo is a 400 rather than a
    # silently empty page that reads as "nobody is on this path".
    career_path = filters.ChoiceFilter(choices=CareerPath.choices)
    school = filters.CharFilter(field_name="student__school", lookup_expr="iexact")

    class Meta(StudentProfileFilter.Meta):
        fields = StudentProfileFilter.Meta.fields + ["career_path", "school"]
