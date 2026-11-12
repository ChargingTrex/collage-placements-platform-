"""Fixtures shared by the matching engine tests."""

from pathlib import Path

import pytest

from matching.engine import MatchingEngine
from matching.management.commands.make_sample_resumes import render_samples
from matching.samples import SAMPLE_RESUMES


@pytest.fixture(scope="session")
def sample_resume_dir(tmp_path_factory) -> Path:
    """Real PDF and DOCX files, rendered once for the whole session."""
    out = tmp_path_factory.mktemp("resumes")
    render_samples(out)
    return out


@pytest.fixture(scope="session")
def engine() -> MatchingEngine:
    """
    The engine on whichever backend this machine has.

    Session-scoped because loading the spaCy model is slow and the engine is
    stateless once built.
    """
    return MatchingEngine()


@pytest.fixture(scope="session")
def sample_texts(engine, sample_resume_dir) -> dict[str, str]:
    """Every sample resume parsed out of its real binary file."""
    texts = {}
    for sample in SAMPLE_RESUMES:
        with (sample_resume_dir / sample.filename).open("rb") as handle:
            texts[sample.key] = engine.parse_resume(handle, sample.filename).raw_text
    return texts


@pytest.fixture(autouse=True)
def _fresh_skill_graph():
    """A test's rollback fires no signal, so a graph it cached would leak."""
    from matching.skills import reset_skill_graph

    reset_skill_graph()
    yield
    reset_skill_graph()
