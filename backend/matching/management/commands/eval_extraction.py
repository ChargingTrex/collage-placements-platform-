"""
Score the extractors against the hand-checked sample resumes.

    python manage.py eval_extraction          regex, and the LLM when it is enabled
    python manage.py eval_extraction --llm    the same; says so when the LLM is off

Per field, how many samples each reader got right: experience within 0.1
years, the exact set of education levels, and the age and CGPA on the
samples that state one. Every miss is listed with what was expected and
what was read. Always exits 0: this measures, it does not gate.

The `llm` column is the model's own reading, not the engine's blend:
experience is what its dated entries add up to, so a resume that only
states "3 years of experience" is a miss for the model and a hit for regex.
That difference is the point of measuring both.
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand

from matching import llm
from matching.engine import MatchingEngine
from matching.samples import SAMPLE_RESUMES, SampleResume

FIELDS = ("experience", "education", "age", "cgpa")
EXPERIENCE_TOLERANCE = 0.1
CGPA_TOLERANCE = 0.01


def regex_reading(text: str, today: datetime.date) -> dict:
    facts = MatchingEngine.regex_facts(text, today)
    return {
        "experience": facts["experience_years"],
        "education": set(facts["education_levels"]),
        "age": facts["age"],
        "cgpa": facts["cgpa"],
    }


def llm_reading(client):
    def read(text: str, today: datetime.date) -> dict | None:
        try:
            facts = llm.parse_resume_facts(text, client=client, today=today)
        except llm.LLMUnavailable:
            return None
        return {
            "experience": facts.experience_years,
            "education": set(facts.education_levels),
            "age": facts.data.get("age"),
            "cgpa": facts.data.get("cgpa"),
        }

    return read


def expected(sample: SampleResume, field: str):
    """The hand-checked value, or None when this sample does not score the field."""
    return {
        "experience": sample.expected_experience_years,
        "education": set(sample.expected_education_levels),
        "age": sample.expected_age,
        "cgpa": sample.expected_cgpa,
    }[field]


def is_hit(field: str, want, got) -> bool:
    if got is None:
        return False
    if field == "experience":
        return round(abs(float(got) - want), 6) <= EXPERIENCE_TOLERANCE
    if field == "cgpa":
        return round(abs(float(got) - want), 6) <= CGPA_TOLERANCE
    return got == want


def shown(value) -> str:
    if isinstance(value, set):
        return "{" + ", ".join(sorted(value)) + "}" if value else "{}"
    return "nothing" if value is None else f"{value:g}" if isinstance(value, float) else str(value)


class Command(BaseCommand):
    help = "Per-field accuracy of regex (and the LLM, when enabled) on the hand-checked sample resumes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--llm", action="store_true",
            help="Score the LLM too. It already runs whenever LLM_ENABLED is true; this says so when it is not.",
        )

    def handle(self, *args, **options):
        today = datetime.date.today()
        readers = {"regex": regex_reading}
        if llm.llm_enabled():
            readers["llm"] = llm_reading(llm.get_client())
        elif options["llm"]:
            self.stdout.write("The LLM is disabled (LLM_ENABLED is false); scoring regex only.\n")

        hits = {(reader, field): 0 for reader in readers for field in FIELDS}
        scored = dict.fromkeys(FIELDS, 0)
        misses: list[str] = []
        for sample in SAMPLE_RESUMES:
            readings = {name: read(sample.text, today) for name, read in readers.items()}
            for field in FIELDS:
                want = expected(sample, field)
                if want is None:
                    continue
                scored[field] += 1
                for name, reading in readings.items():
                    got = None if reading is None else reading[field]
                    if is_hit(field, want, got):
                        hits[(name, field)] += 1
                    else:
                        read_as = "unavailable" if reading is None else shown(got)
                        misses.append(
                            f"  {name:<6} {field:<11} {sample.key}  expected {shown(want)}, got {read_as}"
                        )

        self.stdout.write(f"Extraction accuracy on {len(SAMPLE_RESUMES)} hand-checked sample resumes\n\n")
        self.stdout.write(f"{'field':<12}{'scored':>7}" + "".join(f"  {name:>11}" for name in readers) + "\n")
        for field in FIELDS:
            cells = []
            for name in readers:
                count, total = hits[(name, field)], scored[field]
                percent = f"{round(100 * count / total)}%" if total else "-"
                cells.append(f"  {f'{count}/{total}':>6} {percent:>4}")
            self.stdout.write(f"{field:<12}{scored[field]:>7}" + "".join(cells) + "\n")

        if misses:
            self.stdout.write("\nMisses:\n" + "\n".join(misses) + "\n")
        else:
            self.stdout.write("\nMisses: none\n")
