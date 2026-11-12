"""
Preliminary verification: where the resume, the form and the roster disagree.

A resume is a claim, not proof, so nothing here blocks, rejects or changes
anything. `compare` returns flags for a placement admin to look at, and a
human decides (RESUME_INTELLIGENCE_PLAN.md §2). Flags are computed on
demand from the stored readings and the current form, so they never go
stale, and they reach admins only: never a student, never a company.

Severity says how much a disagreement means. A `warning` is a fact that
should match and does not (a CGPA above the roster's, an age no student
has). An `info` is worth a glance but has innocent explanations (a personal
email on the resume, an internship left off the form).

The resume's CGPA, age and DOB appear only inside a flag's values. None of
them is ever stored as a profile value or used for eligibility: the roster
stays authoritative.

Nothing here imports Django models, so it can be exercised standalone.
"""

from __future__ import annotations

import datetime
import difflib
import re
from dataclasses import asdict, dataclass, field
from itertools import combinations

from django.conf import settings

from matching.engine import _agreement
from matching.extractors import find_phones, highest_education_level

__all__ = ["Flag", "compare", "normalise_phones"]

INFO, WARNING = "info", "warning"

#: Below this, two names are different people rather than two spellings.
NAME_RATIO = 0.8
#: At or above this, two organisations or titles are the same entry.
COUNTERPART_RATIO = 0.75
PLAUSIBLE_AGE = (16, 35)
#: `batch` is the graduating year, so this is the age at graduation.
PLAUSIBLE_GRADUATING_AGE = (19, 30)
#: A stated age and the DOB's may differ by a birthday.
AGE_SLACK_YEARS = 1
EXPERIENCE_GAP_MONTHS = 6
DEFAULT_CGPA_TOLERANCE = 0.1


@dataclass
class Flag:
    field: str
    severity: str
    sources: list[str]
    #: Source name -> what that source says.
    values: dict = field(default_factory=dict)
    message: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def compare(
    facts: dict | None,
    regex_facts: dict | None,
    form: dict,
    roster: dict,
    transcript_cgpa: float | None = None,
    student_cgpa: float | None = None,
    today: datetime.date | None = None,
) -> list[Flag]:
    """
    Every disagreement between the resume's reading, the student's form and
    the roster, as flags.

    `facts` is the model's reading, or None when the LLM was off; then the
    regex reading stands in for it wherever it read the same thing.
    """
    regex = regex_facts or {}
    if not facts and not regex:
        return []
    today = today or datetime.date.today()
    resume = _Resume(facts, regex)

    flags: list[Flag] = []
    for check in (_name, _email, _phone, _cgpa, _age, _education, _experience,
                  _experience_counterparts, _project_counterparts, _programme, _extraction):
        flags.extend(
            check(
                resume,
                form,
                roster,
                transcript_cgpa=transcript_cgpa,
                student_cgpa=student_cgpa,
                today=today,
            )
        )
    return flags


class _Resume:
    """What the resume says, the model's reading first and regex behind it."""

    def __init__(self, facts: dict | None, regex: dict):
        self.facts = facts or None
        self.regex = regex
        llm = facts or {}

        self.full_name = llm.get("full_name")
        self.emails = _unique(e.strip().lower() for e in [*llm.get("emails", []), *regex.get("emails", [])] if e)
        self.phones = _unique(
            phone for raw in [*llm.get("phones", []), *regex.get("phones", [])] for phone in normalise_phones(raw)
        )
        self.cgpa = _first(llm.get("cgpa"), regex.get("cgpa"))
        self.age = _first(llm.get("age"), regex.get("age"))
        self.date_of_birth = _date(_first(llm.get("date_of_birth"), regex.get("date_of_birth")))
        levels = llm.get("education_levels") or regex.get("education_levels") or []
        self.education_level = highest_education_level(set(levels))
        # The engine's precedence: the model's date total when it found one.
        if facts and facts.get("experience_months", 0) > 0:
            self.experience_years = facts.get("experience_years")
        else:
            self.experience_years = regex.get("experience_years")
        self.experience = list(llm.get("experience") or [])
        self.projects = [p.get("title") for p in llm.get("projects") or [] if p.get("title")]
        self.education = list(llm.get("education") or [])


