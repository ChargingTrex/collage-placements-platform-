"""
Preliminary verification: what the resume, the form and the roster disagree on.

`compare` is pure, so these tests build its inputs as plain dicts. The
baseline below agrees on everything and raises no flag; each test changes
one thing and looks for the one flag it should raise.
"""

import datetime

import pytest

from matching.verification import Flag, compare

TODAY = datetime.date(2026, 10, 19)

LOADSTAR = {
    "role": "Backend Developer Intern", "organization": "Loadstar Logistics", "kind": "internship",
    "start": "2024-01", "end": "2024-12", "is_current": False, "summary": "Built REST APIs.",
}


def roster(**overrides):
    return {
        "full_name": "Aarav Mehta",
        "email": "aarav.mehta@college.edu",
        "phone": "+91 98765 43210",
        "cgpa": 8.72,
        "batch": 2026,
        "programme": "B.Tech Computer Engineering",
        "department": "Computer Engineering",
        **overrides,
    }


def regex(**overrides):
    return {
        "experience_years": 1.0,
        "experience_source": "date_ranges",
        "education_levels": ["UG"],
        "age": None,
        "date_of_birth": None,
        "emails": ["aarav.mehta@college.edu"],
        "phones": ["9876543210"],
        "cgpa": None,
        **overrides,
    }


def facts(**overrides):
    return {
        "full_name": "Aarav Mehta",
        "emails": ["aarav.mehta@college.edu"],
        "phones": ["+91 98765 43210"],
        "age": None,
        "date_of_birth": None,
        "cgpa": None,
        "education": [
            {"degree": "B.Tech", "level": "UG", "field": "Computer Engineering",
             "institution": "Sai University", "start": "2022", "end": "2026", "cgpa": None},
        ],
        "experience": [LOADSTAR],
        "skills": ["Python", "Django"],
        "projects": [{"title": "Fleet Tracker", "tech_stack": ["Django"]}],
        "certifications": [],
        "links": [],
        "experience_months": 12,
        "experience_years": 1.0,
        "education_levels": ["UG"],
        "model": "fake-llama",
        **overrides,
    }


def form(**overrides):
    return {
        "experience_years": 1.0,
        "education_level": "UG",
        "experience": [
            {"role": "Backend Developer Intern", "organization": "Loadstar Logistics",
             "start_date": "2024-01-01", "end_date": "2024-12-31", "duration_months": 11},
        ],
        "projects": ["Fleet tracker"],
        "skills": ["Python", "Django"],
        **overrides,
    }


def run(**kwargs):
    arguments = {
        "facts": facts(), "regex_facts": regex(), "form": form(), "roster": roster(), "today": TODAY,
    }
    arguments.update(kwargs)
    return compare(**arguments)


def flags_for(flags, field):
    return [flag for flag in flags if flag.field == field]


def only(flags, field):
    [flag] = flags_for(flags, field)
    return flag


def test_a_resume_that_agrees_with_the_form_and_the_roster_raises_nothing():
    assert run() == []


def test_with_no_reading_at_all_there_is_nothing_to_compare():
    assert run(facts=None, regex_facts={}) == []


def test_a_flag_serialises_to_a_plain_dict():
    flag = Flag("cgpa", "warning", ["roster", "resume"], {"roster": 8.0, "resume": 9.0}, "Differs.")

    assert flag.as_dict() == {
        "field": "cgpa", "severity": "warning", "sources": ["roster", "resume"],
        "values": {"roster": 8.0, "resume": 9.0}, "message": "Differs.",
    }


class TestName:
    def test_a_different_name_is_a_warning(self):
        flag = only(run(facts=facts(full_name="Rahul Sharma")), "name")

        assert flag.severity == "warning"
        assert flag.sources == ["roster", "resume"]
        assert flag.values == {"roster": "Aarav Mehta", "resume": "Rahul Sharma"}

    @pytest.mark.parametrize("name", ["AARAV  MEHTA", "aarav mehta", "Mehta Aarav", "  Aarav   Mehta "])
    def test_case_spacing_and_order_are_not_differences(self, name):
        assert flags_for(run(facts=facts(full_name=name)), "name") == []

    @pytest.mark.parametrize("name", ["A. Mehta", "A Mehta", "Mehta A."])
    def test_initials_are_only_an_info(self, name):
        flag = only(run(facts=facts(full_name=name)), "name")

        assert flag.severity == "info"

    def test_with_the_llm_off_there_is_no_name_to_compare(self):
        assert flags_for(run(facts=None), "name") == []


