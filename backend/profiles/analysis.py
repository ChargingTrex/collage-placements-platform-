"""
Resume analysis: the full reading, the profile vector, and form suggestions.

The upload stays fast: it runs the regex pre-fill and leaves a pending
`ResumeAnalysis`. `analyse()` then does the slow part, in order:

    extract     engine.analyse_resume: regex always, the LLM when it is on
    embed       the profile document (form + resume text), when the LLM is on
    categorise  matching.categories (empty until Task 7)
    upsert      the vector, with filter metadata only, into the vector store
    suggest     resume skills the graph does not know, as pending alias
                suggestions for an admin (never merged here)

There is no task queue, and this keeps it that way. Instead the whole run
gets `RESUME_ANALYSIS["TIME_BUDGET_SECONDS"]`, kept below the server's
request timeout: each model call is given only what is left of it, and none
once it is spent. A call that runs out falls back to the regex reading,
which still counts as done but records the error, so the next request (or
`manage.py analyze_resumes`) runs the model again. An embedding that runs
out marks the profile for `manage.py reindex_vectors --dirty-only`.

Payloads built here go to the student. They never carry age, DOB, CGPA,
phone numbers or emails, even though `facts` holds them: those are for
admins only (Task 8).
"""

from __future__ import annotations

import calendar
import difflib
import hashlib
import logging
import re
import time

from django.conf import settings
from django.utils import timezone

from core.models import AuditLog
from matching import llm
from matching.categories import categorise_profile
from matching.embeddings import get_embedder
from matching.engine import get_engine
from matching.skills import canonical, canonical_slug, expand_slugs, get_graph, suggest_aliases
from matching.vectorstore import get_vector_store
from profiles.models import ExperienceEntry, ResumeAnalysis, StudentProfile

logger = logging.getLogger(__name__)


