"""
Role categories, derived from recruiters' job descriptions (plan Task 7).

Categories reflect what recruiters actually hire for, so they come only
from JDs, never from a fixed taxonomy:

- `record_job_description` folds one JD the LLM has read into the category
  its canonical role names, or starts one. Without the LLM there is no
  canonical role and nothing is recorded: no JDs, no categories, and the
  UI says so rather than inventing them (cold start).
- `categorise_profile` gives a profile its best-fitting categories by
  blending the centroid cosine (calibrated like the match score's semantic
  part) with skill overlap weighted by how often JDs ask for each skill.

Settings: `CATEGORY` (MERGE_THRESHOLD, MIN_FIT, MAX_PER_PROFILE,
CENTROID_WEIGHT).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from django.conf import settings
from django.db import transaction

from matching.embeddings import cosine

#: A role name as stored. Shorter than the name column (100), so a variant's
#: " (n)" suffix always fits.
MAX_ROLE_CHARS = 80
_TAG = re.compile(r"<[^>]{0,200}>")


def clean_role(name: str | None) -> str:
    """
    A recruiter-chosen role or title, made safe to show students as a
    category name: no markup, no control or invisible characters, single
    spaces, at most MAX_ROLE_CHARS. React and the admin escape it anyway;
    this keeps the stored name readable and the variant suffix in bounds.
    """
    text = _TAG.sub(" ", name or "").replace("<", " ").replace(">", " ")
    kept = []
    for ch in text:
        kind = unicodedata.category(ch)
        if kind == "Cf":
            continue  # zero-width and direction marks: drop, do not split a word
        kept.append(" " if kind.startswith("C") else ch)
    return " ".join("".join(kept).split())[:MAX_ROLE_CHARS].strip()


def _comparable(category, vector, model) -> bool:
    return bool(
        vector is not None
        and category.centroid
        and len(category.centroid) == len(vector)
        and (model is None or category.centroid_model == model)
    )


def _unique_name(role: str) -> str:
    from matching.models import RoleCategory

    name, n = role, 2
    while RoleCategory.objects.filter(name__iexact=name).exists():
        name, n = f"{role} ({n})", n + 1
    return name


def record_job_description(job_facts, jd_vector: list[float] | None = None, *, model: str | None = None):
    """
    Fold one JD into its category. Returns the category, or None.

    The JD joins a category whose name or aliases spell its canonical role
    or title (case and spacing ignored). When both the JD and a candidate
    have vectors from the same model, it joins only at a centroid cosine of
    at least `CATEGORY["MERGE_THRESHOLD"]`; a same-titled JD further away
    than that starts a variant ("Backend Engineer (2)") for an admin to
    merge or rename. Required skills are counted by canonical name.
    """
    from matching import skills
    from matching.models import RoleCategory, normalise_role

    role = clean_role(job_facts.canonical_role if job_facts else "")
    if not role:
        return None
    title = clean_role(job_facts.title)
    spelled = {normalise_role(role), normalise_role(title)} - {""}
    threshold = settings.CATEGORY["MERGE_THRESHOLD"]

    with transaction.atomic():
        candidates = [c for c in RoleCategory.objects.select_for_update() if c.spellings() & spelled]
        chosen = None
        close = [
            (cosine(c.centroid, jd_vector), c) for c in candidates if _comparable(c, jd_vector, model)
        ]
        close = [pair for pair in close if pair[0] >= threshold]
        if close:
            chosen = max(close, key=lambda pair: pair[0])[1]
        else:
            # Without two comparable vectors, the name alone decides.
            chosen = next((c for c in candidates if not _comparable(c, jd_vector, model)), None)
        if chosen is None:
            chosen = RoleCategory(name=_unique_name(role))

        chosen.jd_count += 1
        chosen.add_alias(role)
        chosen.add_alias(title)
        weights = dict(chosen.skill_weights or {})
        counted: set[str] = set()
        for name in job_facts.required_skills:
            slug, canonical = skills.canonical_slug(name), skills.canonical(name)
            if slug and slug not in counted:
                counted.add(slug)
                weights[canonical] = weights.get(canonical, 0) + 1
        chosen.skill_weights = weights
        if jd_vector is not None and model:
            chosen.add_vector(list(jd_vector), model)
        chosen.save()
    return chosen


def _skill_fit(category, held: set[str]) -> float | None:
    from matching.skills import canonical_slug

    weights: dict[str, int] = {}
    for name, count in (category.skill_weights or {}).items():
        slug = canonical_slug(name)
        if slug:
            weights[slug] = weights.get(slug, 0) + count
    total = sum(weights.values())
    if not total:
        return None
    return sum(count for slug, count in weights.items() if slug in held) / total


def categorise_profile(
    vector: list[float] | None, skills: Iterable[str], *, model: str | None = None
) -> list[str]:
    """
    The profile's best-fitting categories, best first; [] when none exist.

    Fit blends the calibrated centroid cosine (only for a vector from the
    centroid's own model) with the share of the category's JD skill demand
    the profile covers, through aliases and implications. Below
    `CATEGORY["MIN_FIT"]` a category is not given, so a weak fit is no
    category rather than a misleading one.
    """
    from matching.engine import calibrate_semantic
    from matching.models import RoleCategory
    from matching.skills import expand_slugs

    config = settings.CATEGORY
    held = expand_slugs(skills)
    fits = []
    for category in RoleCategory.objects.all():
        skill_fit = _skill_fit(category, held)
        centroid_fit = (
            calibrate_semantic(cosine(vector, category.centroid), "embedding")
            if _comparable(category, vector, model)
            else None
        )
        if skill_fit is None and centroid_fit is None:
            continue
        if skill_fit is None:
            fit = centroid_fit
        elif centroid_fit is None:
            fit = skill_fit
        else:
            weight = config["CENTROID_WEIGHT"]
            fit = weight * centroid_fit + (1 - weight) * skill_fit
        if fit >= config["MIN_FIT"]:
            fits.append((fit, category.name))
    fits.sort(key=lambda pair: (-pair[0], pair[1]))
    return [name for _, name in fits[: config["MAX_PER_PROFILE"]]]


def canonical_category_names(names: Iterable[str]) -> list[str]:
    """
    The stored spelling of each category name, in order; an unknown name is
    returned as typed, so it matches nobody.

    A name or an alias matches, ignoring case and spacing, so a merged-away
    name still finds its category. One query for the lot: the categories
    are few, and a lookup per value let a long filter list cost one query
    each.
    """
    from matching.models import RoleCategory, normalise_role

    names = list(names)
    if not names:
        return []
    rows = list(RoleCategory.objects.order_by("-jd_count", "name").values_list("name", "aliases"))
    spelled: dict[str, str] = {}
    for name, aliases in rows:
        for alias in aliases or []:
            spelled.setdefault(normalise_role(alias), name)
    # A category's own name beats another category's alias.
    spelled.update((normalise_role(name), name) for name, _ in rows)
    return [spelled.get(normalise_role(str(name)), name) for name in names]
