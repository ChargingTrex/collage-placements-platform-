"""Code list helpers: normalisation, school/programme lookups, PRN entry year."""

import pytest

from roster.reference import (
    PROGRAMMES,
    SCHOOLS,
    is_known_programme,
    is_known_school,
    normalise_code,
    prn_entry_year,
    school_for_programme,
)


def test_there_are_eight_schools_and_each_has_programmes():
    assert len(SCHOOLS) == 8
    assert set(PROGRAMMES) == set(SCHOOLS)
    assert all(PROGRAMMES[key] for key in SCHOOLS)


@pytest.mark.parametrize("text", ["B.Tech", "BTech", "b tech", " B-Tech "])
def test_normalise_code_ignores_case_and_punctuation(text):
    assert normalise_code(text) == "btech"


def test_programme_lookup_ignores_spelling_differences():
    assert is_known_programme("BTech Computer Science")
    assert school_for_programme("btech computer science") == "computing_data_science"


def test_unknown_programme():
    assert not is_known_programme("Department of Wizardry")
    assert school_for_programme("Department of Wizardry") is None


def test_shared_programme_has_no_single_school():
    assert is_known_programme("Ph.D.")
    assert school_for_programme("Ph.D.") is None


def test_school_by_key_or_name():
    assert is_known_school("law")
    assert is_known_school("school of law")
    assert is_known_school("School of Computing and Data Science")
    assert not is_known_school("School of Wizardry")


@pytest.mark.parametrize(
    "prn,year",
    [("220200901", 2022), ("230200924", 2023), ("22020090", None), ("22020090X", None), ("", None)],
)
def test_prn_entry_year(prn, year):
    assert prn_entry_year(prn) == year
