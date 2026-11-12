from django.contrib import admin

from roster.models import FlaggedSignup, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("prn", "full_name", "email", "department", "batch", "cgpa", "is_placement_eligible")
    list_filter = ("department", "batch", "is_placement_eligible")
    search_fields = ("prn", "email", "full_name")
    ordering = ("prn",)


@admin.register(FlaggedSignup)
class FlaggedSignupAdmin(admin.ModelAdmin):
    list_display = ("prn", "email", "reason", "attempts", "status", "updated_at")
    list_filter = ("status", "reason")
    search_fields = ("prn", "email")
    readonly_fields = ("prn", "email", "reason", "attempts", "created_at", "updated_at")
