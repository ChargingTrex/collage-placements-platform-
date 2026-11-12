"""
Test doubles for the model server, shared by every app's tests.

CI has no Ollama. `FakeLLMClient` stands in for `llm.LLMClient`: chat replies
come from a queue (or a function of the prompt), and embeddings are a hashed
bag of words -- deterministic, cheap, and similar for texts that share
vocabulary, so ranking tests still mean something.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable

from matching.llm import LLMClient, LLMUnavailable

EMBED_DIMS = 64
_WORD = re.compile(r"[a-z][a-z0-9+#.]*")


def fake_embedding(text: str, dims: int = EMBED_DIMS) -> list[float]:
    """A unit vector from hashed words. Shared words -> higher cosine."""
    vector = [0.0] * dims
    for word in _WORD.findall((text or "").lower()):
        if len(word) < 3:
            continue
        bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % dims
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeLLMClient(LLMClient):
    """
    An LLMClient that never opens a socket.

    `replies` is a list of chat replies (dicts are JSON-encoded, strings sent
    as-is) consumed in order, or a callable `(system, user) -> reply`.
    `down=True` makes every call raise LLMUnavailable, like a stopped server.
    """

    def __init__(
        self,
        replies: list | Callable[[str, str], object] | None = None,
        *,
        down: bool = False,
        model: str = "fake-llama",
        embed_model: str = "fake-embed",
    ):
        super().__init__(base_url="http://fake", model=model, embed_model=embed_model, timeout=1)
        self._replies = replies if callable(replies) else list(replies or [])
        self.down = down
        self.prompts: list[tuple[str, str]] = []
        self.embedded: list[str] = []

    def chat_json(self, system: str, user: str) -> str:
        if self.down:
            raise LLMUnavailable("fake server is down")
        self.prompts.append((system, user))
        if callable(self._replies):
            reply = self._replies(system, user)
        elif self._replies:
            reply = self._replies.pop(0)
        else:
            raise AssertionError("FakeLLMClient ran out of replies")
        return reply if isinstance(reply, str) else json.dumps(reply)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.down:
            raise LLMUnavailable("fake server is down")
        self.embedded.extend(texts)
        return [fake_embedding(text) for text in texts]


def resume_reply(**overrides) -> dict:
    """A well-formed resume reply; override any key."""
    reply = {
        "full_name": "Aarav Mehta",
        "emails": ["aarav.mehta@college.edu"],
        "phones": [],
        "age": None,
        "date_of_birth": None,
        "cgpa": None,
        "education": [
            {"degree": "B.Tech in Computer Engineering", "level": "UG", "field": "Computer Engineering",
             "institution": "Sai University", "start": "2022", "end": "2026", "cgpa": None}
        ],
        "experience": [],
        "skills": ["Python", "Django"],
        "projects": [],
        "certifications": [],
        "links": [],
    }
    reply.update(overrides)
    return reply


def job_reply(**overrides) -> dict:
    """A well-formed JD reply; override any key."""
    reply = {
        "title": "Backend Engineer",
        "canonical_role": "Backend Engineer",
        "required_skills": ["Python", "Django", "PostgreSQL"],
        "nice_to_have": ["Celery"],
        "min_experience_years": 2,
        "education_levels": ["UG"],
    }
    reply.update(overrides)
    return reply
