"""
Identity for the portal.

One user table, three roles. Students are anchored to their PRN (the college
already controls that number); admins and companies are email-only, exactly
as the PRD specifies. The custom user model lands in the very first migration
on purpose -- swapping AUTH_USER_MODEL later is a migration rewrite.

Login identifier is the email address, because it is the one field every role
has. Students may type either their PRN or their college email at the login
screen; the login endpoint resolves a PRN to its user before authenticating.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.utils import timezone

from core.models import TimeStampedModel


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    ADMIN = "admin", "Placement Cell Admin"
    COMPANY = "company", "Company / Recruiter"


class Status(models.TextChoices):
    """
    The enrolment lifecycle, from the shared identity specification §3.5.

    Separate from `is_placement_eligible`, which is a placement-cell decision
    about one student's participation. This is a registrar fact about their
    enrolment. Both exist and neither implies the other.

    Records outlive accounts: a graduated or withdrawn student keeps every row
    they ever created. Deleting them would silently change participation
    figures for semesters already reported.
    """

    PROVISIONAL = "provisional", "Admitted, not yet enrolled"
    ACTIVE = "active", "Currently enrolled"
    ON_LEAVE = "on_leave", "Temporarily away, still enrolled"
    GRADUATED = "graduated", "Completed the programme"
    WITHDRAWN = "withdrawn", "Left without completing"
    SUSPENDED = "suspended", "Access revoked, enrolment intact"


#: Which statuses may authenticate. Spec §3.5: graduated access is read-only
#: and time-limited, which the portal grants until ID-06 settles the window.
STATUSES_THAT_MAY_LOG_IN = frozenset(
    {Status.ACTIVE, Status.ON_LEAVE, Status.GRADUATED}
)


def issue_human_key(model, field: str, prefix: str, width: int = 4) -> str:
    """
    The next sequential human key for a role: `ADM-0001`, `CMP-0001`.

    Taken under a row lock on the existing maximum, because two accounts
    created at once would otherwise read the same maximum and be issued the
    same identifier -- and these are meant to be unique forever.

    The prefix is the point: an identifier in a log line or an export column
    should say what kind of thing it names without a lookup.
    """
    from django.db.models import Max

    with transaction.atomic():
        highest = (
            model.objects.select_for_update()
            .filter(**{f"{field}__startswith": f"{prefix}-"})
            .aggregate(top=Max(field))["top"]
        )
        nth = int(highest.rsplit("-", 1)[1]) + 1 if highest else 1
        return f"{prefix}-{nth:0{width}d}"


class Company(TimeStampedModel):
    """
    A recruiting organisation, with many recruiter logins belonging to it.

    Previously a company was a `User` row with the organisation's name stuffed
    into `full_name`, a person field. That modelling caused a real bug: a
    shortlist belonged to a recruiter, so two recruiters at one company held
    separate shortlists -- and because "shortlisted only" visibility is computed
    from that table, a student was visible to one and returned 404 for their
    colleague.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The human key. Issued once, never reused, never changed.
    company_id = models.CharField(max_length=16, unique=True, editable=False, blank=True)
    name = models.CharField(max_length=160)
    # Organisation contact -- careers@, not a recruiter's personal address.
    email = models.EmailField(max_length=254, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return f"{self.company_id} {self.name}".strip()

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.company_id:
                self.company_id = issue_human_key(Company, "company_id", "CMP")
        else:
            # Immutable once issued, same rule as admin_id and PRN.
            issued = (
                Company.objects.filter(pk=self.pk)
                .values_list("company_id", flat=True).first()
            )
            if issued:
                self.company_id = issued
        self.email = (self.email or "").lower().strip()
        return super().save(*args, **kwargs)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["password", "last_login"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.STUDENT)
        extra.setdefault("is_active", False)  # inactive until email is verified
        return self._create_user(email, password, **extra)

    def create_admin(self, email: str, password: str, **extra):
        extra.update(role=Role.ADMIN, is_active=True, is_staff=True)
        return self._create_user(email, password, **extra)

    def create_company(self, email: str, password: str, company=None, **extra):
        """
        A recruiter login belonging to a company.

        `company` is the organisation. Passing none leaves the recruiter
        unlinked, which the shortlist endpoint refuses -- deliberately, since a
        shortlist with no company to own it is the bug this modelling fixed.
        """
        extra.update(role=Role.COMPANY, is_active=True, company=company)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra):
        extra.update(
            role=Role.ADMIN, is_active=True, is_staff=True, is_superuser=True
        )
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    # UUID, not a sequence. The shared spec makes user_id the only join key and
    # requires it to be stable forever -- it is the `sub` claim, so it outlives
    # this database. A sequential integer would also leak account volume in
    # every URL.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True, max_length=254)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT)

    # Students only. Unique across the system -- the PRD makes PRN the student
    # identifier, so two accounts can never claim the same one.
    prn = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        help_text="Permanent Registration Number. Students only; null for admin/company.",
    )
    # One field, never split. A large proportion of students here have a
    # single given name, or an initial standing for a father's or place name,
    # and a first/last split rejects them. Validation is length-only for the
    # same reason -- any structural rule turns real names away.
    full_name = models.CharField(max_length=160, blank=True)

    # Human keys, one per role, on the same terms as PRN: issued once, unique,
    # never reused. Students get a PRN from the registrar; these two the portal
    # issues itself.
    admin_id = models.CharField(
        max_length=16, unique=True, null=True, blank=True, editable=False,
        help_text="ADM-0001. Placement cell admins only.",
    )
    # Which organisation a recruiter acts for. Null for students and admins.
    company = models.ForeignKey(
        "accounts.Company", null=True, blank=True, on_delete=models.PROTECT,
        related_name="recruiters",
    )

    # What appears in lists and greetings; the student may set it. Never used
    # on an official document -- that is `full_name`, which changes only
    # through a formal correction.
    display_name_override = models.CharField(max_length=80, blank=True)

    # Registrar fact about enrolment. `is_active` stays because Django's auth
    # backend checks it, but it is now derived -- a user may log in only when
    # their email is verified AND their status permits it.
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )

    # is_active doubles as "email verified": accounts stay inactive, and
    # therefore unable to authenticate, until the OTP is confirmed.
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["email"]
        indexes = [models.Index(fields=["role"])]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # Issued once and never reissued: a human key that changes is not one.
        # Every export and audit line that already named it would become a lie,
        # so an attempt to edit it is ignored rather than honoured.
        if self._state.adding:
            if self.role == Role.ADMIN and not self.admin_id:
                self.admin_id = issue_human_key(User, "admin_id", "ADM")
        else:
            issued = (
                type(self).objects.filter(pk=self.pk)
                .values_list("admin_id", flat=True).first()
            )
            if issued:
                self.admin_id = issued
            elif self.role == Role.ADMIN and not self.admin_id:
                self.admin_id = issue_human_key(User, "admin_id", "ADM")

        # A status that forbids login revokes access immediately, without
        # waiting for a token to expire (spec §5.6).
        if self.status not in STATUSES_THAT_MAY_LOG_IN:
            self.is_active = False

        self.email = self.email.lower().strip()
        # "" and NULL differ under a unique constraint: many blank PRNs would
        # collide, many NULLs do not. Normalise before every write.
        if not self.prn:
            self.prn = None
        else:
            self.prn = self.prn.strip().upper()
        return super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        """What to call them. Falls back through full name to the address."""
        return self.display_name_override or self.full_name or self.email.split("@")[0]

    @property
    def may_log_in(self) -> bool:
        """Verified, and in a status the registrar permits access for."""
        return self.is_active and self.status in STATUSES_THAT_MAY_LOG_IN

    @property
    def is_student(self) -> bool:
        return self.role == Role.STUDENT

    @property
    def is_placement_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_company(self) -> bool:
        return self.role == Role.COMPANY

    def mark_verified(self) -> None:
        """Email ownership confirmed. Status still governs whether they get in."""
        self.email_verified_at = timezone.now()
        self.is_active = self.status in STATUSES_THAT_MAY_LOG_IN
        self.save(update_fields=["is_active", "email_verified_at"])

    def set_status(self, status: str) -> None:
        """
        Change enrolment status, revoking access immediately where it must.

        Suspending or withdrawing a student kills their sessions now rather
        than when the access token happens to expire -- the spec is explicit
        that revocation does not wait (§5.6).
        """
        self.status = status
        self.is_active = (
            self.email_verified_at is not None
            and status in STATUSES_THAT_MAY_LOG_IN
        )
        self.save(update_fields=["status", "is_active"])
        if not self.is_active:
            self.one_time_codes.filter(consumed_at__isnull=True).update(
                consumed_at=timezone.now()
            )


