"""
The student profile: the structured resume companies actually filter on.

Shape of the data:

    roster.Student      the college's record -- name, department, batch, CGPA.
                        Read-only here; it is the source of truth.
    StudentProfile      what the student writes: summary, links, skills,
                        experience, projects, resume file, visibility.
    ExperienceEntry     internships, part-time work, volunteering.
    ProjectEntry        with tech stack and links.
    ProfileSkill        tagged and slugged so companies can filter on them.
    CompanyShortlist    which companies may see a "shortlisted only" profile.
    ResumeAnalysis      the LLM/regex reading of the resume, admin-only facts.

Two values the resume parser produces are stored twice on purpose:
`parsed_experience_years` is what the engine read, `experience_years` is what
the student confirmed. The PRD asks for pre-filled fields the student
reviews and corrects, so overwriting the student's correction on the next
upload would be wrong, and losing what the engine said would make the
suggestion unexplainable.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import TimeStampedModel
from core.storage import marksheet_upload_path, transcript_upload_path, upload_path


def slugify_skill(name: str) -> str:
    """
    A comparison key for a skill name.

    "Node.js", "node js" and "NodeJS" are the same skill to a recruiter
    filtering a list, so they must collapse to one token. C, C++ and C# are
    not, so "+" and "#" are spelled out before the rest is stripped, and so
    is a leading dot: ".NET" is "dotnet", not "NET".
    """
    name = (name or "").strip().lower()
    name = re.sub(r"^\.", "dot", name).replace("+", "plus").replace("#", "sharp")
    return re.sub(r"[^a-z0-9]+", "", name)


class Visibility(models.TextChoices):
    ALL = "all", "Visible to all companies"
    SHORTLISTED = "shortlisted", "Visible only to companies that shortlisted me"
    HIDDEN = "hidden", "Hidden from companies"


class EducationLevel(models.TextChoices):
    UG = "UG", "Undergraduate"
    MASTERS = "Masters", "Masters"
    PG = "PG", "PG / Doctorate"


class CareerPath(models.TextChoices):
    PLACEMENT = "placement", "Placement / campus recruitment"
    BUSINESS = "business", "Starting or joining a business"
    HIGHER_STUDIES = "higher_studies", "Higher studies"
    ENTREPRENEURSHIP = "entrepreneurship", "Entrepreneurship"
    RESEARCH = "research", "Research"
    FAMILY_BUSINESS = "family_business", "Family business"
    COMPETITIVE_EXAMS = "competitive_exams", "Competitive exams"
    OTHER = "other", "Other"
    UNDECIDED = "undecided", "Undecided"


class CgpaReview(models.TextChoices):
    NOT_NEEDED = "not_needed", "Not needed"
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class Board(models.TextChoices):
    """Who issued a school marksheet. `OTHER` carries no free-text detail."""

    CBSE = "cbse", "CBSE"
    ICSE = "icse", "ICSE / CISCE"
    STATE = "state", "State board"
    IB = "ib", "International Baccalaureate"
    CAMBRIDGE = "cambridge", "Cambridge / IGCSE"
    OTHER = "other", "Other"


#: The two school levels a student can record, as `<level>` in the URLs.
MARKSHEET_LEVELS = ("10", "12")


class ProfileQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        The profiles `user` is allowed to see.

        This is the visibility rule, and it lives in the queryset so every
        list, detail and search path goes through it -- there is no code path
        that returns a hidden profile and relies on the UI not to show it.
        """
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_placement_admin:
            return self
        if user.is_student:
            return self.filter(user=user)
        if user.is_company:
            # Scoped to the recruiter's COMPANY, so colleagues see one
            # shortlist. A recruiter with no company sees only the profiles
            # open to everyone.
            shortlisted = CompanyShortlist.objects.filter(
                company=user.company_id, profile=models.OuterRef("pk")
            )
            # Parenthesised explicitly: relying on & binding tighter than |
            # is how a visibility rule quietly becomes the wrong one.
            return self.filter(
                models.Q(visibility=Visibility.ALL)
                | (
                    models.Q(visibility=Visibility.SHORTLISTED)
                    & models.Q(models.Exists(shortlisted))
                )
            )
        return self.none()

    def with_related(self):
        return self.select_related("user", "student", "verified_by").prefetch_related(
            "skills", "experience_entries", "projects"
        )

    def with_shortlist_count(self):
        """
        `shortlist_total`: how many companies shortlisted each profile, in
        the page query. A correlated subquery rather than a JOIN + COUNT, so
        a list filter that joins (skills) cannot multiply it.
        """
        counts = (
            CompanyShortlist.objects.filter(profile=models.OuterRef("pk"))
            .order_by()
            .values("profile")
            .annotate(n=models.Count("pk"))
            .values("n")
        )
        return self.annotate(
            shortlist_total=Coalesce(
                models.Subquery(counts, output_field=models.IntegerField()), 0
            )
        )


