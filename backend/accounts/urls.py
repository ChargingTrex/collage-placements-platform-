"""Auth routes: signup, verification, login (password or OTP), and `me`."""

from django.urls import path

from accounts import demo, directory, views
from accounts.jwks import jwks_view

urlpatterns = [
    path("signup", views.signup, name="auth-signup"),
    path("verify", views.verify, name="auth-verify"),
    path("login", views.login, name="auth-login"),
    path("otp/request", views.otp_request, name="auth-otp-request"),
    path("otp/login", views.otp_login, name="auth-otp-login"),
    path("refresh", views.RefreshView.as_view(), name="auth-refresh"),
    path("me", views.me, name="auth-me"),
    path("jwks", jwks_view, name="auth-jwks"),
    # The placement cell's directory of every account (read-only, audited).
    path("admin/users", directory.UserDirectoryView.as_view(), name="auth-admin-users"),
    path(
        "admin/users/summary",
        directory.UserDirectorySummaryView.as_view(),
        name="auth-admin-users-summary",
    ),
    # Always routed; both answer 404 unless DEBUG and DEMO_MODE are on, checked
    # per request so a settings change cannot leave a stale route open.
    path("demo/personas", demo.DemoPersonasView.as_view(), name="auth-demo-personas"),
    path("demo/login", demo.DemoLoginView.as_view(), name="auth-demo-login"),
]
