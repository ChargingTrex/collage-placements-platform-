"""Fixtures for the profile tests that touch the matching engine's caches."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_matching_caches(settings):
    """
    The skill graph and vector store are cached per process, and a test's
    rollback fires no signal, so either would leak between tests. The local
    store is pinned so a developer's MONGO_URI never receives test vectors.
    """
    from matching.skills import reset_skill_graph
    from matching.vectorstore import reset_vector_store

    settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "local"}
    reset_skill_graph()
    reset_vector_store()
    yield
    reset_skill_graph()
    reset_vector_store()