class TestEmail:
    def test_the_college_email_missing_from_the_resume_is_an_info(self):
        flag = only(
            run(facts=facts(emails=["aarav@gmail.com"]), regex_facts=regex(emails=["aarav@gmail.com"])),
            "email",
        )

        assert flag.severity == "info"
        assert flag.values["roster"] == "aarav.mehta@college.edu"

    def test_the_college_email_in_any_case_is_found(self):
        flags = run(facts=facts(emails=["Aarav.Mehta@College.edu"]), regex_facts=regex(emails=[]))

        assert flags_for(flags, "email") == []


class TestPhone:
    def test_a_different_phone_on_the_resume_is_an_info(self):
        flags = run(facts=facts(phones=["9123456780"]), regex_facts=regex(phones=["9123456780"]))
        flag = only(flags, "phone")

        assert flag.severity == "info"
        assert flag.values == {"roster": "9876543210", "resume": ["9123456780"]}

    @pytest.mark.parametrize("written", ["09876543210", "+91-98765-43210", "98765 43210"])
    def test_the_same_number_written_differently_matches(self, written):
        assert flags_for(run(facts=facts(phones=[written]), regex_facts=regex(phones=[])), "phone") == []

    def test_no_phone_on_the_resume_raises_nothing(self):
        assert flags_for(run(facts=facts(phones=[]), regex_facts=regex(phones=[])), "phone") == []

    def test_no_phone_on_the_roster_raises_nothing(self):
        flags = run(roster=roster(phone=""), facts=facts(phones=["9123456780"]))

        assert flags_for(flags, "phone") == []


class TestCgpa:
    def test_a_resume_cgpa_above_the_roster_is_a_warning_naming_both(self):
        flag = only(run(facts=facts(cgpa=9.4)), "cgpa")

        assert flag.severity == "warning"
        assert flag.sources == ["roster", "resume"]
        assert flag.values == {"roster": 8.72, "resume": 9.4}
        assert "roster" in flag.message and "resume" in flag.message

    def test_a_gap_within_the_tolerance_raises_nothing(self):
        assert flags_for(run(facts=facts(cgpa=8.82)), "cgpa") == []

    def test_the_tolerance_comes_from_settings(self, settings):
        settings.VERIFICATION = {**settings.VERIFICATION, "CGPA_TOLERANCE": 1.0}

        assert flags_for(run(facts=facts(cgpa=9.4)), "cgpa") == []

    def test_the_three_way_comparison_names_each_disagreeing_pair(self):
        flags = flags_for(run(facts=facts(cgpa=9.4), transcript_cgpa=8.7), "cgpa")

        assert sorted(tuple(flag.sources) for flag in flags) == [
            ("roster", "resume"), ("transcript", "resume"),
        ]
        transcript = next(flag for flag in flags if "transcript" in flag.sources)
        assert transcript.values == {"transcript": 8.7, "resume": 9.4}

    def test_a_transcript_that_disagrees_with_the_roster_is_flagged_without_a_resume_value(self):
        flag = only(run(transcript_cgpa=7.9), "cgpa")

        assert flag.sources == ["roster", "transcript"]

    def test_with_the_llm_off_the_regex_cgpa_is_the_resume_value(self):
        flag = only(run(facts=None, regex_facts=regex(cgpa=9.5)), "cgpa")

        assert flag.values["resume"] == 9.5

    def test_the_models_cgpa_wins_over_the_regex_reading(self):
        flag = only(run(facts=facts(cgpa=9.4), regex_facts=regex(cgpa=8.7)), "cgpa")

        assert flag.values["resume"] == 9.4

    def test_no_roster_cgpa_and_no_transcript_leaves_nothing_to_compare(self):
        assert flags_for(run(roster=roster(cgpa=None), facts=facts(cgpa=9.4)), "cgpa") == []


