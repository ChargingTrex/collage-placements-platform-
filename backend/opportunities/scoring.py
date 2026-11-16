"""
One profile against one posting, cached.

The feed, apply and (later) suggestions all score through here, so a score a
student sees is the score that gets stored on their application. The scoring
itself is `profiles.match`; this module only adds the cache.
"""

from __future__ import annotations

import json

from django.core.cache import cache

from profiles.analysis import resume_digest
from profiles.match import profile_payload, read_job, score_profile

CACHE_SECONDS = 60 * 60


def score_key(payload: dict, opportunity) -> str:
    """
    `(resume_digest, opportunity.id, opportunity.updated_at)`.

    The digest covers the whole scored payload (form, resume text, skills,
    experience, education), not the resume file alone: a skill added on the
    form changes the score and must not be served a stale one. `updated_at`
    moves whenever the JD is edited.
    """
    digest = resume_digest(json.dumps(payload, sort_keys=True, default=str))
    return f"opp-score:{digest}:{opportunity.id}:{opportunity.updated_at.timestamp()}"


def score_for(profile, opportunity, *, job=None) -> dict:
    """
    {score, similarity, components, matched_skills, missing_skills,
    hard_filter_failures} for this profile against this posting.

    The JD is read only on a cache miss.
    """
    key = score_key(profile_payload(profile), opportunity)
    cached = cache.get(key)
    if cached is not None:
        return cached
    job = job or read_job(opportunity.description)
    result = score_profile(profile, job).as_dict()
    row = {
        "score": result["score"],
        "similarity": float(result["components"].get("semantic", {}).get("raw", 0.0) or 0.0),
        "components": result["components"],
        "matched_skills": result["matched_skills"],
        "missing_skills": result["missing_skills"],
        "hard_filter_failures": result["hard_filter_failures"],
    }
    cache.set(key, row, CACHE_SECONDS)
    return row
