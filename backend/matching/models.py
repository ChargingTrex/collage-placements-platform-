"""
The matching engine's own storage.

`StoredVector` backs the local vector store (`matching/vectorstore.py`) on
SQLite dev and CI, and on any deployment without MongoDB. It holds what the
MongoDB collection holds and nothing more: an id, the vector, the model that
made it, and filter metadata -- never resume text or contact details.

`Skill`, `SkillAlias` and `SkillAliasSuggestion` are the skill graph that
`matching/skills.py` reads. `RoleCategory` is the roles recruiters' JDs
describe (`matching/categories.py`).
"""

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StoredVector(models.Model):
    #: The profile's id as a string, the same key the MongoDB store uses.
    doc_id = models.CharField(max_length=64, primary_key=True)
    vector = models.JSONField()
    model = models.CharField(max_length=100, db_index=True)
    dims = models.PositiveIntegerField()
    meta = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["model", "dims"])]

    def __str__(self) -> str:
        return f"{self.doc_id} ({self.model}, {self.dims}d)"


# --- the skill graph -----------------------------------------------------------


def slugify_skill(name: str) -> str:
    """
    A comparison key for a skill name.

    Identical to `profiles.models.slugify_skill` (a test holds them equal):
    `matching` must not import `profiles`, yet a graph slug and a profile
    skill's slug have to be the same key. "+", "#" and a leading dot are
    spelled out so C, C++, C# and .NET stay four skills.
    """
    name = (name or "").strip().lower()
    name = re.sub(r"^\.", "dot", name).replace("+", "plus").replace("#", "sharp")
    return re.sub(r"[^a-z0-9]+", "", name)


class Skill(models.Model):
    """
    One canonical skill, the name every spelling of it resolves to.

    `implies` points from the specific to the general: Django implies Python,
    so a JD asking for Python is met by a resume that says Django. Not the
    reverse, which is why the relation is not symmetrical.
    """

    name = models.CharField(max_length=60, unique=True)
    slug = models.CharField(max_length=60, unique=True, editable=False)
    implies = models.ManyToManyField(
        "self", symmetrical=False, related_name="implied_by", blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.slug = slugify_skill(self.name)
        return super().save(*args, **kwargs)


class SkillAlias(models.Model):
    """Another spelling of a skill: Postgres for PostgreSQL."""

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="aliases")
    name = models.CharField(max_length=60)
    #: Unique: one spelling cannot mean two skills.
    slug = models.CharField(max_length=60, unique=True, editable=False)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "skill aliases"

    def __str__(self) -> str:
        return f"{self.name} → {self.skill.name}"

    def clean(self):
        slug = slugify_skill(self.name)
        if not slug:
            raise ValidationError({"name": "Enter an alias."})
        clash = Skill.objects.filter(slug=slug).exclude(pk=self.skill_id).first()
        if clash:
            raise ValidationError({"name": f"'{self.name}' is already the skill '{clash.name}'."})

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.slug = slugify_skill(self.name)
        return super().save(*args, **kwargs)


