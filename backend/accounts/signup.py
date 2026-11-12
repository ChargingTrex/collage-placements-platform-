"""
Student signup: roster matching, and what happens when it fails.

The PRD is specific here -- a PRN/email pair that does not match the roster
must not create an account, and must be flagged for admin review. So this
module answers one question, "may this pair become an account?", and records
the answer either way.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from accounts.models import Role, User
from core.models import AuditLog
from roster.models import FlaggedSignup, Student, normalise_email, normalise_prn


class SignupRejected(Exception):
    """Signup refused. `reason` is the FlaggedSignup.Reason that was recorded."""

    def __init__(self, message: str, reason: str, flagged: FlaggedSignup | None = None):
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.flagged = flagged


@dataclass
class SignupOutcome:
    user: User
    student: Student
    created: bool


def _reject(prn: str, email: str, reason: str, message: str) -> SignupRejected:
    flagged = FlaggedSignup.record(prn=prn, email=email, reason=reason)
    AuditLog.record(
        action=AuditLog.Action.SIGNUP_FLAGGED,
        target=f"{normalise_prn(prn)} / {normalise_email(email)}",
        reason=reason,
        attempts=flagged.attempts,
    )
    return SignupRejected(message, reason, flagged)


def match_or_flag(prn: str, email: str) -> Student:
    """
    Resolve a PRN/email pair against the roster.

    Raises SignupRejected -- having recorded a flag -- for every failure the
    PRD calls out, with a message the student can act on.
    """
    prn = normalise_prn(prn)
    email = normalise_email(email)

    allowed_domains = settings.PLACEMENT["ALLOWED_STUDENT_EMAIL_DOMAINS"]
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if allowed_domains and domain not in allowed_domains:
        raise _reject(
            prn,
            email,
            FlaggedSignup.Reason.DOMAIN_NOT_ALLOWED,
            "Use your college email address ("
            + ", ".join(f"@{d}" for d in allowed_domains)
            + ").",
        )

    student = Student.match(prn, email)
    if student is None:
        # Distinguish the three near-misses: a student who mistyped one field
        # should be told which one, and an admin reading the flag queue needs
        # to see the difference between a typo and an unknown PRN.
        by_prn = Student.objects.filter(prn=prn).first()
        by_email = Student.objects.filter(email=email).first()

        if by_prn is not None:
            raise _reject(
                prn,
                email,
                FlaggedSignup.Reason.EMAIL_MISMATCH,
                "That PRN is on the roster under a different email address. "
                "Check the address, or contact the placement cell.",
            )
        if by_email is not None:
            raise _reject(
                prn,
                email,
                FlaggedSignup.Reason.PRN_MISMATCH,
                "That email is on the roster under a different PRN. "
                "Check your PRN, or contact the placement cell.",
            )
        raise _reject(
            prn,
            email,
            FlaggedSignup.Reason.NO_SUCH_PRN,
            "No roster entry matches that PRN and email. "
            "Contact the placement cell to be added.",
        )

    if not student.is_placement_eligible:
        raise _reject(
            prn,
            email,
            FlaggedSignup.Reason.NOT_ELIGIBLE,
            "Your roster entry is not marked placement-eligible. "
            "Contact the placement cell.",
        )

    return student


def register_student(prn: str, email: str) -> SignupOutcome:
    """
    Create (or return) the inactive account behind a matched roster row.

    Deliberately not wrapped in a transaction: a rejection here writes a
    FlaggedSignup and an audit entry *and then raises*, and an enclosing
    atomic block would roll both away -- losing exactly the record the PRD
    asks us to keep. Each step below is a single write, so there is no
    partial state to protect against.

    Returning the existing account for an unverified retry is deliberate: a
    student who closed the tab before entering the code must be able to start
    again without being told the account already exists.
    """
    student = match_or_flag(prn, email)

    existing = User.objects.filter(prn=student.prn).first()
    if existing is not None:
        if existing.is_active:
            raise _reject(
                student.prn,
                student.email,
                FlaggedSignup.Reason.ALREADY_REGISTERED,
                "An account already exists for this PRN. Log in instead, "
                "or use 'forgot password'.",
            )
        # Unverified: let them retry, and pick up a corrected roster email.
        if existing.email != student.email:
            existing.email = student.email
            existing.save(update_fields=["email"])
        return SignupOutcome(user=existing, student=student, created=False)

    user = User.objects.create_user(
        email=student.email,
        password=None,  # set when the code is verified
        role=Role.STUDENT,
        prn=student.prn,
        full_name=student.full_name,
    )
    return SignupOutcome(user=user, student=student, created=True)
