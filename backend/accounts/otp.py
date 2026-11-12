"""
One-time code issue and verification.

Kept apart from the views so signup, login-by-OTP and any later re-send flow
all go through the same rate limit, the same hashing, and the same
single-use rules.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from accounts.models import OneTimeCode, User


class OtpError(Exception):
    """Raised with a message safe to show the user."""


class OtpRateLimited(OtpError):
    pass


def _hash(code: str) -> str:
    """HMAC with SECRET_KEY: a stolen table of hashes is not a rainbow table."""
    return hmac.new(
        settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def _generate(length: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


@dataclass
class IssuedCode:
    code: str
    record: OneTimeCode

    @property
    def expires_at(self):
        return self.record.expires_at


def _enforce_rate_limit(user: User, purpose: str) -> None:
    window_start = timezone.now() - timezone.timedelta(
        minutes=settings.PLACEMENT["OTP_RATE_WINDOW_MINUTES"]
    )
    recent = OneTimeCode.objects.filter(
        user=user, purpose=purpose, created_at__gte=window_start
    ).count()
    if recent >= settings.PLACEMENT["OTP_REQUESTS_PER_WINDOW"]:
        minutes = settings.PLACEMENT["OTP_RATE_WINDOW_MINUTES"]
        raise OtpRateLimited(
            f"Too many codes requested. Try again in {minutes} minutes, "
            f"or contact the placement cell."
        )


def issue_code(
    user: User, purpose: str, *, ip: str | None = None, send_email: bool = True
) -> IssuedCode:
    """Invalidate any outstanding code for this purpose, then issue a fresh one."""
    _enforce_rate_limit(user, purpose)

    # One live code at a time: an old code left usable is an extra way in.
    OneTimeCode.objects.filter(
        user=user, purpose=purpose, consumed_at__isnull=True
    ).update(consumed_at=timezone.now())

    code = _generate(settings.PLACEMENT["OTP_LENGTH"])
    record = OneTimeCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash=_hash(code),
        expires_at=timezone.now()
        + timezone.timedelta(minutes=settings.PLACEMENT["OTP_TTL_MINUTES"]),
        requested_ip=ip,
    )

    if send_email:
        _send(user, code, purpose)

    return IssuedCode(code=code, record=record)


def _send(user: User, code: str, purpose: str) -> None:
    minutes = settings.PLACEMENT["OTP_TTL_MINUTES"]
    subject = (
        "Verify your Placement Cell Portal account"
        if purpose == OneTimeCode.Purpose.SIGNUP
        else "Your Placement Cell Portal login code"
    )
    body = (
        f"Hello{' ' + user.full_name if user.full_name else ''},\n\n"
        f"Your verification code is {code}.\n"
        f"It expires in {minutes} minutes and can be used once.\n\n"
        f"If you did not request this, tell the placement cell — somebody may "
        f"be trying to use your PRN.\n"
    )
    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def verify_code(user: User, code: str, purpose: str) -> OneTimeCode:
    """
    Check a submitted code and consume it.

    Wrong guesses are counted against the live code rather than ignored, so
    a brute-force run burns the code instead of eventually finding it.
    """
    record = (
        OneTimeCode.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if record is None:
        raise OtpError("No code is waiting. Request a new one.")
    if record.is_expired:
        raise OtpError("That code has expired. Request a new one.")
    if record.is_locked:
        raise OtpError("Too many wrong attempts. Request a new code.")

    if not hmac.compare_digest(record.code_hash, _hash((code or "").strip())):
        record.attempts += 1
        record.save(update_fields=["attempts"])
        remaining = settings.PLACEMENT["OTP_MAX_ATTEMPTS"] - record.attempts
        if remaining <= 0:
            raise OtpError("Too many wrong attempts. Request a new code.")
        raise OtpError(f"Incorrect code. {remaining} attempt(s) left.")

    record.consume()
    return record


def resolve_user(identifier: str) -> User | None:
    """
    Find a user by either half of a student's identity.

    Students are told their PRN is their identifier, but they will type their
    email as often as not; admins and companies only ever have an email.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    return User.objects.filter(
        Q(email__iexact=identifier) | Q(prn__iexact=identifier)
    ).first()
