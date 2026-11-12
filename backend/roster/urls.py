"""Roster administration routes (placement-cell admins only)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from roster import views

# No trailing slashes: every hand-written route in this project is
# slashless (/api/health, /api/auth/login), and mixing the two styles
# means half the API answers 301 instead of 200.
router = DefaultRouter(trailing_slash=False)
router.register("students", views.StudentViewSet, basename="roster-student")
router.register("flagged", views.FlaggedSignupViewSet, basename="roster-flagged")

urlpatterns = [
    path("upload", views.upload_roster, name="roster-upload"),
    path("", include(router.urls)),
]