# --- the checks --------------------------------------------------------------------


def _name(resume, form, roster, **_):
    on_roster, on_resume = roster.get("full_name"), resume.full_name
    if not on_roster or not on_resume:
        return []
    a, b = _name_words(on_roster), _name_words(on_resume)
    if _ratio(" ".join(a), " ".join(b)) >= NAME_RATIO or _ratio(" ".join(sorted(a)), " ".join(sorted(b))) >= NAME_RATIO:
        return []
    values = {"roster": on_roster, "resume": on_resume}
    if _initials_match(a, b) or _initials_match(sorted(a), sorted(b)):
        return [Flag("name", INFO, ["roster", "resume"], values,
                     f"The resume abbreviates the roster name: '{on_resume}' for '{on_roster}'.")]
    return [Flag("name", WARNING, ["roster", "resume"], values,
                 f"The name on the resume, '{on_resume}', does not match the roster's '{on_roster}'.")]


def _email(resume, form, roster, **_):
    college = (roster.get("email") or "").strip().lower()
    if not college or college in resume.emails:
        return []
    return [Flag("email", INFO, ["roster", "resume"], {"roster": college, "resume": resume.emails},
                 "The college email is not on the resume.")]


def _phone(resume, form, roster, **_):
    on_roster = normalise_phones(roster.get("phone"))
    if not on_roster or not resume.phones or on_roster[0] in resume.phones:
        return []
    return [Flag("phone", INFO, ["roster", "resume"], {"roster": on_roster[0], "resume": resume.phones},
                 "The phone number on the resume is not the roster's.")]


def _cgpa(resume, form, roster, *, transcript_cgpa=None, student_cgpa=None, **_):
    tolerance = getattr(settings, "VERIFICATION", {}).get("CGPA_TOLERANCE", DEFAULT_CGPA_TOLERANCE)
    present = [
        (source, float(value))
        for source, value in (
            ("roster", roster.get("cgpa")),
            ("transcript", transcript_cgpa),
            ("resume", resume.cgpa),
            # What the student typed into the form. A fourth source to
            # disagree with, never the one that settles it.
            ("student", student_cgpa),
        )
        if value is not None
    ]
    flags = []
    for (first, a), (second, b) in combinations(present, 2):
        if round(abs(a - b), 4) > tolerance:
            flags.append(Flag(
                "cgpa", WARNING, [first, second], {first: a, second: b},
                f"The {first} CGPA ({a:g}) and the {second} CGPA ({b:g}) differ by more than {tolerance:g}.",
            ))
    return flags


def _age(resume, form, roster, *, today, **_):
    flags = []
    dob = resume.date_of_birth
    from_dob = _years_between(dob, today) if dob else None
    age = resume.age if resume.age is not None else from_dob

    low, high = PLAUSIBLE_AGE
    if age is not None and not low <= age <= high:
        flags.append(Flag("age", WARNING, ["resume"], {"resume": age},
                          f"An age of {age} is outside the plausible {low}-{high} for a student."))
    if resume.age is not None and from_dob is not None and abs(resume.age - from_dob) > AGE_SLACK_YEARS:
        flags.append(Flag("age", WARNING, ["resume"], {"stated_age": resume.age, "age_from_dob": from_dob},
                          f"The resume states an age of {resume.age}, but its date of birth makes it {from_dob}."))

    batch = roster.get("batch")
    if dob and batch:
        graduating = int(batch) - dob.year
        low, high = PLAUSIBLE_GRADUATING_AGE
        if not low <= graduating <= high:
            flags.append(Flag(
                "date_of_birth", WARNING, ["roster", "resume"], {"roster": int(batch), "resume": dob.isoformat()},
                f"Born in {dob.year} and graduating in {batch} means graduating at about {graduating}, "
                f"outside the plausible {low}-{high}.",
            ))
    return flags


