"""
Skill matching through aliases and implications.

A JD asking for "PostgreSQL" must match a resume that says "Postgres", and
one asking for "Python" must match a Django developer. Every skill
comparison in the portal (match scores, categories, form suggestions) goes
through here rather than comparing raw names.

The graph lives in Postgres (`matching.models.Skill`) and is read once per
process into a cache: skill comparisons happen per candidate per JD, and a
query each time would dominate a bulk screen. Saving or deleting a skill or
alias drops the cache in that process (`matching/signals.py`); other
processes pick the change up within `GRAPH_TTL_SECONDS`.

With an empty table everything still works: a name is its own canonical
form, compared by slug, so "Node.js" still meets "node js".
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.conf import settings

from matching import llm
from matching.embeddings import cosine
from matching.models import slugify_skill

logger = logging.getLogger(__name__)

__all__ = [
    "canonical",
    "canonical_slug",
    "expand",
    "expand_slugs",
    "find_in_text",
    "skill_overlap",
    "suggest_aliases",
    "reset_skill_graph",
]

#: How stale another worker's copy of the graph may get after an admin edit.
GRAPH_TTL_SECONDS = 300


@dataclass(frozen=True)
class SkillGraph:
    #: canonical slug -> display name
    names: dict[str, str] = field(default_factory=dict)
    #: any known slug (alias or canonical) -> canonical slug
    resolve: dict[str, str] = field(default_factory=dict)
    #: canonical slug -> canonical slugs it directly implies
    implies: dict[str, frozenset[str]] = field(default_factory=dict)


_lock = threading.Lock()
_graph: SkillGraph | None = None
_loaded_at = 0.0


def _load() -> SkillGraph:
    from matching.models import Skill, SkillAlias

    names, resolve, implies = {}, {}, {}
    for skill in Skill.objects.prefetch_related("implies"):
        names[skill.slug] = skill.name
        resolve[skill.slug] = skill.slug
        implies[skill.slug] = frozenset(target.slug for target in skill.implies.all())
    for alias_slug, skill_slug in SkillAlias.objects.values_list("slug", "skill__slug"):
        # A canonical name always wins over an alias spelled the same way.
        resolve.setdefault(alias_slug, skill_slug)
    return SkillGraph(names=names, resolve=resolve, implies=implies)


def get_graph() -> SkillGraph:
    global _graph, _loaded_at
    with _lock:
        if _graph is None or time.monotonic() - _loaded_at > GRAPH_TTL_SECONDS:
            _graph = _load()
            _loaded_at = time.monotonic()
        return _graph


def reset_skill_graph() -> None:
    """Drop the cached graph. Called by signals, and by tests."""
    global _graph
    with _lock:
        _graph = None


# --- comparisons -----------------------------------------------------------------


def canonical_slug(name: str) -> str:
    """The comparison key of the skill `name` names: an alias's skill, or its own slug."""
    slug = slugify_skill(name)
    return get_graph().resolve.get(slug, slug) if slug else ""


def canonical(name: str) -> str:
    """The canonical spelling: "Postgres" -> "PostgreSQL". Unknown names as written."""
    slug = canonical_slug(name)
    if not slug:
        return ""
    return get_graph().names.get(slug) or (name or "").strip()


def expand_slugs(skills: Iterable[str]) -> set[str]:
    """Canonical slugs of `skills` and everything they imply, transitively."""
    graph = get_graph()
    seen: set[str] = set()
    stack = [slug for slug in (canonical_slug(name) for name in skills) if slug]
    while stack:
        slug = stack.pop()
        if slug in seen:
            continue  # cycle-safe: each skill is visited once
        seen.add(slug)
        stack.extend(graph.implies.get(slug, ()))
    return seen


def expand(skills: Iterable[str]) -> set[str]:
    """Canonical names of `skills` plus everything they imply."""
    skills = list(skills)
    graph = get_graph()
    as_written = {canonical_slug(name): (name or "").strip() for name in reversed(skills)}
    return {graph.names.get(slug) or as_written.get(slug, slug) for slug in expand_slugs(skills)}


