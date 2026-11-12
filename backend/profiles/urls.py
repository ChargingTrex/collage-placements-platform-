"""Student profile routes: own profile, company browse, admin verification."""

from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from profiles import views

router = DefaultRouter(trailing_slash=False)
router.register("me/experience", views.ExperienceViewSet, basename="my-experience")
router.register("me/projects", views.ProjectViewSet, basename="my-projects")
router.register("me/skills", views.SkillViewSet, basename="my-skills")
router.register("students", views.CompanyProfileViewSet, basename="company-profile")
router.register("admin", views.AdminProfileViewSet, basename="admin-profile")

urlpatterns = [
    path("me", views.MyProfileView.as_view(), name="my-profile"),
    path("me/visibility", views.MyVisibilityView.as_view(), name="my-visibility"),
    path("me/resume", views.MyResumeView.as_view(), name="my-resume"),
    path("me/resume/file", views.MyResumeFileView.as_view(), name="my-resume-file"),
    path("me/transcript", views.MyTranscriptView.as_view(), name="my-transcript"),
    path("me/transcript/file", views.MyTranscriptFileView.as_view(), name="my-transcript-file"),
    # `<level>` is constrained to the two school levels, so an unknown one is a
    # 404 from the router rather than a field lookup that never matches.
    re_path(
        r"^me/marksheet/(?P<level>10|12)$", views.MyMarksheetView.as_view(), name="my-marksheet"
    ),
    re_path(
        r"^me/marksheet/(?P<level>10|12)/file$",
        views.MyMarksheetFileView.as_view(),
        name="my-marksheet-file",
    ),
    path("me/confirm-cgpa", views.MyConfirmCgpaView.as_view(), name="my-confirm-cgpa"),
    path("me/onboarding", views.MyOnboardingView.as_view(), name="my-onboarding"),
    path(
        "me/onboarding/dismiss",
        views.MyOnboardingDismissView.as_view(),
        name="my-onboarding-dismiss",
    ),
    path("me/resume/analyze", views.MyResumeAnalyzeView.as_view(), name="my-resume-analyze"),
    path("me/resume/analysis", views.MyResumeAnalysisView.as_view(), name="my-resume-analysis"),
    path("me/match", views.MyMatchView.as_view(), name="my-match"),
    path("me/confirm-parsed", views.ConfirmParsedValuesView.as_view(), name="my-confirm-parsed"),
    path("", include(router.urls)),
]
