"""
Where profile vectors live, and how the nearest ones are found.

Two stores behind one interface, selected like the similarity backend:

    mongo  MongoDB `$vectorSearch` (Atlas, or the mongodb-atlas-local image)
    local  numpy cosine over the `StoredVector` table -- SQLite dev and CI
    auto   (default) mongo when MONGO_URI is set and reachable, else local

Two rules hold for both:

- **No resume text and no contact details are stored here** -- only an id,
  the vector, the model that made it, and the metadata companies filter on.
  The second copy of student data stays minimal.
- **This layer never decides who may see a profile.** `search()` returns
  candidate ids; callers pass them through `StudentProfile.objects.visible_to`
  before anything reaches a response.

Filters are a small shared dialect so both stores mean the same thing:
    {"department": "CE"}              equality (or "contains" for a list field)
    {"skills": {"in": ["python"]}}    any of
    {"experience_months": {"gte": 12}}
"""

from __future__ import annotations

import logging
from functools import lru_cache

from django.conf import settings

from matching.embeddings import cosine

logger = logging.getLogger(__name__)

#: The metadata both stores can filter on. Mongo's index declares exactly these.
FILTER_FIELDS = ("department", "batch", "education_level", "experience_months", "skills", "categories")


class VectorStore:
    """Interface every store implements."""

    name = "base"

    def upsert(self, doc_id: str, vector: list[float], meta: dict, model: str) -> None:
        raise NotImplementedError

    def search(
        self, vector: list[float], k: int, model: str, filters: dict | None = None
    ) -> list[tuple[str, float]]:
        """The k nearest (doc_id, cosine) pairs, best first."""
        raise NotImplementedError

    def get(self, doc_id: str) -> tuple[list[float], dict, str] | None:
        """(vector, meta, model) for one document, or None."""
        raise NotImplementedError

    def delete(self, doc_id: str) -> None:
        raise NotImplementedError

    def update_meta(self, doc_id: str, meta: dict) -> None:
        """Merge metadata into a stored document without re-embedding it."""
        raise NotImplementedError


def _clean_meta(meta: dict) -> dict:
    """Only the filterable fields -- nothing else is allowed into a store."""
    return {key: meta[key] for key in FILTER_FIELDS if key in meta}


def matches_filters(meta: dict, filters: dict | None) -> bool:
    """The local reading of the shared filter dialect."""
    for key, condition in (filters or {}).items():
        value = meta.get(key)
        if isinstance(condition, dict):
            if "in" in condition:
                wanted = set(condition["in"])
                held = set(value) if isinstance(value, list) else {value}
                if not wanted & held:
                    return False
            if "gte" in condition and (value is None or value < condition["gte"]):
                return False
            if "lte" in condition and (value is None or value > condition["lte"]):
                return False
        elif isinstance(value, list):
            if condition not in value:
                return False
        elif value != condition:
            return False
    return True


# --- local -------------------------------------------------------------------


class LocalVectorStore(VectorStore):
    """
    Exact cosine over every stored vector of the same model.

    Linear in the number of profiles. A college roster is thousands, not
    millions, so this is fast enough for dev and a small deployment.
    """

    name = "local"

    def upsert(self, doc_id, vector, meta, model):
        from matching.models import StoredVector

        StoredVector.objects.update_or_create(
            doc_id=str(doc_id),
            defaults={"vector": list(vector), "model": model, "dims": len(vector), "meta": _clean_meta(meta)},
        )

    def search(self, vector, k, model, filters=None):
        import numpy as np

        from matching.models import StoredVector

        rows = [
            row
            for row in StoredVector.objects.filter(model=model, dims=len(vector))
            if matches_filters(row.meta, filters)
        ]
        if not rows or k <= 0:
            return []
        matrix = np.asarray([row.vector for row in rows], dtype=float)
        query = np.asarray(vector, dtype=float)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query) or 1.0)
        scores = np.divide(matrix @ query, norms, out=np.zeros(len(rows)), where=norms > 0)
        order = np.argsort(-scores)[:k]
        return [(rows[i].doc_id, max(0.0, float(scores[i]))) for i in order]

    def get(self, doc_id):
        from matching.models import StoredVector

        row = StoredVector.objects.filter(doc_id=str(doc_id)).first()
        return (row.vector, row.meta, row.model) if row else None

    def delete(self, doc_id):
        from matching.models import StoredVector

        StoredVector.objects.filter(doc_id=str(doc_id)).delete()

    def update_meta(self, doc_id, meta):
        from matching.models import StoredVector

        row = StoredVector.objects.filter(doc_id=str(doc_id)).first()
        if row:
            row.meta = {**row.meta, **_clean_meta(meta)}
            row.save(update_fields=["meta", "updated_at"])


# --- mongo -------------------------------------------------------------------