class StudentProfile(TimeStampedModel):
    """One profile per verified student account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    student = models.OneToOneField(
        "roster.Student", on_delete=models.CASCADE, related_name="profile"
    )

    headline = models.CharField(
        max_length=120, blank=True, help_text="One line, e.g. 'Backend developer'."
    )
    summary = models.TextField(blank=True, max_length=2000)
    phone = models.CharField(max_length=20, blank=True)
    github_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    website_url = models.URLField(blank=True)

    # --- confirmed by the student, pre-filled from their resume ---
    experience_years = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("0.0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("50"))],
    )
    education_level = models.CharField(
        max_length=16, choices=EducationLevel.choices, blank=True
    )

    # --- what the parser read, kept separate from what the student confirmed ---
    resume = models.FileField(upload_to=upload_path, blank=True, null=True)
    resume_filename = models.CharField(max_length=255, blank=True)
    resume_text = models.TextField(blank=True)
    resume_uploaded_at = models.DateTimeField(null=True, blank=True)
    parsed_experience_years = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    parsed_education_levels = models.JSONField(default=list, blank=True)
    #: False until the student has looked at the parsed values.
    parsed_values_confirmed = models.BooleanField(default=False)

    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.ALL
    )

    # --- R2/R4: what the student plans to do, never shown to companies ---
    career_path = models.CharField(
        max_length=24, choices=CareerPath.choices, default=CareerPath.UNDECIDED
    )
    career_path_detail = models.CharField(max_length=200, blank=True)
    also_attending_placements = models.BooleanField(default=False)
    personal_email = models.EmailField(blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    onboarding_dismissed_at = models.DateTimeField(null=True, blank=True)

    # --- R5: the transcript and what was read from it ---
    transcript = models.FileField(upload_to=transcript_upload_path, blank=True, null=True)
    transcript_filename = models.CharField(max_length=255, blank=True)
    transcript_text = models.TextField(blank=True)
    transcript_uploaded_at = models.DateTimeField(null=True, blank=True)
    transcript_prn = models.CharField(max_length=32, blank=True)
    transcript_school = models.CharField(max_length=150, blank=True)
    transcript_degree = models.CharField(max_length=40, blank=True)
    # Three CGPAs kept apart on purpose: the printed one, our recomputation,
    # and what the student confirmed. None of them is the roster's Student.cgpa.
    parsed_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    recomputed_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    confirmed_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    cgpa_matches_roster = models.BooleanField(null=True, blank=True)
    cgpa_review_status = models.CharField(
        max_length=16, choices=CgpaReview.choices, default=CgpaReview.NOT_NEEDED
    )

    # --- School marksheets: 10th and 12th, each a file plus what it says ---
    # Two fixed levels, so explicit fields rather than a child model: it is how
    # every other document on this profile is stored, and `audited_document`
    # resolves a field name plus its `<field>_filename` sibling, which this
    # shape gives it for free.
    #
    # Unlike the transcript, nothing here is parsed. The marks are the
    # student's own statement, which is why they are writable on the profile
    # while the files are not.
    marksheet_10 = models.FileField(upload_to=marksheet_upload_path, blank=True, null=True)
    marksheet_10_filename = models.CharField(max_length=255, blank=True)
    marksheet_10_uploaded_at = models.DateTimeField(null=True, blank=True)
    marks_10_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    marks_10_board = models.CharField(max_length=16, choices=Board.choices, blank=True)
    marks_10_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1950), MaxValueValidator(2100)],
    )

    marksheet_12 = models.FileField(upload_to=marksheet_upload_path, blank=True, null=True)
    marksheet_12_filename = models.CharField(max_length=255, blank=True)
    marksheet_12_uploaded_at = models.DateTimeField(null=True, blank=True)
    marks_12_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    marks_12_board = models.CharField(max_length=16, choices=Board.choices, blank=True)
    marks_12_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1950), MaxValueValidator(2100)],
    )

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_profiles",
    )

    objects = ProfileQuerySet.as_manager()

    class Meta:
        ordering = ["student__prn"]
        indexes = [
            models.Index(fields=["visibility"]),
            models.Index(fields=["is_verified"]),
        ]

    def __str__(self) -> str:
        return f"Profile of {self.student.prn}"

    # --- derived -----------------------------------------------------------

    @property
    def prn(self) -> str:
        return self.student.prn

    @property
    def onboarding_completed(self) -> bool:
        return self.onboarding_completed_at is not None

    @property
    def has_resume(self) -> bool:
        return bool(self.resume)

    @property
    def parsed_differs_from_confirmed(self) -> bool:
        """Whether the engine's reading still disagrees with the student's."""
        if self.parsed_experience_years is None:
            return False
        return Decimal(self.parsed_experience_years) != Decimal(self.experience_years)

    #: What counts towards "profile completion rate" in the PRD's metrics.
    COMPLETION_CHECKS = (
        ("headline", "A one-line headline"),
        ("summary", "A summary"),
        ("skills", "At least three skills"),
        ("experience", "At least one experience entry"),
        ("projects", "At least one project"),
        ("resume", "A resume upload"),
        ("links", "At least one link (GitHub, LinkedIn or website)"),
        ("career_path", "A career path"),
    )

    def completion_detail(self) -> dict[str, bool]:
        return {
            "headline": bool(self.headline.strip()),
            "summary": bool(self.summary.strip()),
            "skills": self.skills.count() >= 3,
            "experience": self.experience_entries.exists(),
            "projects": self.projects.exists(),
            "resume": self.has_resume,
            "links": any([self.github_url, self.linkedin_url, self.website_url]),
            "career_path": self.career_path != CareerPath.UNDECIDED,
        }

    @property
    def completion_percent(self) -> int:
        detail = self.completion_detail()
        return round(100 * sum(detail.values()) / len(detail))

    @property
    def company_completion_percent(self) -> int:
        """
        Completion as companies see it: the same items minus career_path.

        Companies never see a student's career path (DECISIONS D24). If the
        company figure counted it, the number would rise when a path is
        chosen, which tells a company something they are not meant to know.
        """
        detail = self.completion_detail()
        detail.pop("career_path", None)
        return round(100 * sum(detail.values()) / len(detail))

    # --- state changes -------------------------------------------------------

    def apply_parsed_resume(self, extracted) -> dict:
        """
        Record what the engine read and pre-fill the student's fields.

        Pre-fill, not overwrite: once the student has confirmed a value, a
        later upload records the new reading and flags the disagreement
        rather than silently replacing their correction.
        """
        from matching.extractors import highest_education_level

        self.resume_text = extracted.raw_text
        self.parsed_experience_years = Decimal(str(extracted.experience_years))
        self.parsed_education_levels = sorted(extracted.education_levels)
        self.resume_uploaded_at = timezone.now()

        suggestion = {
            "experience_years": extracted.experience_years,
            "education_level": highest_education_level(extracted.education_levels),
            "applied": False,
        }

        if not self.parsed_values_confirmed:
            self.experience_years = self.parsed_experience_years
            if suggestion["education_level"]:
                self.education_level = suggestion["education_level"]
            suggestion["applied"] = True

        return suggestion

    def apply_analysed_experience(self, years: float) -> bool:
        """
        Record the model's date-derived total, pre-filling as an upload does.

        The same pre-fill-not-overwrite rule as `apply_parsed_resume`: a
        value the student confirmed stays. Returns whether it was applied.
        """
        self.parsed_experience_years = Decimal(str(years))
        if self.parsed_values_confirmed:
            return False
        self.experience_years = self.parsed_experience_years
        return True

    def mark_verified(self, by_user) -> None:
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_by = by_user
        self.save(update_fields=["is_verified", "verified_at", "verified_by", "updated_at"])

    def revoke_verification(self) -> None:
        self.is_verified = False
        self.verified_at = None
        self.verified_by = None
        self.save(update_fields=["is_verified", "verified_at", "verified_by", "updated_at"])


class ProfileSkill(TimeStampedModel):
    """One tagged skill. Slugged so filtering is not defeated by spelling."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Category(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        TOOL = "tool", "Tool / platform"
        SOFT = "soft", "Soft skill"

    profile = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="skills"
    )
    name = models.CharField(max_length=60)
    slug = models.CharField(max_length=60, editable=False, db_index=True)
    category = models.CharField(
        max_length=16, choices=Category.choices, default=Category.TECHNICAL
    )

    class Meta:
        ordering = ["category", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "slug"], name="unique_skill_per_profile"
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.slug = slugify_skill(self.name)
        return super().save(*args, **kwargs)


