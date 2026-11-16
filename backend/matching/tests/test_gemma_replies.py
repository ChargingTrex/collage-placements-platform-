"""
Real gemma4:e4b replies, recorded, replayed offline.

`fixtures/gemma/<mode>/<key>.json` is what `manage.py eval_extraction --llm
--dump DIR` wrote against Ollama on 2026-11-16: every chat call for one
sample resume, its raw HTTP body and its timing. `thinking/` was recorded
with the model's reasoning on, `no_thinking/` with `reasoning_effort: none`
(the demo setting). Each test feeds the recorded replies back through
`FakeLLMClient`, so no test here needs Ollama.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from matching import llm
from matching.samples import SAMPLE_RESUMES
from matching.testing import FakeLLMClient, resume_reply

FIXTURES = Path(__file__).parent / "fixtures" / "gemma"
SAMPLES = {sample.key: sample for sample in SAMPLE_RESUMES}
TODAY = datetime.date(2026, 11, 16)


def recorded(mode: str, key: str) -> dict:
    return json.loads((FIXTURES / mode / f"{key}.json").read_text())


def replay(mode: str, key: str, text: str | None = None) -> llm.ResumeFacts:
    """The recorded replies for one sample, read through the real parser."""
    record = recorded(mode, key)
    client = FakeLLMClient([call["content"] for call in record["calls"]], model=record["model"])
    return llm.parse_resume_facts(text if text is not None else SAMPLES[key].text, client=client, today=TODAY)


class TestStatedFactsMustBeOnThePage:
    """G3a: a DOB, age, phone or email the resume does not write is dropped."""

    def test_the_recorded_hallucinated_dob_is_dropped(self):
        """
        With thinking off, gemma4 read the roll number 220200901 as a DOB.

        `backend_engineer_dob.json` is reconstructed (its `note` says how):
        that reply was measured but not saved.
        """
        record = recorded("no_thinking", "backend_engineer_dob")
        assert json.loads(record["calls"][0]["content"])["date_of_birth"] == "2002-09-01"

        facts = replay("no_thinking", "backend_engineer_dob", SAMPLES["backend_engineer"].text)

        assert facts.data["date_of_birth"] is None

    def test_the_thinking_reply_stays_clean(self):
        facts = replay("thinking", "backend_engineer")

        assert facts.data["date_of_birth"] is None
        assert facts.data["age"] is None
        assert facts.data["emails"] == ["aarav.mehta@college.edu"]

    def test_a_stated_dob_and_age_survive(self):
        """civil_fresher writes "Age: 21 | Date of Birth: 14/05/2005"."""
        reply = resume_reply(age=21, date_of_birth="2005-05-14", phones=["+91 98220 11223"],
                             emails=["Rohan.Patil@college.edu"])

        facts = llm.parse_resume_facts(SAMPLES["civil_fresher"].text, client=FakeLLMClient([reply]), today=TODAY)

        assert facts.data["date_of_birth"] == "2005-05-14"
        assert facts.data["age"] == 21
        assert facts.data["phones"] == ["+91 98220 11223"]
        assert facts.data["emails"] == ["Rohan.Patil@college.edu"]

    def test_an_invented_age_phone_and_email_are_dropped(self):
        reply = resume_reply(age=24, phones=["98765 43210", "+91 98220 11223"],
                             emails=["rohan@gmail.com", "rohan.patil@college.edu"])

        facts = llm.parse_resume_facts(SAMPLES["civil_fresher"].text, client=FakeLLMClient([reply]), today=TODAY)

        assert facts.data["age"] is None
        assert facts.data["phones"] == ["+91 98220 11223"]
        assert facts.data["emails"] == ["rohan.patil@college.edu"]

    @pytest.mark.parametrize(
        "written",
        [
            "DOB: 14/05/2005", "DOB: 14-5-2005", "DOB: 14.05.2005", "DOB: 2005-05-14",
            "Born 14 May 2005", "Born 14th May, 2005", "Born May 14, 2005", "DOB 14-May-2005",
            "DOB: 05/14/2005",
        ],
    )
    def test_a_dob_is_matched_in_the_usual_formats(self, written):
        assert llm.drop_unstated_facts({"date_of_birth": "2005-05-14"}, written)["date_of_birth"] == "2005-05-14"

    @pytest.mark.parametrize("written", ["Roll no 220200901", "Class of 2002, joined Sep 2001", "DOB: 2002"])
    def test_digits_that_merely_contain_the_date_do_not_count(self, written):
        assert llm.drop_unstated_facts({"date_of_birth": "2002-09-01"}, written)["date_of_birth"] is None

    @pytest.mark.parametrize(
        "phone, written, kept",
        [
            ("9822011223", "Phone: +91-98220-11223", True),
            ("+91 98220 11223", "Mobile 9822011223", True),
            ("(982) 201-1223", "call 982 201 1223", True),
            ("9822011223", "Roll 98220112230", False),
            ("12345", "12345", False),
        ],
    )
    def test_a_phone_is_compared_by_its_digits(self, phone, written, kept):
        assert llm.drop_unstated_facts({"phones": [phone]}, written)["phones"] == ([phone] if kept else [])

    def test_an_age_must_be_written_as_a_number_of_its_own(self):
        assert llm.drop_unstated_facts({"age": 21}, "Age: 21")["age"] == 21
        assert llm.drop_unstated_facts({"age": 21}, "Batch of 2021, CGPA 8.21")["age"] is None
