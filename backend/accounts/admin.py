from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "prn", "role", "is_active", "email_verified_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "prn", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password", "role", "prn", "full_name")}),
        ("Status", {"fields": ("is_active", "email_verified_at")}),
        ("Permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "role", "prn", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("last_login", "email_verified_at")
