"""The skill graph and role categories are curated by placement admins in Django admin."""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction

from matching.models import RoleCategory, Skill, SkillAlias, SkillAliasSuggestion


class SkillAliasInline(admin.TabularInline):
    model = SkillAlias
    extra = 1
    fields = ("name", "slug")
    readonly_fields = ("slug",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "implied")
    search_fields = ("name", "slug", "aliases__name")
    readonly_fields = ("slug",)
    filter_horizontal = ("implies",)
    inlines = [SkillAliasInline]

    @admin.display(description="Implies")
    def implied(self, skill):
        return ", ".join(target.name for target in skill.implies.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("implies")


@admin.register(SkillAlias)
class SkillAliasAdmin(admin.ModelAdmin):
    list_display = ("name", "skill", "slug")
    search_fields = ("name", "slug", "skill__name")
    readonly_fields = ("slug",)
    autocomplete_fields = ("skill",)


@admin.register(SkillAliasSuggestion)
class SkillAliasSuggestionAdmin(admin.ModelAdmin):
    """
    Embedding guesses, reviewed by a person.

    Approving -- by the action or by saving the row as approved -- is what
    creates the alias. Nothing else does.
    """

    list_display = ("alias", "skill", "similarity", "status", "created_at", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("alias", "skill__name")
    readonly_fields = ("slug", "similarity", "created_at", "reviewed_at")
    autocomplete_fields = ("skill",)
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description="Approve: add as an alias of the suggested skill")
    def approve_selected(self, request, queryset):
        pending = queryset.filter(status=SkillAliasSuggestion.Status.PENDING)
        count = 0
        for suggestion in pending.select_related("skill"):
            try:
                suggestion.approve()
            except ValidationError as exc:
                self.message_user(request, " ".join(exc.messages), level=messages.WARNING)
                continue
            count += 1
        self.message_user(request, f"Approved {count} suggestion(s).")

    @admin.action(description="Reject")
    def reject_selected(self, request, queryset):
        count = 0
        for suggestion in queryset.filter(status=SkillAliasSuggestion.Status.PENDING):
            suggestion.reject()
            count += 1
        self.message_user(request, f"Rejected {count} suggestion(s).")

    def save_model(self, request, obj, form, change):
        approving = obj.status == SkillAliasSuggestion.Status.APPROVED and (
            not change
            or SkillAliasSuggestion.objects.filter(pk=obj.pk)
            .exclude(status=SkillAliasSuggestion.Status.APPROVED)
            .exists()
        )
        if approving:
            # Saved pending first: `approve()` is what marks it approved, and
            # a spelling that already means another skill must stay pending.
            obj.status = SkillAliasSuggestion.Status.PENDING
        super().save_model(request, obj, form, change)
        if approving:
            try:
                obj.approve()
            except ValidationError as exc:
                self.message_user(request, " ".join(exc.messages), level=messages.ERROR)


@admin.register(RoleCategory)
class RoleCategoryAdmin(admin.ModelAdmin):
    """
    Categories are learnt from JDs; admins tidy them: rename, merge, delete.

    Profiles keep the names they were given until `manage.py recategorise`
    runs, so each change here says to run it.
    """

    list_display = ("name", "jd_count", "top_skill_names", "alias_names", "centroid_model", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("jd_count", "skill_weights", "centroid_model", "centroid_count", "created_at", "updated_at")
    exclude = ("centroid",)
    actions = ["merge_selected"]

    @admin.display(description="Top skills")
    def top_skill_names(self, category):
        return ", ".join(category.top_skills())

    @admin.display(description="Aliases")
    def alias_names(self, category):
        return ", ".join(category.aliases or [])

    def save_model(self, request, obj, form, change):
        # A renamed category keeps its old name as an alias, so JDs that
        # still use it join this category instead of starting a new one.
        if change and obj.pk:
            old = RoleCategory.objects.filter(pk=obj.pk).values_list("name", flat=True).first()
            if old and old != obj.name:
                obj.add_alias(old)
        super().save_model(request, obj, form, change)
        if change:
            self.message_user(request, "Run `manage.py recategorise` to update profiles.")

    @admin.action(description="Merge into the one with the most JDs")
    def merge_selected(self, request, queryset):
        chosen = list(queryset.order_by("-jd_count", "created_at", "pk"))
        if len(chosen) < 2:
            self.message_user(request, "Select at least two categories to merge.", level=messages.WARNING)
            return
        target, others = chosen[0], chosen[1:]
        with transaction.atomic():
            target.absorb(*others)
            for other in others:
                other.delete()
            target.save()
        self.message_user(
            request,
            f"Merged {len(others)} into {target.name}. Run `manage.py recategorise` to update profiles.",
        )
