"""`manage.py seed_outcomes_demo`: demo students for the outcomes dashboard."""

import pytest
from django.core.management import call_command

from accounts.models import User
from profiles.management.commands.seed_outcomes_demo import (
    DEFAULT_BATCHES,
    SCHOOL_SIZES,
    is_demo,
)
from profiles.models import StudentProfile
from profiles.views import build_outcomes
from roster.models import Student
from roster.reference import SCHOOLS

PER_BATCH = sum(SCHOOL_SIZES.values())

pytestmark = pytest.mark.django_db


def seed(*args):
    call_command("seed_outcomes_demo", *args, stdout=open("/dev/null", "w"))


def test_every_school_and_both_batches_are_filled():
    seed()

    everyone = build_outcomes(None)
    assert everyone["grand_total"] == PER_BATCH * len(DEFAULT_BATCHES)
    assert [row["school"] for row in everyone["rows"]] == list(SCHOOLS)
    for batch in DEFAULT_BATCHES:
        assert build_outcomes(batch)["grand_total"] == PER_BATCH


def test_the_columns_sum_to_the_cohort():
    seed()

    outcomes = build_outcomes(None)

    assert sum(outcomes["totals"].values()) == outcomes["grand_total"]
    for row in outcomes["rows"]:
        assert sum(row["counts"].values()) == row["total"]


def test_the_mix_is_plausible_not_uniform():
    seed()

    by_school = {row["school"]: row for row in build_outcomes(2026)["rows"]}
    computing, law = by_school["computing_data_science"], by_school["law"]

    assert computing["counts"]["placement"] > computing["total"] / 3
    assert law["counts"]["competitive_exams"] + law["counts"]["higher_studies"] > law["counts"]["placement"]
    assert 0 < build_outcomes(None)["verified"] < build_outcomes(None)["grand_total"]
    assert build_outcomes(None)["also_attending_placements"] > 0


def test_the_later_batch_is_less_decided():
    seed()

    final_year, next_year = (build_outcomes(b) for b in DEFAULT_BATCHES)

    assert next_year["totals"]["undecided"] > final_year["totals"]["undecided"]


def test_a_rerun_updates_rather_than_duplicates():
    seed()
    first = build_outcomes(None)

    seed()

    assert build_outcomes(None) == first
    assert Student.objects.count() == PER_BATCH * len(DEFAULT_BATCHES)


def test_one_batch_can_be_seeded_alone():
    seed("--batch", "2026")

    assert build_outcomes(None)["grand_total"] == PER_BATCH


def test_nobody_can_sign_in_as_a_demo_student():
    seed("--batch", "2026")

    users = User.objects.filter(prn__in=Student.objects.values("prn"))
    assert users.count() == PER_BATCH
    assert not any(user.has_usable_password() for user in users)


def test_every_demo_row_is_marked_and_valid():
    seed("--batch", "2026")

    for student in Student.objects.all():
        assert is_demo(student)
        student.full_clean()


def test_reset_removes_only_the_demo_students(roster_student):
    seed()

    call_command("seed_outcomes_demo", "--reset", stdout=open("/dev/null", "w"))

    assert list(Student.objects.values_list("prn", flat=True)) == [roster_student.prn]
    assert not StudentProfile.objects.exists()
    assert build_outcomes(None)["grand_total"] == 0
