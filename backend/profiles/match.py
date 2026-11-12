"""
Matching profiles against a job description: search, score, own match.

The engine (`get_engine().match_score`) scores one plain dict against one
JD; this module turns profiles into those dicts and decides which profiles
are scored at all. That decision is `StudentProfile.objects.visible_to`
and nothing else: the vector store only proposes candidate ids, and an id
it returns for a hidden profile goes no further than the queryset.

Two search paths (plan §5.5):

    embedder   the JD is embedded, the store returns 3k nearest ids, the
               visible ones are scored on their stored vectors
    fallback   no embedder, the LLM unreachable, or an empty store: every
               visible profile with resume text is scored on the similarity
               backend, up to MATCH_SCORE["FALLBACK_MAX_PROFILES"]
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from matching import llm, vectorstore
from matching.categories import canonical_category_names, record_job_description
from matching.embeddings import get_embedder
from matching.engine import MatchScore, get_engine
from matching.skills import canonical_slug, find_in_text
from matching.vectorstore import matches_filters
from profiles.analysis import _BudgetedClient, llm_client, profile_document, vector_doc_id, vector_meta
from profiles.models import ResumeAnalysis, StudentProfile

logger = logging.getLogger(__name__)


# --- the job ---------------------------------------------------------------------


@dataclass
class Job:
    """One JD, read once and scored against many profiles."""

    text: str
    requirements: dict
    facts: llm.JobFacts | None = None
    vector: list[float] | None = None
    model: str | None = None

    def summary(self) -> dict:
        """What the caller is told the JD asks for. Never the JD text back."""
        return {
            "canonical_role": self.facts.canonical_role if self.facts else None,
            **self.requirements,
        }


#: How long a JD that fed a category is remembered, so the same JD pasted
#: again within it does not count twice.
JD_RECORDED_SECONDS = 60 * 60 * 24 * 30


def jd_recorded_key(jd_text: str) -> str:
    digest = hashlib.sha256(jd_text.strip().encode("utf-8")).hexdigest()
    return f"jd-recorded:{digest}"


def _record_once(jd_text: str, facts: llm.JobFacts, vector, model) -> None:
    """
    Feed the role categories with this JD, unless it already fed them.

    "Already fed" is its own marker, not the facts cache: a student's
    `me/match` caches the facts too, and must not stop the recruiter's
    reading from counting. `cache.add` claims the marker before the write,
    so two concurrent requests for one JD count it once; a failed write
    gives it back, so the next request tries again.
    """
    key = jd_recorded_key(jd_text)
    if not cache.add(key, True, JD_RECORDED_SECONDS):
        return
    try:
        record_job_description(facts, vector, model=model if vector is not None else None)
    except Exception:  # a category is a by-product; the match is the answer
        cache.delete(key)
        logger.exception("Could not record the JD in a role category")


def read_job(jd_text: str, *, record: bool = False) -> Job:
    """
    The JD's requirements and, when the LLM is on, its facts and vector.

    Both model calls share the analysis time budget, so a slow server
    costs at most that before the request falls back to the text reading.

    With `record` (company and admin requests), a JD the model has read
    feeds the role categories (Task 7), once per JD. A student's JD never
    does: categories describe what recruiters hire for.
    """
    client = llm_client()
    facts = vector = model = None
    if client is not None:
        deadline = time.monotonic() + settings.RESUME_ANALYSIS["TIME_BUDGET_SECONDS"]
        budgeted = _BudgetedClient(client, deadline)
        try:
            facts = llm.parse_job_description(jd_text, client=budgeted)
        except llm.LLMUnavailable as exc:
            logger.warning("JD reading fell back to the text: %s", exc)
        embedder = get_embedder(budgeted)
        vector = embedder.try_embed(jd_text)
        model = embedder.model
    if record and facts is not None:
        _record_once(jd_text, facts, vector, model)
    requirements = get_engine().job_requirements(jd_text, facts)
    return Job(text=jd_text, requirements=requirements, facts=facts, vector=vector, model=model)


# --- the profile -----------------------------------------------------------------


def _analysis(profile: StudentProfile) -> ResumeAnalysis | None:
    try:
        return profile.analysis
    except ResumeAnalysis.DoesNotExist:
        return None


def profile_categories(profile: StudentProfile) -> list[str]:
    """The role categories the profile was last sorted into."""
    analysis = _analysis(profile)
    return list(analysis.categories or []) if analysis is not None else []


def profile_skill_names(profile: StudentProfile, analysis: ResumeAnalysis | None = None) -> list[str]:
    """
    What the profile holds: the form's skills, the model's reading of the
    resume, and known skills the resume text names, in that order.
    """
    analysis = analysis if analysis is not None else _analysis(profile)
    names = [skill.name for skill in profile.skills.all()]
    if analysis is not None and analysis.facts:
        names += [name for name in analysis.facts.get("skills") or [] if isinstance(name, str)]
    names += find_in_text(profile.resume_text or "")
    seen, unique = set(), []
    for name in names:
        slug = canonical_slug(name)
        if slug and slug not in seen:
            seen.add(slug)
            unique.append(name)
    return unique


def profile_payload(profile: StudentProfile) -> dict:
    """
    The plain dict `engine.match_score` reads: the student's own values.

    Experience and education are the confirmed (or pre-filled) ones, the
    parser's levels only when the student has none. Nothing admin-only.
    """
    levels = [profile.education_level] if profile.education_level else list(profile.parsed_education_levels or [])
    return {
        "text": profile_document(profile),
        "skills": profile_skill_names(profile),
        "experience_years": float(profile.experience_years),
        "education_levels": levels,
    }


def _stored_vector(profile: StudentProfile, job: Job) -> list[float] | None:
    """The profile's vector, when it was made by the model the JD was."""
    if job.vector is None:
        return None
    try:
        stored = vectorstore.get_vector_store().get(vector_doc_id(profile))
    except Exception as exc:  # the store is optional; the score is not
        logger.warning("Vector store unavailable while scoring: %s", exc)
        return None
    if not stored:
        return None
    vector, _, model = stored
    return vector if model == job.model and len(vector) == len(job.vector) else None


