"""
Score the extractors against the hand-checked sample resumes.

    python manage.py eval_extraction          regex, and the LLM when it is enabled
    python manage.py eval_extraction --llm    the same; says so when the LLM is off
    python manage.py eval_extraction --llm --dump DIR [--sample KEY ...]
                                              also write every raw model reply,
                                              with its timing, to DIR/<key>.json

Per field, how many samples each reader got right: experience within 0.1
years, the exact set of education levels, and the age and CGPA on the
samples that state one. Every miss is listed with what was expected and
what was read. Always exits 0: this measures, it does not gate.

The `llm` column is the model's own reading, not the engine's blend:
experience is what its dated entries add up to, so a resume that only
states "3 years of experience" is a miss for the model and a hit for regex.
That difference is the point of measuring both.

The `engine` column, shown beside `llm`, is what the portal actually stores
and shows: `MatchingEngine.analyse_resume`'s rule applied to the same two
readings (the model's dated total when it found one, else regex; its
education levels when it found any, else regex; regex for everything when
the model was unavailable). It costs no extra model call.
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

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
            "experience_months": facts.experience_months,
        }

    return read


def engine_reading(regex: dict, model: dict | None) -> dict:
    """The engine's blend of the two readings (`MatchingEngine.analyse_resume`)."""
    if model is None:
        return dict(regex)
    return {
        "experience": model["experience"] if model["experience_months"] > 0 else regex["experience"],
        "education": model["education"] or regex["education"],
        "age": model["age"] if model["age"] is not None else regex["age"],
        "cgpa": model["cgpa"] if model["cgpa"] is not None else regex["cgpa"],
    }


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


class ReplyRecorder:
    """
    Records every model call one sample makes: the raw HTTP body when the
    client is a real one (the reply, and Ollama's `reasoning` and token
    usage), the content string either way, and the seconds each call took.
    The recordings become regression fixtures and the timing evidence.
    """

    def __init__(self, client):
        self.calls: list[dict] = []
        self._client = client
        self._last_body = None
        post, chat = client._post, client.chat_json

        def recording_post(path, payload):
            body = post(path, payload)
            self._last_body = body
            return body

        def recording_chat(system, user):
            self._last_body = None
            started = time.monotonic()
            call = {"attempt": len(self.calls) + 1}
            try:
                content = chat(system, user)
            except llm.LLMUnavailable as exc:
                call.update(seconds=round(time.monotonic() - started, 1), error=str(exc), content=None)
                self.calls.append(call)
                raise
            call.update(seconds=round(time.monotonic() - started, 1), content=content)
            if self._last_body is not None:
                call["body"] = self._last_body
            self.calls.append(call)
            return content

        client._post, client.chat_json = recording_post, recording_chat

    def write(self, directory: Path, sample: SampleResume, seconds: float) -> None:
        record = {
            "key": sample.key,
            "model": self._client.model,
            "reasoning_effort": getattr(self._client, "reasoning_effort", ""),
            "total_seconds": round(seconds, 1),
            "calls": self.calls,
        }
        (directory / f"{sample.key}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
        self.calls = []


class Command(BaseCommand):
    help = "Per-field accuracy of regex (and the LLM, when enabled) on the hand-checked sample resumes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--llm", action="store_true",
            help="Score the LLM too. It already runs whenever LLM_ENABLED is true; this says so when it is not.",
        )
        parser.add_argument(
            "--dump", metavar="DIR",
            help="Write each sample's raw model replies and timings to DIR/<key>.json.",
        )
        parser.add_argument(
            "--sample", action="append", metavar="KEY",
            help="Only this sample (repeatable). Default: all of them.",
        )

    def handle(self, *args, **options):
        today = datetime.date.today()
        samples = SAMPLE_RESUMES
        if options.get("sample"):
            known = {sample.key for sample in SAMPLE_RESUMES}
            unknown = set(options["sample"]) - known
            if unknown:
                raise CommandError(f"Unknown sample(s): {', '.join(sorted(unknown))}")
            samples = tuple(s for s in SAMPLE_RESUMES if s.key in options["sample"])

        readers = {"regex": regex_reading}
        recorder = dump_dir = None
        if llm.llm_enabled():
            client = llm.get_client()
            if options.get("dump"):
                dump_dir = Path(options["dump"])
                dump_dir.mkdir(parents=True, exist_ok=True)
                recorder = ReplyRecorder(client)
            readers["llm"] = llm_reading(client)
        elif options["llm"]:
            self.stdout.write("The LLM is disabled (LLM_ENABLED is false); scoring regex only.\n")

        columns = [*readers, "engine"] if "llm" in readers else list(readers)
        hits = {(column, field): 0 for column in columns for field in FIELDS}
        scored = dict.fromkeys(FIELDS, 0)
        misses: list[str] = []
        for sample in samples:
            readings = {}
            for name, read in readers.items():
                started = time.monotonic()
                readings[name] = read(sample.text, today)
                if name == "llm" and recorder is not None:
                    recorder.write(dump_dir, sample, time.monotonic() - started)
                    self.stdout.write(f"  {sample.key}: {time.monotonic() - started:.1f}s\n")
                    self.stdout.flush()
            if "llm" in readers:
                readings["engine"] = engine_reading(readings["regex"], readings["llm"])
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

        self.stdout.write(f"Extraction accuracy on {len(samples)} hand-checked sample resumes\n\n")
        self.stdout.write(f"{'field':<12}{'scored':>7}" + "".join(f"  {name:>11}" for name in columns) + "\n")
        for field in FIELDS:
            cells = []
            for name in columns:
                count, total = hits[(name, field)], scored[field]
                percent = f"{round(100 * count / total)}%" if total else "-"
                cells.append(f"  {f'{count}/{total}':>6} {percent:>4}")
            self.stdout.write(f"{field:<12}{scored[field]:>7}" + "".join(cells) + "\n")

        if misses:
            self.stdout.write("\nMisses:\n" + "\n".join(misses) + "\n")
        else:
            self.stdout.write("\nMisses: none\n")
