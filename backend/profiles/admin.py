from django.contrib import admin

from profiles.models import (
    CompanyShortlist,
    ExperienceEntry,
    ProfileSkill,
    ProjectEntry,
    ResumeAnalysis,
    StudentProfile,
)


@admin.register(ResumeAnalysis)
class ResumeAnalysisAdmin(admin.ModelAdmin):
    """Read-only: an analysis is the engine's record, changed only by re-running it."""

    list_display = ("profile", "status", "source", "model_name", "needs_reindex", "analysed_at")
    list_filter = ("status", "source", "needs_reindex")
    search_fields = ("profile__student__prn",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class SkillInline(admin.TabularInline):
    model = ProfileSkill
    extra = 0


class ExperienceInline(admin.TabularInline):
    model = ExperienceEntry
    extra = 0


class ProjectInline(admin.TabularInline):
    model = ProjectEntry
    extra = 0


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("prn", "headline", "visibility", "is_verified", "completion_percent")
    list_filter = ("visibility", "is_verified", "student__department", "student__batch")
    search_fields = ("student__prn", "student__full_name", "student__email", "headline")
    readonly_fields = (
        "student",
        "user",
        "resume_text",
        "parsed_experience_years",
        "parsed_education_levels",
        "verified_at",
        "verified_by",
    )
    inlines = [SkillInline, ExperienceInline, ProjectInline]

    @admin.display(description="Completion")
    def completion_percent(self, profile):
        return f"{profile.completion_percent}%"


@admin.register(CompanyShortlist)
class CompanyShortlistAdmin(admin.ModelAdmin):
    list_display = ("company", "profile", "created_at")
    search_fields = ("company__email", "profile__student__prn")
