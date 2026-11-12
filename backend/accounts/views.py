"""
Auth endpoints.

Shape of the student journey:
    POST /api/auth/signup        PRN + college email -> roster match -> code emailed
    POST /api/auth/verify        code + chosen password -> account active, tokens
    POST /api/auth/login         PRN or email + password -> tokens
    POST /api/auth/otp/request   email a login code instead of using a password
    POST /api/auth/otp/login     that code -> tokens
    POST /api/auth/refresh       rotate the access token
    GET  /api/auth/me            who am I

Admin and company accounts use the same login endpoints with their email; they
have no PRN and never go through signup, exactly as the PRD specifies.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.models import OneTimeCode, RevokedTokenFamily, User
from core.models import AuditLog
from accounts.otp import IssuedCode, OtpError, OtpRateLimited, issue_code, resolve_user, verify_code
from accounts.serializers import (
    LoginSerializer,
    OtpLoginSerializer,
    OtpRequestSerializer,
    SignupSerializer,
    UserSerializer,
    VerifySerializer,
    auth_response,
)
from accounts.signup import SignupRejected, register_student

# Generic message for every failed credential check. Naming which half was
# wrong would let anyone test whether a given PRN has an account.
INVALID_CREDENTIALS = "Those credentials did not match an active account."


class OtpThrottle(ScopedRateThrottle):
    """Per-IP ceiling on OTP endpoints, on top of the per-account limit."""

    scope = "otp"


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _otp_payload(issued: IssuedCode, message: str) -> dict:
    payload = {"detail": message, "expires_at": issued.expires_at}
    # DEBUG-only convenience so the prototype UI can be driven without
    # reading the server console. Never set in a real deployment.
    if settings.PLACEMENT["EXPOSE_OTP_IN_RESPONSE"]:
        payload["debug_otp"] = issued.code
    return payload


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OtpThrottle])
def signup(request):
    """PRN + college email -> roster match -> inactive account + emailed code."""
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        outcome = register_student(**serializer.validated_data)
    except SignupRejected as exc:
        # 403, not 400: the input was well-formed, the *identity* was refused.
        return Response(
            {"detail": exc.message, "reason": exc.reason, "flagged_for_review": True},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        issued = issue_code(
            outcome.user, OneTimeCode.Purpose.SIGNUP, ip=_client_ip(request)
        )
    except OtpRateLimited as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    return Response(
        {
            **_otp_payload(issued, f"Verification code sent to {outcome.user.email}."),
            "prn": outcome.user.prn,
            "email": outcome.user.email,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OtpThrottle])
def verify(request):
    """Confirm the signup code, set a password, activate the account."""
    serializer = VerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = resolve_user(data["identifier"])
    if user is None or user.is_active:
        # Already-active accounts verify nothing; say as little as possible.
        return Response(
            {"detail": "No pending verification for that PRN or email."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        verify_code(user, data["code"], OneTimeCode.Purpose.SIGNUP)
    except OtpError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(data["password"])
    user.save(update_fields=["password"])
    user.mark_verified()

    return Response(auth_response(user), status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """PRN or email plus password. Works for all three roles."""
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = resolve_user(data["identifier"])
    if user is None:
        return Response(
            {"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
        )

    # An unverified account is worth a distinct message: the student has
    # already proved they know the PRN, and a dead end here is a support call.
    if not user.is_active:
        return Response(
            {
                "detail": "This account is not verified yet. "
                "Check your college email for the code.",
                "needs_verification": True,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    authenticated = authenticate(request, username=user.email, password=data["password"])
    if authenticated is None:
        return Response(
            {"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
        )

    return Response(auth_response(authenticated), status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OtpThrottle])
def otp_request(request):
    """Email a login code. Answers the same way whether or not the account exists."""
    serializer = OtpRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    generic = {
        "detail": "If that PRN or email has a verified account, a code is on its way."
    }
    user = resolve_user(serializer.validated_data["identifier"])
    if user is None or not user.is_active:
        return Response(generic, status=status.HTTP_200_OK)

    try:
        issued = issue_code(user, OneTimeCode.Purpose.LOGIN, ip=_client_ip(request))
    except OtpRateLimited as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    return Response(_otp_payload(issued, generic["detail"]), status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OtpThrottle])
def otp_login(request):
    """Exchange a login code for tokens."""
    serializer = OtpLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = resolve_user(data["identifier"])
    if user is None or not user.is_active:
        return Response(
            {"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        verify_code(user, data["code"], OneTimeCode.Purpose.LOGIN)
    except OtpError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(auth_response(user), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


class RefreshView(TokenRefreshView):
    """
    Token rotation with reuse detection.

    Rotation alone is theatre. If a refresh token is stolen, both the thief and
    the legitimate holder can rotate it, and whichever rotates second is simply
    told "already used" -- the other keeps a working session. The spec's rule is
    that reuse of a consumed token revokes the *family*, so the descendants of
    the stolen token die with it and the real holder is forced to log in again.
    That is the intended outcome: a forced re-login is the signal something went
    wrong, and is cheap next to a silent parallel session.

    SimpleJWT blacklists the presented token on rotation but has no concept of
    a family, so the detection and the cascade are here.
    """

    permission_classes = [AllowAny]

    REVOKED = {
        "detail": "This refresh token's family has been revoked after a replay. "
        "Sign in again."
    }

    def post(self, request, *args, **kwargs):
        presented = request.data.get("refresh")
        if presented:
            family, already_consumed = self._inspect(presented)

            # A descendant of a family already killed by a replay.
            if family and RevokedTokenFamily.objects.filter(family=family).exists():
                return Response(self.REVOKED, status=status.HTTP_401_UNAUTHORIZED)

            # The replay itself: kill the family, which takes the descendants
            # the thief or the real holder is still carrying.
            if already_consumed:
                self._revoke_family(family, presented)
                return Response(self.REVOKED, status=status.HTTP_401_UNAUTHORIZED)

        return super().post(request, *args, **kwargs)

    @staticmethod
    def _inspect(raw_token: str) -> tuple[str | None, bool]:
        """`(family, has_already_been_consumed)` for a presented refresh token."""
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            # verify=False: an expired or already-consumed token still has to be
            # readable, because that is precisely the case being detected.
            payload = RefreshToken(raw_token, verify=False).payload
        except Exception:
            return None, False

        jti = payload.get("jti")
        consumed = bool(jti) and BlacklistedToken.objects.filter(token__jti=jti).exists()
        return payload.get("family"), consumed

    @staticmethod
    def _revoke_family(family: str | None, raw_token: str) -> None:
        from rest_framework_simplejwt.tokens import RefreshToken

        if not family:
            return

        user = None
        try:
            user_id = RefreshToken(raw_token, verify=False).payload.get("user_id")
            user = User.objects.filter(pk=user_id).first()
        except Exception:
            pass

        RevokedTokenFamily.objects.get_or_create(
            family=family, defaults={"user": user, "reason": "refresh token reuse"}
        )
        AuditLog.record(
            actor=user,
            action=AuditLog.Action.SESSIONS_REVOKED,
            target=str(getattr(user, "email", family)),
            reason="refresh token reuse",
            family=family,
        )