class TestAge:
    @pytest.mark.parametrize("age", [15, 36, 40])
    def test_an_implausible_stated_age_is_a_warning(self, age):
        flag = only(run(facts=facts(age=age)), "age")

        assert flag.severity == "warning"
        assert flag.values == {"resume": age}

    @pytest.mark.parametrize("age", [16, 22, 35])
    def test_a_plausible_age_raises_nothing(self, age):
        assert flags_for(run(facts=facts(age=age)), "age") == []

    def test_a_stated_age_the_dob_contradicts_is_a_warning(self):
        flag = only(run(facts=facts(age=22, date_of_birth="2000-01-01")), "age")

        assert flag.severity == "warning"
        assert flag.values == {"stated_age": 22, "age_from_dob": 26}

    def test_a_stated_age_within_a_year_of_the_dob_raises_nothing(self):
        flags = run(facts=facts(age=22, date_of_birth="2004-03-12"))

        assert flags_for(flags, "age") == [] and flags_for(flags, "date_of_birth") == []

    def test_an_implausible_dob_derived_age_is_a_warning_when_no_age_is_stated(self):
        flag = only(run(facts=facts(date_of_birth="1985-06-01")), "age")

        assert flag.values == {"resume": 41}

    def test_a_dob_that_does_not_fit_the_graduating_batch_is_a_warning(self):
        flag = only(run(facts=facts(date_of_birth="2010-01-01")), "date_of_birth")

        assert flag.severity == "warning"
        assert flag.sources == ["roster", "resume"]
        assert flag.values == {"roster": 2026, "resume": "2010-01-01"}

    def test_a_dob_that_fits_the_batch_raises_nothing(self):
        assert flags_for(run(facts=facts(date_of_birth="2004-03-12")), "date_of_birth") == []

    def test_with_the_llm_off_the_regex_age_and_dob_are_checked(self):
        flags = run(facts=None, regex_facts=regex(age=22, date_of_birth="2000-01-01"))

        assert only(flags, "age").values == {"stated_age": 22, "age_from_dob": 26}


class TestEducation:
    def test_a_confirmed_level_the_resume_does_not_show_is_a_warning(self):
        flag = only(run(form=form(education_level="Masters")), "education_level")

        assert flag.severity == "warning"
        assert flag.values == {"form": "Masters", "resume": "UG"}

    def test_the_resumes_highest_level_is_compared(self):
        flags = run(facts=facts(education_levels=["Masters", "UG"]), form=form(education_level="Masters"))

        assert flags_for(flags, "education_level") == []

    def test_an_unconfirmed_level_raises_nothing(self):
        assert flags_for(run(form=form(education_level=None)), "education_level") == []


class TestExperience:
    def test_a_confirmed_value_far_from_the_resume_is_a_warning_naming_them(self):
        flags = flags_for(run(form=form(experience_years=3.0)), "experience_years")
        pairs = {tuple(flag.sources) for flag in flags}

        assert ("form", "resume") in pairs
        flag = next(flag for flag in flags if flag.sources == ["form", "resume"])
        assert flag.severity == "warning"
        assert flag.values == {"form": 3.0, "resume": 1.0}

    def test_form_entries_that_add_up_to_more_than_the_resume_are_a_warning(self):
        entries = [
            {"role": "Backend Developer Intern", "organization": "Loadstar Logistics",
             "start_date": "2023-01-01", "end_date": "2024-12-31", "duration_months": 23},
        ]
        flags = flags_for(run(form=form(experience=entries)), "experience_years")
        pairs = {tuple(flag.sources) for flag in flags}

        assert pairs == {("form", "form_entries"), ("resume", "form_entries")}

    def test_a_gap_of_six_months_or_less_raises_nothing(self):
        flags = run(form=form(experience_years=1.5, experience=[]))

        assert flags_for(flags, "experience_years") == []

    def test_with_the_llm_off_the_regex_total_is_the_resume_value(self):
        flags = run(facts=None, regex_facts=regex(experience_years=4.0))
        flag = next(f for f in flags_for(flags, "experience_years") if f.sources == ["form", "resume"])

        assert flag.values["resume"] == 4.0

    def test_a_stated_claim_the_dates_do_not_support_is_a_warning(self):
        """F2: the claim lost to the date total, and an admin should know."""
        flags = run(
            regex_facts=regex(experience_years=3.0, experience_source="claim"),
            facts=facts(experience_months=6, experience_years=0.5),
            form=form(experience_years=0.5, experience=[]),
        )
        [flag] = [f for f in flags if f.message.startswith("Stated experience not supported by dates")]

        assert flag.severity == "warning"
        assert flag.sources == ["regex", "llm"]
        assert flag.values == {"regex": 3.0, "llm": 0.5}

    def test_dates_that_support_the_claim_raise_nothing(self):
        flags = run(regex_facts=regex(experience_years=1.0, experience_source="claim"))

        assert not [f for f in flags if "not supported by dates" in f.message]

    def test_a_date_reading_is_not_a_claim(self):
        flags = run(
            regex_facts=regex(experience_years=3.0, experience_source="date_ranges"),
            facts=facts(experience_months=6, experience_years=0.5),
        )

        assert not [f for f in flags if "not supported by dates" in f.message]


