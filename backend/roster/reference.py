"""
Fixed lists of schools and programmes, and helpers to look them up.

Source: REQUIREMENTS-ADDENDUM.md, "Reference: schools and degrees" (taken from
the university website; confirm against the registrar's list). To add or
rename a school or programme, edit the two dicts below -- nothing else.
"""

from __future__ import annotations

import re

SCHOOLS: dict[str, str] = {
    "arts_sciences": "School of Arts and Sciences",
    "computing_data_science": "School of Computing and Data Science",
    "law": "School of Law",
    "artificial_intelligence": "School of Artificial Intelligence",
    "media": "School of Media",
    "technology": "School of Technology",
    "business": "School of Business",
    "allied_health": "School of Allied Health Sciences",
}

PROGRAMMES: dict[str, list[str]] = {
    "arts_sciences": [
        "B.Sc. (Hons.) Neuroscience",
        "B.Sc. (Hons.) Biological Sciences",
        "B.Sc. (Hons.) Psychology",
        "B.A. (Hons.) Economics",
        "B.A. (Hons.) Politics, Philosophy and Economics (PPE)",
        "Ph.D.",
    ],
    "computing_data_science": [
        "B.Tech Computer Science",
        "B.Tech Data Science",
        "B.Tech Computer Science (AI)",
        "B.Tech Computing and Data Science",
        "B.Tech Computer Science (Cyber Security)",
        "B.Tech Computer Science (Full Stack)",
        "B.Tech Computer Science (AI and ML)",
        "B.Tech Computer Science (AI & Data Science), jointly with L&T",
        "B.Tech Computer Science, jointly with Xebia",
        "MCA",
        "Ph.D.",
    ],
    "law": [
        "B.A. LL.B. (Hons.)",
        "BBA LL.B. (Hons.)",
        "LL.M. in Regulation and Governance",
        "Daksha Fellowship",
        "Ph.D.",
    ],
    "artificial_intelligence": [
        "B.Tech Artificial Intelligence",
        "BCA (Hons.)",
        "Ph.D. in Artificial Intelligence",
    ],
    "media": [
        "B.A. (Hons.) Media Studies",
        "B.Sc. (Hons.) Visual Communication",
        "B.Sc. (Hons.) Film and Television",
        "Ph.D.",
    ],
    "technology": [
        "B.Tech Biotechnology",
        "B.Tech Environmental Engineering",
        "B.Tech Biomedical Engineering",
        "Ph.D.",
    ],
    "business": [
        "BBA (Hons.)",
        "BBA (Hons.) Business Intelligence & Data Analytics",
        "BBA (Hons.) Digital Marketing",
        "B.Com. (Hons.) with ACCA",
        "MBA",
        "MBA Artificial Intelligence and Business Analytics",
        "MBA Operations and Project Management",
        "Ph.D.",
    ],
    "allied_health": [
        "B.Sc. Operation Theatre & Anaesthesia Technology",
        "B.Sc. Dialysis Technology",
        "B.Sc. Physician Assistant",
        "B.Sc. Medical Laboratory Technology",
        "B.Sc. Respiratory Technology",
        "B.Sc. Emergency Medical Technology",
        "B.Sc. Critical Care Technology",
        "B.Sc. Cardiovascular Technology",
        "Bachelor of Optometry",
        "Bachelor of Physiotherapy",
        "Bachelor of Occupational Therapy",
        "Bachelor in Radiology",
        "M.Sc. Clinical Embryology",
        "Diploma in Art Counselling",
    ],
}


def normalise_code(text: str) -> str:
    """Lower-case and drop everything but letters and digits, so "B.Tech" == "btech"."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


# Lookup tables built once at import. If you edit the dicts above at runtime,
# these will not follow; restart instead.
_SCHOOL_LOOKUP: dict[str, str] = {}
for _key, _name in SCHOOLS.items():
    _SCHOOL_LOOKUP[normalise_code(_key)] = _key
    _SCHOOL_LOOKUP[normalise_code(_name)] = _key

_PROGRAMME_SCHOOLS: dict[str, set[str]] = {}
for _key, _names in PROGRAMMES.items():
    for _name in _names:
        _PROGRAMME_SCHOOLS.setdefault(normalise_code(_name), set()).add(_key)


def school_for_programme(name: str) -> str | None:
    """School key for a programme, or None if unknown or shared (e.g. "Ph.D.")."""
    schools = _PROGRAMME_SCHOOLS.get(normalise_code(name), set())
    # A programme listed under several schools cannot tell us the school.
    return next(iter(schools)) if len(schools) == 1 else None


def is_known_school(name_or_key: str) -> bool:
    """True if the text is a school key or full school name (case/punctuation ignored)."""
    return normalise_code(name_or_key) in _SCHOOL_LOOKUP


def is_known_programme(name: str) -> bool:
    """True if the text is a listed programme name (case/punctuation ignored)."""
    return normalise_code(name) in _PROGRAMME_SCHOOLS


def prn_entry_year(prn: str) -> int | None:
    """Entry year from the first two digits of a nine-digit PRN; None otherwise.

    Helper only: nothing warns or rejects based on it.
    """
    value = (prn or "").strip()
    if not re.fullmatch(r"[0-9]{9}", value):
        return None
    return 2000 + int(value[:2])
