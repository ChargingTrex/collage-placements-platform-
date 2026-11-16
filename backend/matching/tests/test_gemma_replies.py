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
        """With thinking off, gemma4 read the roll number 220200901 as a DOB."""
        record = recorded("no_thinking", "backend_engineer")
        assert json.loads(record["calls"][0]["content"])["date_of_birth"] == "2002-09-01"

        facts = replay("no_thinking", "backend_engineer")

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

    @pytest.mark.parametrize(
        "written",
        [
            "DOB: 01-09-02", "DOB: 01/09/02", "DOB: 1.9.02", "DOB 1-Sep-02", "Born 1st Sep '02",
            "DOB: 01 - 09 - 2002", "DOB: 01 / 09 / 2002", "Born 1 Sept. 2002", "Born Sept. 1, 2002",
            "DOB: 09-01-02",
        ],
    )
    def test_a_dob_with_a_two_digit_year_or_spaced_separators_is_matched(self, written):
        """QA-2: these real ways of writing 1 September 2002 were dropped."""
        assert llm.drop_unstated_facts({"date_of_birth": "2002-09-01"}, written)["date_of_birth"] == "2002-09-01"

    @pytest.mark.parametrize("written, iso", [("DOB: 14/05/85", "1985-05-14"), ("DOB: 14-May-30", "2030-05-14"),
                                              ("DOB: 14-May-31", "1931-05-14")])
    def test_a_two_digit_year_pivots_at_30(self, written, iso):
        assert llm.drop_unstated_facts({"date_of_birth": iso}, written)["date_of_birth"] == iso

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

    @pytest.mark.parametrize(
        "written",
        [
            "Aarav\n9876543210\n2019-2023 BTech",
            "Phone: 9876543210 2021 - 2025 B.Tech",
            "9876543210 8.5",
            "9876543210 9123456780",
            "9123456780 9876543210",
            "Mobile: (+91) 98765 43210",
            "Tel 0091-9876543210",
            "call 09876543210",
        ],
    )
    def test_a_phone_next_to_another_number_is_still_found(self, written):
        """QA-2: the old candidate regex ran across spaces into the next number."""
        assert llm.drop_unstated_facts({"phones": ["9876543210"]}, written)["phones"] == ["9876543210"]

    @pytest.mark.parametrize(
        "written, kept",
        [
            ("+919876543210", True), ("919876543210", True), ("0919876543210", True),
            ("00919876543210", True), ("+91 9876543210", True),
            ("PRN 12349876543210", False), ("Roll no. 5559876543210", False),
            ("ID 449876543210", False), ("+44 9876543210", False),
        ],
    )
    def test_only_an_indian_or_trunk_prefix_may_stand_before_the_number(self, written, kept):
        """QA-2: a long PRN ending in the same ten digits must not ground a phone."""
        assert llm.drop_unstated_facts({"phones": ["9876543210"]}, written)["phones"] == (
            ["9876543210"] if kept else []
        )

    @pytest.mark.parametrize(
        "phone, written, kept",
        [
            ("+91 98765 43210", "Mobile 09876543210", True),
            ("+44 20 7946 0958", "Tel +44 20 7946 0958", True),
            ("+44 20 7946 0958", "Tel 2079460958", False),
        ],
    )
    def test_the_models_own_prefix_must_be_one_of_them_too(self, phone, written, kept):
        assert llm.drop_unstated_facts({"phones": [phone]}, written)["phones"] == ([phone] if kept else [])

    @pytest.mark.parametrize(
        "email, written, kept",
        [
            ("john@gmail.com", "Email: bigjohn@gmail.com", False),
            ("a@b.com", "aa@b.com.au", False),
            ("a@b.com", "x.a@b.com", False),
            ("a@b.com", "a@b.com-mail.net", False),
            ("john@gmail.com", "Email: John@Gmail.com.", True),
            ("john@gmail.com", "<john@gmail.com>", True),
            ("mailto:john@gmail.com", "john@gmail.com | 98765", True),
        ],
    )
    def test_an_email_must_be_written_whole(self, email, written, kept):
        """QA-2: a substring check kept john@gmail.com for bigjohn@gmail.com."""
        assert llm.drop_unstated_facts({"emails": [email]}, written)["emails"] == ([email] if kept else [])

    def test_an_age_must_be_written_as_a_number_of_its_own(self):
        assert llm.drop_unstated_facts({"age": 21}, "Age: 21")["age"] == 21
        assert llm.drop_unstated_facts({"age": 21}, "Batch of 2021, CGPA 8.21")["age"] is None

    @pytest.mark.parametrize(
        "written, kept",
        [
            ("Age: 21", True), ("Aged 21, from Pune", True), ("21 years old", True), ("21 yrs old", True),
            ("AGE - 21", True),
            ("Team of 21 engineers", False), ("Ranked 21 in the state", False),
            ("Age: 23. Led a team of 21", False),
        ],
    )
    def test_an_age_needs_an_age_cue_beside_it(self, written, kept):
        """QA-2 (optional): a bare 21 anywhere on the page grounded age 21."""
        assert llm.drop_unstated_facts({"age": 21}, written)["age"] == (21 if kept else None)

    @pytest.mark.parametrize(
        "written, kept",
        [
            ("Date of Birth: 01/09/2002", True), ("D.O.B. 01-09-2002", True),
            ("Born on the 1st of September, 2002 in Pune", True),
            ("Intern, Loadstar, 01/09/2002 - 30/11/2002", False),
            ("Joined 1 Sep 2002", False),
        ],
    )
    def test_a_dob_needs_a_birth_label_before_it(self, written, kept):
        """QA-2 (optional): an internship's start date grounded a DOB."""
        assert llm.drop_unstated_facts({"date_of_birth": "2002-09-01"}, written)["date_of_birth"] == (
            "2002-09-01" if kept else None
        )


NO_THINKING_KEYS = sorted(path.stem for path in (FIXTURES / "no_thinking").glob("*.json"))


class TestTheEngineNeverReadsWorseThanRegex:
    """
    G3b: on the recorded thinking-off replies, the engine's blend (what the
    portal stores) scores at least as well as regex on every field.

    The model alone scored experience 4/10 in that run: six samples give
    experience only as a duration ("3 years"), and the model's reading
    counts dated entries alone. The blend falls back to regex for those.
    """

    def test_every_sample_was_recorded(self):
        assert NO_THINKING_KEYS == sorted(SAMPLES)

    def test_per_field_hits(self):
        from matching.management.commands.eval_extraction import (
            FIELDS, engine_reading, expected, is_hit, llm_reading, regex_reading,
        )

        hits = {(column, field): 0 for column in ("regex", "engine") for field in FIELDS}
        for key in NO_THINKING_KEYS:
            sample = SAMPLES[key]
            client = FakeLLMClient([call["content"] for call in recorded("no_thinking", key)["calls"]])
            model = llm_reading(client)(sample.text, TODAY)
            assert model is not None, f"{key}: the recorded reply did not parse"
            regex = regex_reading(sample.text, TODAY)
            readings = {"regex": regex, "engine": engine_reading(regex, model)}
            for field in FIELDS:
                want = expected(sample, field)
                if want is None:
                    continue
                for column, reading in readings.items():
                    hits[(column, field)] += is_hit(field, want, reading[field])

        for field in FIELDS:
            assert hits[("engine", field)] >= hits[("regex", field)], field