class ExperienceEntry(TimeStampedModel):
    """An internship, part-time job or volunteering stint."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Kind(models.TextChoices):
        INTERNSHIP = "internship", "Internship"
        PART_TIME = "part_time", "Part-time"
        FULL_TIME = "full_time", "Full-time"
        VOLUNTEER = "volunteer", "Volunteering"
        FREELANCE = "freelance", "Freelance"

    profile = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="experience_entries"
    )
    role = models.CharField(max_length=120)
    organization = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INTERNSHIP)
    start_date = models.DateField()
    #: Null means "still there".
    end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True, max_length=2000)
    skills_used = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.role} at {self.organization}"

    @property
    def is_current(self) -> bool:
        return self.end_date is None

    @property
    def duration_months(self) -> int:
        end = self.end_date or timezone.localdate()
        return max(
            0,
            (end.year - self.start_date.year) * 12 + (end.month - self.start_date.month),
        )

    def searchable_text(self) -> str:
        return " ".join(
            filter(None, [self.role, self.organization, self.description, *self.skills_used])
        )


class ProjectEntry(TimeStampedModel):
    """A project, with the tech stack and links a recruiter will click."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    profile = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="projects"
    )
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, max_length=2000)
    tech_stack = models.JSONField(default=list, blank=True)
    role = models.CharField(max_length=120, blank=True)
    team_size = models.PositiveSmallIntegerField(null=True, blank=True)
    repo_url = models.URLField(blank=True)
    demo_url = models.URLField(blank=True)
    video_url = models.URLField(blank=True)
    started_on = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-completed_on", "-started_on", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def searchable_text(self) -> str:
        return " ".join(
            filter(None, [self.title, self.description, self.role, *self.tech_stack])
        )