def _education(resume, form, roster, **_):
    confirmed = form.get("education_level") or None
    if not confirmed or not resume.education_level or confirmed == resume.education_level:
        return []
    return [Flag("education_level", WARNING, ["form", "resume"],
                 {"form": confirmed, "resume": resume.education_level},
                 f"The confirmed education level is {confirmed}; the resume's highest is {resume.education_level}.")]


def _experience(resume, form, roster, **_):
    readings = [("form", form.get("experience_years")), ("resume", resume.experience_years)]
    entries = form.get("experience") or []
    if entries:
        months = sum(entry.get("duration_months") or 0 for entry in entries)
        readings.append(("form_entries", round(months / 12.0, 1)))
    present = [(source, float(value)) for source, value in readings if value is not None]

    flags = []
    for (first, a), (second, b) in combinations(present, 2):
        if round(abs(a - b) * 12, 4) > EXPERIENCE_GAP_MONTHS:
            flags.append(Flag(
                "experience_years", WARNING, [first, second], {first: a, second: b},
                f"{_LABELS[first]} ({a:g} years) and {_LABELS[second].lower()} ({b:g} years) "
                f"differ by more than {EXPERIENCE_GAP_MONTHS} months.",
            ))

    # The F2 trade-off: a stated "N years" lost to the dated entries, which is
    # right for the pre-fill, but a claim the dates do not back up is exactly
    # what an admin should see.
    regex = resume.regex
    if resume.facts is not None and regex.get("experience_source") == "claim":
        claimed = float(regex.get("experience_years") or 0)
        dated_months = resume.facts.get("experience_months", 0) or 0
        if round(claimed * 12 - dated_months, 4) > EXPERIENCE_GAP_MONTHS:
            dated = round(dated_months / 12.0, 1)
            flags.append(Flag(
                "experience_years", WARNING, ["regex", "llm"], {"regex": claimed, "llm": dated},
                f"Stated experience not supported by dates: the resume claims {claimed:g} years, "
                f"its dated entries add up to {dated:g}.",
            ))
    return flags


_LABELS = {"form": "The confirmed value", "resume": "The resume's total", "form_entries": "The form's entries"}


def _experience_counterparts(resume, form, roster, **_):
    if resume.facts is None:
        return []
    on_form = [entry for entry in form.get("experience") or [] if entry.get("role") or entry.get("organization")]
    on_resume = [entry for entry in resume.experience if entry.get("role") or entry.get("organization")]

    flags = []
    for entry in on_form:
        if not any(_same_entry(entry, other) for other in on_resume):
            flags.append(Flag("experience", INFO, ["form"], {"form": _describe(entry)},
                              f"'{_describe(entry)}' is on the form but not on the resume."))
    for entry in on_resume:
        if not any(_same_entry(entry, other) for other in on_form):
            flags.append(Flag("experience", INFO, ["resume"], {"resume": _describe(entry)},
                              f"'{_describe(entry)}' is on the resume but not on the form."))
    return flags


def _project_counterparts(resume, form, roster, **_):
    if resume.facts is None:
        return []
    on_form = [title for title in form.get("projects") or [] if title]
    flags = []
    for title in on_form:
        if not any(_similar(title, other) for other in resume.projects):
            flags.append(Flag("projects", INFO, ["form"], {"form": title},
                              f"The project '{title}' is on the form but not on the resume."))
    for title in resume.projects:
        if not any(_similar(title, other) for other in on_form):
            flags.append(Flag("projects", INFO, ["resume"], {"resume": title},
                              f"The project '{title}' is on the resume but not on the form."))
    return flags


