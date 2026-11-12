"""
Text embeddings for fast matching, from the same Ollama server as the LLM.

An embedding is optional in the way spaCy is: when the server is down or
disabled, `get_embedder()` returns None and scoring falls back to the
similarity backend (`matching/backends.py`). Every vector carries the model
that produced it, because vectors from two models do not share a space --
changing EMBED_MODEL means reindexing, never mixing.
"""

from __future__ import annotations

import logging
import math

from matching import llm

logger = logging.getLogger(__name__)

#: Long enough for a full profile; Ollama truncates beyond the model's window.
MAX_EMBED_CHARS = 8_000


def normalise(vector: list[float]) -> list[float]:
    """Unit length, so a dot product is a cosine."""
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else list(vector)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine of two vectors, clamped to [0, 1] like every portal score."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return max(0.0, dot / norms) if norms else 0.0


class Embedder:
    """Embeds text through an LLMClient's `/embeddings` endpoint."""

    def __init__(self, client: llm.LLMClient):
        self._client = client

    @property
    def model(self) -> str:
        return self._client.embed_model

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Unit vectors, one per text. Raises LLMUnavailable."""
        if not texts:
            return []
        vectors = self._client.embed([(t or "")[:MAX_EMBED_CHARS] for t in texts])
        if len(vectors) != len(texts):
            raise llm.LLMUnavailable("The embeddings reply had the wrong number of vectors.")
        # A malformed reply is the server's failure, not the caller's: it
        # must reach `try_embed` as LLMUnavailable, never as a ValueError.
        try:
            floats = [[float(v) for v in vector] for vector in vectors]
        except (TypeError, ValueError) as exc:
            raise llm.LLMUnavailable(f"The embeddings reply was not numeric: {exc}") from exc
        dims = {len(vector) for vector in floats}
        if len(dims) != 1 or 0 in dims:
            raise llm.LLMUnavailable(f"The embeddings reply mixed or lacked dimensions: {sorted(dims)}")
        return [normalise(vector) for vector in floats]

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def try_embed(self, text: str) -> list[float] | None:
        """The vector, or None when the server cannot be reached."""
        try:
            return self.embed(text)
        except llm.LLMUnavailable as exc:
            logger.warning("Embedding unavailable, falling back: %s", exc)
            return None


def get_embedder(client: llm.LLMClient | None = None) -> Embedder | None:
    """An embedder, or None when the LLM is disabled and no client was given."""
    if client is not None:
        return Embedder(client)
    if not llm.llm_enabled():
        return None
    return Embedder(llm.get_client())