class ResumeAnalysis(TimeStampedModel):
    """
    The full reading of a profile's resume: regex always, the LLM when on.

    Created pending by the upload, finished by `POST me/resume/analyze` or
    `manage.py analyze_resumes`. `facts` and `regex_facts` hold what the
    resume says about age, DOB, CGPA and contacts: admin-only, never in a
    student or company payload (`profiles/analysis.py` builds those).

    The vector itself lives in the vector store, keyed by the student's
    uuid; only the model that made it is recorded here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (no readable text)"

    class Source(models.TextChoices):
        LLM = "llm", "LLM"
        REGEX = "regex", "Regex"

    profile = models.OneToOneField(
        StudentProfile, on_delete=models.CASCADE, related_name="analysis"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=8, choices=Source.choices, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    #: The model's validated reading, or None when regex alone was used.
    facts = models.JSONField(null=True, blank=True)
    regex_facts = models.JSONField(default=dict, blank=True)
    agreement = models.JSONField(default=dict, blank=True)
    #: sha256 of the resume *text*, the input the reading depends on.
    resume_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    #: Role categories, best first. Task 7 fills these in.
    categories = models.JSONField(default=list, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    #: The form changed since the vector was written; `reindex_vectors --dirty-only`.
    needs_reindex = models.BooleanField(default=False, db_index=True)
    analysed_at = models.DateTimeField(null=True, blank=True)
    #: Why the LLM's reading was not used. Set means a retry may do better.
    error = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "resume analyses"

    def __str__(self) -> str:
        return f"Analysis of {self.profile.prn} ({self.status})"

    @property
    def experience_years(self) -> float | None:
        """The engine's precedence: the model's date total when it found one."""
        if self.status != self.Status.DONE:
            return None
        if self.facts and self.facts.get("experience_months", 0) > 0:
            return self.facts["experience_years"]
        return self.regex_facts.get("experience_years")

    @property
    def education_level(self) -> str | None:
        from matching.extractors import highest_education_level

        if self.status != self.Status.DONE:
            return None
        levels = (self.facts or {}).get("education_levels") or self.regex_facts.get("education_levels") or []
        return highest_education_level(set(levels))


class CompanyShortlist(TimeStampedModel):
    """
    A company's interest in one student.

    Needed here rather than in Phase 4 because "visible only to companies
    that shortlisted me" is a Phase 3 visibility setting, and without a
    shortlist that setting is untestable. Phase 4's applications build on it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The COMPANY, not the recruiter who clicked. A shortlist held per
    # recruiter means two colleagues at one company see different students,
    # and "shortlisted only" visibility silently disagrees with itself.
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="shortlisted_profiles"
    )
    profile = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="shortlisted_by"
    )
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "profile"], name="unique_shortlist_entry"
            )
        ]

    def __str__(self) -> str:
        return f"{self.company.name} shortlisted {self.profile.prn}"