def mongo_filter(model: str, filters: dict | None) -> dict:
    """The shared dialect as a `$vectorSearch` pre-filter."""
    clauses = [{"model": {"$eq": model}}]
    for key, condition in (filters or {}).items():
        path = f"meta.{key}"
        if isinstance(condition, dict):
            if "in" in condition:
                clauses.append({path: {"$in": list(condition["in"])}})
            if "gte" in condition:
                clauses.append({path: {"$gte": condition["gte"]}})
            if "lte" in condition:
                clauses.append({path: {"$lte": condition["lte"]}})
        else:
            # On an array field, $eq matches any element: "contains".
            clauses.append({path: {"$eq": condition}})
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def vector_index_definition(dims: int) -> dict:
    """The search index `manage.py init_vector_index` creates."""
    return {
        "fields": [
            {"type": "vector", "path": "vector", "numDimensions": dims, "similarity": "cosine"},
            {"type": "filter", "path": "model"},
            *({"type": "filter", "path": f"meta.{field}"} for field in FILTER_FIELDS),
        ]
    }


class MongoVectorStore(VectorStore):
    """`$vectorSearch` over a MongoDB collection."""

    name = "mongo"

    def __init__(self, collection, index_name: str):
        self._collection = collection
        self._index = index_name

    @classmethod
    def from_settings(cls) -> "MongoVectorStore":
        import pymongo  # imported lazily: optional dependency

        config = settings.VECTOR_STORE
        client = pymongo.MongoClient(config["MONGO_URI"], serverSelectionTimeoutMS=2000)
        client.admin.command("ping")  # fail now, not on the first upload
        return cls(client[config["DB"]][config["COLLECTION"]], config["INDEX"])

    def upsert(self, doc_id, vector, meta, model):
        import datetime

        self._collection.replace_one(
            {"_id": str(doc_id)},
            {
                "_id": str(doc_id),
                "vector": list(vector),
                "model": model,
                "dims": len(vector),
                "meta": _clean_meta(meta),
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
            upsert=True,
        )

    def search(self, vector, k, model, filters=None):
        if k <= 0:
            return []
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self._index,
                    "path": "vector",
                    "queryVector": list(vector),
                    "numCandidates": min(max(k * 10, 100), 10_000),
                    "limit": k,
                    "filter": mongo_filter(model, filters),
                }
            },
            {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        # For cosine, Mongo reports (1 + cos) / 2. Convert back, so both
        # stores return the same number for the same pair.
        return [
            (doc["_id"], max(0.0, 2.0 * float(doc["score"]) - 1.0))
            for doc in self._collection.aggregate(pipeline)
        ]

    def get(self, doc_id):
        doc = self._collection.find_one({"_id": str(doc_id)})
        return (doc["vector"], doc.get("meta", {}), doc["model"]) if doc else None

    def delete(self, doc_id):
        self._collection.delete_one({"_id": str(doc_id)})

    def update_meta(self, doc_id, meta):
        clean = _clean_meta(meta)
        if clean:
            self._collection.update_one(
                {"_id": str(doc_id)}, {"$set": {f"meta.{key}": value for key, value in clean.items()}}
            )

    def create_index(self, dims: int) -> None:
        spec = {"definition": vector_index_definition(dims), "name": self._index, "type": "vectorSearch"}
        try:
            from pymongo.operations import SearchIndexModel
        except ImportError:
            # `create_search_index` takes the same keys as a plain mapping;
            # this path also lets the command be tested without pymongo.
            self._collection.create_search_index(spec)
            return
        self._collection.create_search_index(SearchIndexModel(**spec))


# --- selection ---------------------------------------------------------------


@lru_cache(maxsize=None)
def get_vector_store(name: str | None = None) -> VectorStore:
    """The process-wide store, per settings.VECTOR_STORE["BACKEND"]."""
    requested = (name or settings.VECTOR_STORE["BACKEND"]).strip().lower()

    if requested == "local":
        return LocalVectorStore()
    if requested == "mongo":
        return MongoVectorStore.from_settings()
    if requested != "auto":
        raise ValueError(f"Unknown VECTOR_STORE_BACKEND '{requested}'. Use auto, mongo, or local.")

    if settings.VECTOR_STORE["MONGO_URI"]:
        try:
            return MongoVectorStore.from_settings()
        except Exception as exc:  # ImportError, connection failure
            logger.warning("MongoDB vector store unavailable (%s); using the local store.", exc)
    return LocalVectorStore()


def reset_vector_store() -> None:
    """Drop the cached store. For tests that swap settings."""
    get_vector_store.cache_clear()


def vector_store_info() -> dict:
    """Which store is live -- for /api/health."""
    try:
        store = get_vector_store()
        return {"ok": True, "backend": store.name}
    except Exception as exc:  # pragma: no cover - misconfiguration only
        return {"ok": False, "backend": "none", "detail": str(exc)}


__all__ = [
    "VectorStore",
    "LocalVectorStore",
    "MongoVectorStore",
    "get_vector_store",
    "reset_vector_store",
    "matches_filters",
    "mongo_filter",
    "cosine",
]
