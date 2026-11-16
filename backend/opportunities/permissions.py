"""Gates for the opportunity endpoints. Per-object ownership is the queryset's job."""

from rest_framework.permissions import BasePermission


class RecruiterHasCompany(BasePermission):
    """
    A recruiter acts for `request.user.company`; with none there is nothing to
    act for, so every company action is a 403. Students and admins pass.
    """

    message = "This recruiter account is not linked to a company."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if user and user.is_authenticated and user.is_company:
            return user.company_id is not None
        return True