def skill_overlap(required: Iterable[str], held: Iterable[str]) -> tuple[list[str], list[str]]:
    """
    (matched, missing): which required skills `held` covers.

    Through aliases and implications, in one direction only: holding Django
    meets a Python requirement, holding Python does not meet a Django one.
    Both lists hold canonical names, in the order required, each once.
    """
    covered = expand_slugs(held)
    matched: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for name in required:
        slug = canonical_slug(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        (matched if slug in covered else missing).append(canonical(name))
    return matched, missing


# --- skills named in free text ------------------------------------------------------

#: A token: "Node.js", "C++", "C#", ".NET", "k8s". A trailing full stop is
#: the sentence's; a leading one may be the skill's (see `find_in_text`).
_TOKEN = re.compile(r"\.?[A-Za-z0-9][A-Za-z0-9+#.]*")
#: What may sit between the words of one skill name: "node js", "scikit-learn".
_JOINER = re.compile(r"[ \t]{1,3}|-")
#: The longest skill name, in words ("Google Cloud Platform").
_MAX_WORDS = 4
#: Skill names that are also ordinary English words. In running text they
#: count only with a capital: "Go" and "React" are skills, "go" and "react"
#: are what a JD asks you to do. A lone "c" is far more often a list
#: marker ("c) Git") than the language.
_COMMON_WORDS = frozenset({"go", "express", "node", "react", "angular", "spring", "flask", "next", "c"})


def _tokens(text: str) -> list[tuple[str, int, int]]:
    tokens = []
    for match in _TOKEN.finditer(text or ""):
        word = match.group().rstrip(".")
        if word:
            tokens.append((word, match.start(), match.start() + len(word)))
    return tokens


def find_in_text(text: str) -> list[str]:
    """
    Known skills named in `text`, by canonical name, in order of appearance.

    This is how a JD's requirements are read when the LLM is off: every
    canonical name and alias in the graph, matched on whole words (and runs
    of up to four words, longest first, so "Django REST Framework" is one
    skill, not Django plus noise). Spellings are compared by slug, so
    "Postgres", "node js" and "NodeJS" resolve like a typed skill would.
    Only skills the graph knows are found; with an empty graph, none.
    """
    graph = get_graph()
    if not graph.resolve:
        return []
    tokens = _tokens(text)
    found: list[str] = []
    seen: set[str] = set()
    i = 0
    while i < len(tokens):
        for width in range(min(_MAX_WORDS, len(tokens) - i), 0, -1):
            run = tokens[i : i + width]
            if any(not _JOINER.fullmatch(text[a[2] : b[1]]) for a, b in zip(run, run[1:])):
                continue
            spelled = text[run[0][1] : run[-1][2]]
            slug = graph.resolve.get(slugify_skill(spelled))
            if slug is None and spelled.startswith("."):
                # ".NET" is a skill; "...React" is React after an ellipsis.
                spelled = spelled[1:]
                slug = graph.resolve.get(slugify_skill(spelled))
            if slug is None:
                continue
            if width == 1 and slugify_skill(spelled) in _COMMON_WORDS and spelled.islower():
                continue
            if slug not in seen:
                seen.add(slug)
                found.append(graph.names.get(slug, spelled))
            i += width
            break
        else:
            i += 1
    return found


# --- alias suggestions -------------------------------------------------------------


def suggest_aliases(unknown_names: Iterable[str], embedder, threshold: float | None = None) -> list:
    """
    For each unknown name, the nearest canonical skill by embedding cosine.

    At or above `threshold` (default `SKILL_GRAPH["ALIAS_SUGGESTION_THRESHOLD"]`)
    a *pending* `SkillAliasSuggestion` is created for an admin. Nothing is
    merged here, ever. A name already known, or already suggested (even if
    rejected), is skipped, so a rejection sticks. Returns the new suggestions.
    """
    from matching.models import Skill, SkillAliasSuggestion

    if threshold is None:
        threshold = settings.SKILL_GRAPH["ALIAS_SUGGESTION_THRESHOLD"]

    graph = get_graph()
    candidates: dict[str, str] = {}
    for name in unknown_names:
        slug = slugify_skill(name)
        if slug and slug not in graph.resolve and slug not in candidates:
            candidates[slug] = name.strip()
    already = set(SkillAliasSuggestion.objects.filter(slug__in=candidates).values_list("slug", flat=True))
    for slug in already:
        candidates.pop(slug)

    targets = list(Skill.objects.all())
    if not candidates or not targets:
        return []

    try:
        vectors = embedder.embed_many([skill.name for skill in targets] + list(candidates.values()))
    except llm.LLMUnavailable as exc:
        logger.warning("Alias suggestions skipped: %s", exc)
        return []
    skill_vectors, name_vectors = vectors[: len(targets)], vectors[len(targets):]

    created = []
    for (slug, name), vector in zip(candidates.items(), name_vectors):
        score, best = max(
            ((cosine(vector, target_vector), skill) for skill, target_vector in zip(targets, skill_vectors)),
            key=lambda pair: pair[0],
        )
        if score >= threshold:
            created.append(SkillAliasSuggestion.objects.create(alias=name, skill=best, similarity=round(score, 4)))
    return created