def resume_digest(text: str) -> str:
    """sha256 of the resume text: two files with the same words read alike."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def vector_doc_id(profile: StudentProfile) -> str:
    """The vector's key: the student's uuid, never PRN or email (D8)."""
    return str(profile.student_id)


def profile_document(profile: StudentProfile) -> str:
    """
    What gets embedded: the form first, then the resume text.

    The form leads so it survives the embedder's length cut, and so a
    student who fills the form in well is found even with a thin resume.
    """
    skills = [skill.name for skill in profile.skills.all()]
    parts = [
        profile.headline,
        profile.summary,
        f"Skills: {', '.join(skills)}" if skills else "",
        *(entry.searchable_text() for entry in profile.experience_entries.all()),
        *(project.searchable_text() for project in profile.projects.all()),
        profile.resume_text,
    ]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def vector_meta(profile: StudentProfile, analysis: ResumeAnalysis) -> dict:
    """
    The filter fields, from the student's own values: the confirmed (or
    pre-filled) ones, and the reading's education level only when the
    profile has none.

    Skills are canonical slugs plus what they imply, so a filter on
    "python" finds a student who listed only Django.
    """
    return {
        "department": profile.student.department,
        "batch": profile.student.batch,
        "education_level": profile.education_level or analysis.education_level,
        "experience_months": int(round(float(profile.experience_years) * 12)),
        "skills": sorted(expand_slugs(skill.name for skill in profile.skills.all())),
        "categories": list(analysis.categories or []),
    }


# --- the time budget -------------------------------------------------------------


class _BudgetedClient:
    """
    An LLM client that gives each call only what is left of the budget.

    The client's own timeout is per request, and one analysis makes up to
    three (a reply, a retry, an embedding), so it cannot bound the total.
    """

    def __init__(self, inner: llm.LLMClient, deadline: float):
        self._inner = inner
        self._deadline = deadline
        self._configured = inner.timeout

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def embed_model(self) -> str:
        return self._inner.embed_model

    def _arm(self) -> None:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise llm.LLMUnavailable("The resume analysis time budget ran out.")
        self._inner.timeout = min(self._configured, left)

    def chat_json(self, system: str, user: str) -> str:
        self._arm()
        return self._inner.chat_json(system, user)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._arm()
        return self._inner.embed(texts)


def llm_client() -> llm.LLMClient | None:
    """The configured client, or None when the LLM is off."""
    return llm.get_client() if llm.llm_enabled() else None


# --- the pipeline ------------------------------------------------------------------


def mark_pending(profile: StudentProfile) -> ResumeAnalysis:
    """
    A new resume: whatever was read before no longer applies.

    When the text changed, the old vector goes now rather than at the next
    analysis: until then search would rank the student on a resume they
    replaced, under its stale categories. Search falls back for them until
    `analyze` runs, which the frontend starts straight after the upload.
    """
    digest = resume_digest(profile.resume_text)
    previous = ResumeAnalysis.objects.filter(profile=profile).values_list("resume_sha256", flat=True).first()
    if previous is not None and previous != digest:
        drop_vector(profile)
    analysis, _ = ResumeAnalysis.objects.update_or_create(
        profile=profile,
        defaults={
            "status": ResumeAnalysis.Status.PENDING,
            "resume_sha256": digest,
            "source": "",
            "model_name": "",
            "facts": None,
            "regex_facts": {},
            "agreement": {},
            "categories": [],
            "analysed_at": None,
            "error": "",
        },
    )
    return analysis


def is_current(analysis: ResumeAnalysis, profile: StudentProfile) -> bool:
    """Done, for this very text, and with nothing a retry could improve."""
    return (
        analysis.status == ResumeAnalysis.Status.DONE
        and analysis.resume_sha256 == resume_digest(profile.resume_text)
        and not analysis.error
    )


def analyse(
    profile: StudentProfile,
    *,
    client: llm.LLMClient | None = None,
    actor=None,
    force: bool = False,
    today=None,
) -> tuple[ResumeAnalysis, bool]:
    """
    Read the profile's resume fully. Returns (analysis, whether it ran).

    Idempotent: an analysis already current for this text is returned as
    is, unless `force`. `client` defaults to the configured one.
    """
    analysis, _ = ResumeAnalysis.objects.get_or_create(profile=profile)
    if not force and is_current(analysis, profile):
        return analysis, False

    text = profile.resume_text or ""
    analysis.resume_sha256 = resume_digest(text)
    analysis.analysed_at = timezone.now()
    if not text.strip():
        analysis.status = ResumeAnalysis.Status.SKIPPED
        analysis.source, analysis.model_name, analysis.facts = "", "", None
        analysis.regex_facts, analysis.agreement, analysis.error = {}, {}, ""
        analysis.save()
        _audit(profile, analysis, actor)
        return analysis, True

    deadline = time.monotonic() + settings.RESUME_ANALYSIS["TIME_BUDGET_SECONDS"]
    client = client or llm_client()
    budgeted = _BudgetedClient(client, deadline) if client else None

    try:
        extracted = get_engine().analyse_resume(text, client=budgeted, today=today)
    except Exception as exc:  # a reading bug must not cost the student a 500
        logger.exception("Resume analysis failed for %s", profile.prn)
        analysis.status = ResumeAnalysis.Status.FAILED
        analysis.error = f"{type(exc).__name__}: {exc}"[:2000]
        analysis.save()
        _audit(profile, analysis, actor)
        return analysis, True

    analysis.status = ResumeAnalysis.Status.DONE
    analysis.source = extracted.extraction_source
    analysis.facts = extracted.facts
    analysis.model_name = (extracted.facts or {}).get("model", "")
    analysis.regex_facts = extracted.regex_facts
    analysis.agreement = extracted.agreement
    analysis.error = extracted.extraction_error

    if analysis.source == ResumeAnalysis.Source.LLM and extracted.facts.get("experience_months", 0) > 0:
        profile.apply_analysed_experience(extracted.experience_years)
        profile.save(update_fields=["parsed_experience_years", "experience_years", "updated_at"])

    embedder = get_embedder(budgeted) if budgeted else None
    vector = embedder.try_embed(profile_document(profile)) if embedder else None
    from profiles.match import profile_skill_names  # match imports this module

    analysis.categories = categorise_profile(
        vector, profile_skill_names(profile, analysis), model=embedder.model if vector is not None else None
    )
    if vector is not None:
        _store(profile, analysis, vector, embedder.model)
    elif embedder is not None:
        analysis.needs_reindex = True  # the model was meant to embed it and could not
    else:
        # No embedder at all: keep any earlier vector's filters truthful.
        _update_meta(profile, analysis)
    if extracted.facts and embedder is not None:
        _suggest_unknown_skills(extracted.facts.get("skills") or [], embedder)
    analysis.save()
    _audit(profile, analysis, actor)
    return analysis, True


def _suggest_unknown_skills(names: list[str], embedder) -> None:
    """
    Resume skills the graph does not know go to an admin as alias
    suggestions (pending, never merged). Last in the pipeline, so it spends
    only what is left of the budget, and a failure here never costs the
    student their reading.
    """
    try:
        known = get_graph().names
        unknown = [name for name in names if canonical_slug(name) and canonical_slug(name) not in known]
        if unknown:
            suggest_aliases(unknown, embedder)
    except Exception as exc:
        logger.warning("Alias suggestions failed: %s", exc)


def index_profile(profile: StudentProfile, analysis: ResumeAnalysis, embedder) -> bool:
    """(Re-)embed one analysed profile. False leaves it marked dirty."""
    vector = embedder.try_embed(profile_document(profile))
    if vector is None:
        analysis.needs_reindex = True
        analysis.save(update_fields=["needs_reindex", "updated_at"])
        return False
    _store(profile, analysis, vector, embedder.model)
    analysis.save(update_fields=["embedding_model", "needs_reindex", "updated_at"])
    return True


def _store(profile, analysis, vector, model) -> None:
    get_vector_store().upsert(vector_doc_id(profile), vector, vector_meta(profile, analysis), model)
    analysis.embedding_model = model
    analysis.needs_reindex = False


def _update_meta(profile, analysis) -> None:
    try:
        get_vector_store().update_meta(vector_doc_id(profile), vector_meta(profile, analysis))
    except Exception as exc:  # the store is optional; the reading is not
        logger.warning("Could not update vector metadata for %s: %s", profile.prn, exc)


def forget(profile: StudentProfile) -> None:
    """The resume is gone: so are its vector and its reading."""
    drop_vector(profile)
    ResumeAnalysis.objects.filter(profile=profile).delete()


def drop_vector(profile: StudentProfile) -> None:
    """Delete the profile's vector. The store is optional, so this never raises."""
    try:
        get_vector_store().delete(vector_doc_id(profile))
    except Exception as exc:
        logger.warning("Could not delete the vector for profile %s: %s", profile.pk, exc)