class TestCounterparts:
    def test_a_form_entry_the_resume_does_not_mention_is_an_info(self):
        entries = form()["experience"] + [
            {"role": "Tutor", "organization": "Acme Coaching", "start_date": "2023-06-01",
             "end_date": "2023-08-31", "duration_months": 2},
        ]
        [flag] = [f for f in run(form=form(experience=entries)) if f.sources == ["form"]]

        assert flag.field == "experience"
        assert flag.severity == "info"
        assert "Acme Coaching" in flag.message

    def test_a_resume_entry_the_form_does_not_have_is_an_info(self):
        acme = {"role": "Freelance Web Developer", "organization": "Acme Corp", "kind": "freelance",
                "start": "2023-06", "end": "2023-11", "is_current": False, "summary": None}
        flags = run(facts=facts(experience=[LOADSTAR, acme]))
        [flag] = [f for f in flags_for(flags, "experience") if f.sources == ["resume"]]

        assert flag.severity == "info"
        assert "Acme Corp" in flag.message

    @pytest.mark.parametrize("organization", ["Loadstar Logistics Pvt. Ltd.", "LOADSTAR", "Loadstar Logistic"])
    def test_an_organisation_written_differently_is_still_a_counterpart(self, organization):
        entries = [{**form()["experience"][0], "organization": organization}]

        assert flags_for(run(form=form(experience=entries)), "experience") == []

    def test_without_an_organisation_the_role_is_matched(self):
        entries = [{**form()["experience"][0], "organization": ""}]

        assert flags_for(run(form=form(experience=entries)), "experience") == []

    def test_a_form_project_the_resume_does_not_mention_is_an_info(self):
        flags = run(form=form(projects=["Fleet tracker", "Chess engine"]))
        [flag] = flags_for(flags, "projects")

        assert flag.sources == ["form"]
        assert "Chess engine" in flag.message

    def test_a_resume_project_the_form_does_not_have_is_an_info(self):
        flags = run(facts=facts(projects=[{"title": "Fleet Tracker App", "tech_stack": []},
                                          {"title": "Hostel Mess Portal", "tech_stack": []}]))
        [flag] = flags_for(flags, "projects")

        assert flag.sources == ["resume"]
        assert "Hostel Mess Portal" in flag.message

    def test_with_the_llm_off_there_are_no_resume_entries_to_compare(self):
        assert [f for f in run(facts=None) if f.field in ("experience", "projects")] == []


class TestProgramme:
    def test_a_degree_in_another_field_is_an_info(self):
        education = [{"degree": "B.Tech", "level": "UG", "field": "Mechanical Engineering",
                      "institution": None, "start": None, "end": "2026", "cgpa": None}]
        flag = only(run(facts=facts(education=education)), "programme")

        assert flag.severity == "info"
        assert flag.sources == ["roster", "resume"]

    def test_any_degree_matching_the_programme_or_department_raises_nothing(self):
        education = [
            {"degree": "HSC", "level": None, "field": "Science", "institution": None,
             "start": None, "end": "2022", "cgpa": None},
            {"degree": "Bachelor of Technology", "level": "UG", "field": "Computer Engineering",
             "institution": None, "start": None, "end": "2026", "cgpa": None},
        ]

        assert flags_for(run(facts=facts(education=education)), "programme") == []


class TestRegexVersusLlm:
    def test_a_disagreement_is_an_info_that_the_extraction_needs_a_look(self):
        flags = run(regex_facts=regex(experience_years=3.0), form=form(experience_years=1.0))
        [flag] = [f for f in flags if f.sources == ["regex", "llm"]]

        assert flag.severity == "info"
        assert flag.field == "extraction.experience_years"
        assert flag.values == {"regex": 3.0, "llm": 1.0}
        assert "extraction" in flag.message.lower()

    def test_agreement_raises_nothing(self):
        assert not [f for f in run() if f.sources == ["regex", "llm"]]

    def test_with_the_llm_off_there_is_nothing_to_disagree_with(self):
        assert not [f for f in run(facts=None, regex_facts=regex(cgpa=9.0)) if "llm" in f.sources]