class SkillAliasSuggestion(models.Model):
    """
    A spelling the embedder thinks is an existing skill, awaiting an admin.

    Never applied by itself: "Java" and "JavaScript" sit close in embedding
    space, and one wrong merge silently changes every match that uses it.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    alias = models.CharField(max_length=60)
    slug = models.CharField(max_length=60, editable=False, db_index=True)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="alias_suggestions")
    similarity = models.FloatField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-similarity"]
        constraints = [
            models.UniqueConstraint(fields=["slug", "skill"], name="unique_alias_suggestion")
        ]

    def __str__(self) -> str:
        return f"{self.alias} → {self.skill.name}? ({self.status})"

    def save(self, *args, **kwargs):
        self.alias = self.alias.strip()
        self.slug = slugify_skill(self.alias)
        return super().save(*args, **kwargs)

    def approve(self) -> SkillAlias:
        """
        Make the alias real. The only way a suggestion changes the graph.

        Raises ValidationError, leaving the suggestion pending, when the
        spelling already means another skill: one spelling cannot mean two.
        """
        slug = slugify_skill(self.alias)
        alias = SkillAlias.objects.select_related("skill").filter(slug=slug).first()
        owner = alias.skill if alias else Skill.objects.filter(slug=slug).exclude(pk=self.skill_id).first()
        if owner is not None and owner.pk != self.skill_id:
            raise ValidationError(
                f"'{self.alias}' already means '{owner.name}', so it cannot be an alias of '{self.skill.name}'."
            )
        if alias is None:
            alias = SkillAlias.objects.create(skill=self.skill, name=self.alias)
        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_at"])
        return alias

    def reject(self) -> None:
        self.status = self.Status.REJECTED
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_at"])


# --- role categories --------------------------------------------------------------


def normalise_role(name: str | None) -> str:
    """How role names compare: "Backend  ENGINEER" is "backend engineer"."""
    return " ".join((name or "").lower().split())


class RoleCategory(models.Model):
    """
    A role recruiters hire for, learnt from their job descriptions.

    Not a fixed taxonomy: each JD the LLM reads (`categories.
    record_job_description`) joins the category its canonical role names,
    or starts one. `skill_weights` counts how many JDs asked for each
    canonical skill; `centroid` is the mean JD embedding, kept only while
    every vector in it came from `centroid_model`.
    """

    name = models.CharField(max_length=100, unique=True)
    #: Raw titles and role names seen for it, and names it was merged from.
    aliases = models.JSONField(default=list, blank=True)
    #: canonical skill name -> how many of its JDs require it
    skill_weights = models.JSONField(default=dict, blank=True)
    centroid = models.JSONField(null=True, blank=True)
    centroid_model = models.CharField(max_length=100, blank=True)
    #: How many JD vectors the centroid averages. Not `jd_count`: a JD whose
    #: embedding failed still counts as a JD but adds nothing to the mean.
    centroid_count = models.PositiveIntegerField(default=0)
    jd_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-jd_count", "name"]
        verbose_name_plural = "role categories"

    def __str__(self) -> str:
        return self.name

    def spellings(self) -> set[str]:
        """Every name a JD's role may use to join this category."""
        return {normalise_role(self.name), *(normalise_role(a) for a in self.aliases or [])} - {""}

    def add_alias(self, name: str | None) -> None:
        name = " ".join((name or "").split())
        if name and normalise_role(name) not in self.spellings():
            self.aliases = [*(self.aliases or []), name]

    def top_skills(self, n: int = 5) -> list[str]:
        ranked = sorted((self.skill_weights or {}).items(), key=lambda item: (-item[1], item[0].lower()))
        return [name for name, _ in ranked[:n]]

    def add_vector(self, vector: list[float], model: str, count: int = 1) -> None:
        """Fold `count` vectors averaging `vector` into the running mean."""
        if not vector or not model:
            return
        if self.centroid and self.centroid_model == model and len(self.centroid) == len(vector):
            n = self.centroid_count
            self.centroid = [(c * n + v * count) / (n + count) for c, v in zip(self.centroid, vector)]
            self.centroid_count = n + count
        else:
            # Vectors from two models share no space: start the mean over.
            self.centroid, self.centroid_model, self.centroid_count = list(vector), model, count

    def absorb(self, *others: "RoleCategory") -> None:
        """
        Merge `others` into this one. The caller deletes them.

        Centroids from two embedding models share no space, so one model's
        survives: the one averaging the most JD vectors across the whole
        merge (ties: this category's), as the mean of all its centroids.
        Folding them in one at a time instead let whichever came last reset
        the mean, so a one-JD category could discard a four-JD one.
        """
        groups: dict[tuple[str, int], tuple[list[float], int]] = {}
        for category in (self, *others):
            if not (category.centroid and category.centroid_model):
                continue
            key, n = (category.centroid_model, len(category.centroid)), category.centroid_count or 1
            sums, total = groups.get(key, ([0.0] * key[1], 0))
            groups[key] = ([s + c * n for s, c in zip(sums, category.centroid)], total + n)

        for other in others:
            self.jd_count += other.jd_count
            for name in [other.name, *(other.aliases or [])]:
                self.add_alias(name)
            weights = dict(self.skill_weights or {})
            for skill, count in (other.skill_weights or {}).items():
                weights[skill] = weights.get(skill, 0) + count
            self.skill_weights = weights

        if groups:
            own = (self.centroid_model, len(self.centroid)) if self.centroid and self.centroid_model else None
            best = max(groups, key=lambda key: (groups[key][1], key == own))
            sums, total = groups[best]
            self.centroid = [s / total for s in sums]
            self.centroid_model, self.centroid_count = best[0], total