def score_profile(profile: StudentProfile, job: Job) -> MatchScore:
    """One profile against the JD, on its stored vector when there is one."""
    vector = _stored_vector(profile, job)
    return get_engine().match_score(
        profile_payload(profile),
        job.text,
        job_facts=job.facts,
        vector=vector,
        jd_vector=job.vector if vector is not None else None,
        requirements=job.requirements,
    )


# --- many profiles ---------------------------------------------------------------


def normalise_filters(filters: dict | None) -> dict:
    """
    Skills compare as canonical slugs, the way the store holds them, and
    category names in their stored spelling, whatever the case typed.
    """
    clean = {}
    for key, condition in (filters or {}).items():
        if key == "skills":
            if isinstance(condition, dict) and "in" in condition:
                condition = {**condition, "in": [canonical_slug(str(v)) for v in condition["in"]]}
            elif not isinstance(condition, dict):
                condition = canonical_slug(str(condition))
        elif key == "categories":
            if isinstance(condition, dict) and "in" in condition:
                condition = {**condition, "in": canonical_category_names(str(v) for v in condition["in"])}
            elif not isinstance(condition, dict):
                condition = canonical_category_names([str(condition)])[0]
        clean[key] = condition
    return clean


def _ranked(scored: list[tuple[StudentProfile, MatchScore]], k: int | None = None):
    scored.sort(key=lambda pair: (-pair[1].score, pair[0].student.prn))
    return scored[:k] if k is not None else scored


def search(user, job: Job, k: int, filters: dict | None = None) -> tuple[list, bool]:
    """
    The k best visible matches for the JD, and whether the fallback ran.
    """
    filters = normalise_filters(filters)
    visible = StudentProfile.objects.visible_to(user).with_related().select_related("analysis")

    hits = None
    if job.vector is not None:
        try:
            hits = vectorstore.get_vector_store().search(job.vector, k * 3, job.model, filters)
        except Exception as exc:
            logger.warning("Vector search failed, falling back to the backend: %s", exc)
    if hits:
        ids = [doc_id for doc_id, _ in hits]
        candidates = list(visible.filter(student_id__in=ids))
        return _ranked([(p, score_profile(p, job)) for p in candidates], k), False

    cap = settings.MATCH_SCORE["FALLBACK_MAX_PROFILES"]
    pool = visible.exclude(resume_text="").order_by("-resume_uploaded_at", "student__prn")
    candidates = []
    for profile in pool:
        if len(candidates) >= cap:
            break
        if filters and not matches_filters(vector_meta(profile, _analysis(profile) or ResumeAnalysis()), filters):
            continue
        candidates.append(profile)
    return _ranked([(p, score_profile(p, job)) for p in candidates], k), True


def score_named(user, job: Job, student_ids) -> list:
    """Named profiles, visible ones only. Others are left out, silently."""
    profiles = (
        StudentProfile.objects.visible_to(user)
        .with_related()
        .select_related("analysis")
        .filter(student_id__in=list(student_ids))
    )
    return _ranked([(p, score_profile(p, job)) for p in profiles])