def mark_needs_reindex(profile_id) -> None:
    """The form changed, so the stored vector no longer describes it."""
    ResumeAnalysis.objects.filter(profile_id=profile_id, needs_reindex=False).update(needs_reindex=True)


def _audit(profile, analysis, actor) -> None:
    """Which model, which path, what outcome. Never any resume content."""
    AuditLog.record(
        actor=actor,
        action=AuditLog.Action.RESUME_ANALYSED,
        target=profile.prn,
        model_name=analysis.model_name,
        source=analysis.source,
        status=analysis.status,
        experience_years=analysis.experience_years,
    )


# --- what the student sees ------------------------------------------------------


def analysis_payload(profile: StudentProfile, analysis: ResumeAnalysis) -> dict:
    """
    The student-facing reading. Built field by field from an allow-list:
    `facts` holds age, DOB, CGPA, phones and emails, and none of it may leak.
    """
    agreement = {
        key: value for key, value in (analysis.agreement or {}).items()
        if key in ("experience_years", "education_level")
    }
    return {
        "status": analysis.status,
        "source": analysis.source or None,
        "model_name": analysis.model_name or None,
        "analysed_at": analysis.analysed_at.isoformat() if analysis.analysed_at else None,
        "experience_years": analysis.experience_years,
        "education_level": analysis.education_level,
        "agreement": agreement,
        "categories": list(analysis.categories or []),
        # A fallen-back reading: asking again may get the model's.
        "retryable": bool(analysis.error) and analysis.status == ResumeAnalysis.Status.DONE,
        "suggested_skills": suggested_skills(profile, analysis.facts),
        "suggested_experience": suggested_experience(profile, analysis.facts),
    }


def suggested_skills(profile: StudentProfile, facts: dict | None) -> list[str]:
    """Skills on the resume but not on the profile, compared canonically."""
    if not facts:
        return []
    held = {canonical_slug(skill.name) for skill in profile.skills.all()}
    suggestions: list[str] = []
    for name in facts.get("skills") or []:
        slug = canonical_slug(name)
        if slug and slug not in held:
            held.add(slug)
            suggestions.append(canonical(name))
    return suggestions


_ORG_NOISE = re.compile(
    r"\b(?:pvt|private|ltd|limited|llp|llc|inc|corp|corporation|co|company|technologies|solutions)\b"
)


def _normalise(name: str | None) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return " ".join(_ORG_NOISE.sub(" ", words).split())


def _same(a: str | None, b: str | None) -> bool:
    """A fuzzy match: 'Loadstar Logistics Pvt. Ltd.' is 'Loadstar Logistics'."""
    a, b = _normalise(a), _normalise(b)
    if not a or not b:
        return False
    if a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _month_date(value, last: bool = False) -> str | None:
    parsed = llm.parse_month(value)
    if parsed is None:
        return None
    year, month = parsed
    month = month or (12 if last else 1)
    day = calendar.monthrange(year, month)[1] if last else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def suggested_experience(profile: StudentProfile, facts: dict | None) -> list[dict]:
    """
    Resume roles with no form entry, shaped for `POST me/experience`.

    Matched on the organisation (or the role, when the model gave no
    organisation), so the same internship typed differently is not offered
    twice. The student adds a suggestion; nothing is added for them.

    Only entries whose start year is written in the resume are offered, the
    same grounding rule the experience total uses: a model that invents a
    1980 job gets it neither counted nor suggested. A kind the model did not
    give is left out rather than guessed, so nothing is offered as an
    internship that the resume never called one.
    """
    if not facts:
        return []
    entries = list(profile.experience_entries.all())
    text = profile.resume_text or ""
    suggestions = []
    for item in facts.get("experience") or []:
        role, organization = item.get("role"), item.get("organization")
        if not role and not organization:
            continue
        start = llm.parse_month(item.get("start"))
        if start is None or not llm._year_on_page(start[0], text):
            continue
        if organization:
            known = any(_same(organization, entry.organization) for entry in entries)
        else:
            known = any(_same(role, entry.role) for entry in entries)
        if known:
            continue
        suggestion = {
            "role": role or "",
            "organization": organization or "",
            "start_date": _month_date(item.get("start")),
            "end_date": None if item.get("is_current") else _month_date(item.get("end"), last=True),
            "description": item.get("summary") or "",
        }
        if item.get("kind") in ExperienceEntry.Kind.values:
            suggestion["kind"] = item["kind"]
        suggestions.append(suggestion)
    return suggestions