class OneTimeCode(models.Model):
    """
    A short-lived numeric code emailed to a college address.

    Stored hashed, never in plaintext: a leaked database should not hand
    somebody a working login code. Codes are single-use, expire, and lock out
    after a handful of wrong guesses so the 6-digit space cannot be walked.
    """

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Verify a new account"
        LOGIN = "login", "Log in without a password"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="one_time_codes"
    )
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    requested_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "purpose", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_purpose_display()} for {self.user.email}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_locked(self) -> bool:
        from django.conf import settings

        return self.attempts >= settings.PLACEMENT["OTP_MAX_ATTEMPTS"]

    @property
    def is_usable(self) -> bool:
        return not (self.is_expired or self.is_consumed or self.is_locked)

    def consume(self) -> None:
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at"])


class RevokedTokenFamily(models.Model):
    """
    A refresh-token family killed by reuse detection.

    Needed because SimpleJWT registers only the tokens minted by `for_user` as
    outstanding -- a token produced by *rotation* is never recorded, so there is
    nothing to blacklist it through. Recording the family instead of the token
    catches every descendant, including ones issued after the revocation.

    Rows are kept rather than cleaned up on expiry: a family that was revoked
    for reuse is a security event, and the trail is worth more than the bytes.
    """

    family = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="revoked_token_families",
    )
    reason = models.CharField(max_length=120, default="refresh token reuse")
    revoked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revoked_at"]
        verbose_name_plural = "revoked token families"

    def __str__(self) -> str:
        return f"{self.family} revoked ({self.reason})"
