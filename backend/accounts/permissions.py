"""Role gates. Authorization is enforced here and in querysets, never in the UI."""

from rest_framework.permissions import BasePermission


class IsPlacementAdmin(BasePermission):
    message = "Only placement cell admins can do this."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_placement_admin)


class IsStudent(BasePermission):
    message = "Only students can do this."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_student)


class IsCompany(BasePermission):
    message = "Only company accounts can do this."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_company)


class IsCompanyOrAdmin(BasePermission):
    message = "Only companies and placement cell admins can do this."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_company or user.is_placement_admin)
        )
