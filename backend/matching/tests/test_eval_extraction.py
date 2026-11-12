"""
The hand-checked reference set, and `manage.py eval_extraction` over it.

CI has no Ollama, so the LLM column is exercised with a `FakeLLMClient`.
"""

import io
import json

import pytest
from django.core.management import call_command

from matching import llm
from matching.management.commands.make_sample_resumes import render_samples
from matching.samples import RELEVANT_KEYS, SAMPLE_RESUMES
from matching.testing import FakeLLMClient, resume_reply


def run(*args) -> str:
    out = io.StringIO()
    call_command("eval_extraction", *args, stdout=out)
    return out.getvalue()


def row(output: str, field: str) -> list[str]:
    [line] = [line for line in output.splitlines() if line.split()[:1] == [field]]
    return line.split()


class TestTheReferenceSet:
    def test_it_has_grown_past_the_phase_two_five(self):
        assert len(SAMPLE_RESUMES) >= 10
        assert len({sample.key for sample in SAMPLE_RESUMES}) == len(SAMPLE_RESUMES)

    def test_the_phase_two_relevance_is_unchanged(self):
        assert RELEVANT_KEYS == {"backend_engineer", "data_engineer"}

    def test_it_covers_the_readings_the_regex_fixes_are_about(self):
        by_key = {sample.key: sample for sample in SAMPLE_RESUMES}

        assert by_key["civil_fresher"].expected_experience_years == 0.0
        assert by_key["civil_fresher"].expected_age is not None
        assert "Date of Birth" in by_key["civil_fresher"].text
        assert "experience" not in by_key["electronics_dated"].text.split("EXPERIENCE")[0].lower()
        assert by_key["biotech_masters"].expected_cgpa is not None
        assert "Masters" in by_key["biotech_masters"].expected_education_levels
        assert "Jan'23" in by_key["designer_short_dates"].text

    def test_every_sample_is_rendered_with_its_reference(self, tmp_path):
        written = render_samples(tmp_path)
        reference = json.loads((tmp_path / "reference.json").read_text())

        assert len(written) == len(SAMPLE_RESUMES)
        assert set(reference) == {sample.filename for sample in SAMPLE_RESUMES}
        assert reference["rohan_patil_civil.pdf"]["age"] == 21
        assert reference["nandini_rao_biotech.docx"]["cgpa"] == 8.6
        assert "age" not in reference["aarav_mehta_backend.pdf"]


class TestEvalExtractionWithTheLlmOff:
    def test_regex_reproduces_every_hand_checked_value(self):
        output = run()

        scored = len(SAMPLE_RESUMES)
        assert row(output, "experience")[1:3] == [str(scored), f"{scored}/{scored}"]
        assert row(output, "education")[1:3] == [str(scored), f"{scored}/{scored}"]
        ages = sum(sample.expected_age is not None for sample in SAMPLE_RESUMES)
        cgpas = sum(sample.expected_cgpa is not None for sample in SAMPLE_RESUMES)
        assert row(output, "age")[1:3] == [str(ages), f"{ages}/{ages}"]
        assert row(output, "cgpa")[1:3] == [str(cgpas), f"{cgpas}/{cgpas}"]
        assert "Misses: none" in output

    def test_there_is_no_llm_column(self):
        assert "llm" not in row(run(), "field")

    def test_asking_for_the_llm_while_it_is_off_says_so_and_still_succeeds(self):
        output = run("--llm")

        assert "LLM is disabled" in output
        assert "llm" not in row(output, "field")


class TestEvalExtractionWithAFakeLlm:
    @pytest.fixture
    def llm_on(self, monkeypatch):
        def _install(client):
            monkeypatch.setattr(llm, "llm_enabled", lambda: True)
            monkeypatch.setattr(llm, "get_client", lambda: client)
            return client

        return _install

    def test_the_model_is_scored_beside_regex(self, llm_on):
        client = llm_on(FakeLLMClient(lambda system, user: resume_reply(experience=[])))

        output = run("--llm")

        assert row(output, "field")[-2:] == ["regex", "llm"]
        assert len(client.prompts) == len(SAMPLE_RESUMES)

    def test_the_models_misses_are_listed_by_sample(self, llm_on):
        # A model that always answers UG with no dated work: right for a
        # fresher, wrong for anyone with experience or a Masters.
        llm_on(FakeLLMClient(lambda system, user: resume_reply(experience=[])))

        output = run("--llm")

        assert "llm    experience  backend_engineer" in output
        assert "llm    education   biotech_masters" in output
        assert "regex  " not in output.split("Misses")[1]

    def test_the_model_runs_whenever_it_is_enabled(self, llm_on):
        llm_on(FakeLLMClient(lambda system, user: resume_reply()))

        assert row(run(), "field")[-1] == "llm"

    def test_a_model_that_is_down_is_a_miss_not_a_crash(self, llm_on):
        llm_on(FakeLLMClient(down=True))

        output = run("--llm")

        assert "unavailable" in output
        assert row(output, "experience")[-2] == f"0/{len(SAMPLE_RESUMES)}"