def _programme(resume, form, roster, **_):
    on_roster = [value for value in (roster.get("programme"), roster.get("department")) if value]
    degrees = [
        " ".join(filter(None, [entry.get("degree"), entry.get("field")]))
        for entry in resume.education
    ]
    subjects = [_subject(degree) for degree in degrees if _subject(degree)]
    roster_subjects = [_subject(value) for value in on_roster if _subject(value)]
    if not subjects or not roster_subjects:
        return []
    if any(_similar(a, b, normalise=False) for a in subjects for b in roster_subjects):
        return []
    return [Flag("programme", INFO, ["roster", "resume"],
                 {"roster": " / ".join(on_roster), "resume": [d for d in degrees if d]},
                 "No degree on the resume matches the roster's programme or department.")]


def _extraction(resume, form, roster, **_):
    """Regex and the model read the same field differently: the extraction itself needs a look."""
    if resume.facts is None:
        return []
    try:
        agreement = _agreement(resume.regex, resume.facts)
    except (KeyError, TypeError):  # a reading stored before a field existed
        return []
    return [
        Flag(f"extraction.{name}", INFO, ["regex", "llm"], {"regex": entry["regex"], "llm": entry["llm"]},
             f"Regex and the model read {name.replace('_', ' ')} differently; the extraction itself needs a look.")
        for name, entry in agreement.items()
        if not entry["agree"]
    ]


# --- helpers -------------------------------------------------------------------------


def _unique(values) -> list:
    return list(dict.fromkeys(values))


def _first(*values):
    return next((value for value in values if value is not None), None)


def normalise_phones(raw) -> list[str]:
    """Ten digits, the way `find_phones` writes them; a number it cannot read, by its last ten digits."""
    if not raw:
        return []
    found = find_phones(str(raw))
    if found:
        return found
    digits = re.sub(r"\D", "", str(raw))
    return [digits[-10:]] if len(digits) >= 10 else []


def _date(value) -> datetime.date | None:
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _years_between(born: datetime.date, today: datetime.date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _name_words(name: str) -> list[str]:
    return re.sub(r"[^a-z]+", " ", name.lower()).split()


def _initials_match(a: list[str], b: list[str]) -> bool:
    """'a mehta' and 'aarav mehta': word for word the same, an initial standing for a name."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        if not ((len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))):
            return False
    return True


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


_ORG_NOISE = {
    "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "corp", "corporation", "co",
    "company", "the",
}


def _normalise(text: str | None) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return " ".join(word for word in words if word not in _ORG_NOISE)


def _similar(a: str | None, b: str | None, *, normalise: bool = True) -> bool:
    """The same organisation or title, written differently: 'Loadstar Logistics Pvt. Ltd.' is 'LOADSTAR'."""
    if normalise:
        a, b = _normalise(a), _normalise(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return _ratio(a, b) >= COUNTERPART_RATIO


def _same_entry(a: dict, b: dict) -> bool:
    """The organisation decides when both have one; otherwise the role."""
    if a.get("organization") and b.get("organization"):
        return _similar(a["organization"], b["organization"])
    return _similar(a.get("role"), b.get("role"))


def _describe(entry: dict) -> str:
    return " at ".join(filter(None, [entry.get("role"), entry.get("organization")]))


# Degree words carry no subject: "B.Tech in Computer Engineering" and the
# department "Computer Engineering" are the same programme.
_DEGREE_WORDS = {
    "b", "m", "be", "me", "tech", "btech", "mtech", "sc", "bsc", "msc", "ba", "ma", "bca", "mca",
    "bba", "mba", "com", "bcom", "mcom", "bachelor", "bachelors", "master", "masters", "degree",
    "of", "in", "and", "honours", "hons", "technology", "engineering", "science", "sciences",
    "studies", "programme", "program",
}


def _subject(text: str | None) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return " ".join(word for word in words if word not in _DEGREE_WORDS)
