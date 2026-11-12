from django.contrib import admin

from core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target", "actor")
    list_filter = ("action",)
    search_fields = ("target",)
    readonly_fields = ("actor", "action", "target", "detail", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
