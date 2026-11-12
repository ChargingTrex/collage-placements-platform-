"""Request/response shapes for the auth endpoints."""

from __future__ import annotations

import uuid

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    """The `me` payload the frontend routes and renders on."""

    is_verified = serializers.SerializerMethodField()
    has_usable_password = serializers.SerializerMethodField()
    # Plural and a list, matching the token. The frontend routes on this, so a
    # singular string here would leave the claim contract with no reader.
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "prn",
            "full_name",
            "display_name",
            "roles",
            "status",
            "is_verified",
            "has_usable_password",
            "date_joined",
        )
        read_only_fields = fields

    def get_roles(self, user: User) -> list[str]:
        from accounts.identity import roles_for

        return roles_for(user)

    def get_is_verified(self, user: User) -> bool:
        return user.email_verified_at is not None

    def get_has_usable_password(self, user: User) -> bool:
        return user.has_usable_password()


def tokens_for(user: User, *, mfa: bool = False) -> dict[str, str]:
    """
    Mint an access/refresh pair carrying the shared spec's §5.4 claim set.

    The claims ride on both tokens so that rendering a page needs no call back
    for basic identity, and so that the refresh that replaces an access token
    produces one carrying the same facts.
    """
    from accounts.identity import build_claims

    refresh = RefreshToken.for_user(user)
    # Every rotation of this token inherits the family id, which is what makes
    # reuse detection able to revoke the descendants of a stolen token rather
    # than only the token presented.
    refresh["family"] = str(uuid.uuid4())
    for claim, value in build_claims(user, mfa=mfa).items():
        # `exp` and `iat` belong to the token machinery, which has already set
        # them correctly for each half of the pair.
        if claim not in {"exp", "iat"}:
            refresh[claim] = value

    access = refresh.access_token
    for claim, value in build_claims(user, mfa=mfa).items():
        if claim not in {"exp", "iat"}:
            access[claim] = value

    return {"access": str(access), "refresh": str(refresh)}


def auth_response(user: User) -> dict:
    return {"user": UserSerializer(user).data, "tokens": tokens_for(user)}


class SignupSerializer(serializers.Serializer):
    prn = serializers.CharField(max_length=32, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)


class VerifySerializer(serializers.Serializer):
    """Confirm the emailed code and choose a password in one step."""

    identifier = serializers.CharField(
        max_length=254, help_text="PRN or email address."
    )
    code = serializers.CharField(max_length=12, trim_whitespace=True)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128)


class OtpRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)


class OtpLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    code = serializers.CharField(max_length=12, trim_whitespace=True)
