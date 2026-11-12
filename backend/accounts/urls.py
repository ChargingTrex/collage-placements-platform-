"""Auth routes: signup, verification, login (password or OTP), and `me`."""

from django.urls import path

from accounts import views
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
]
