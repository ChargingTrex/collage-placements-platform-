"""
Fill the career outcomes dashboard (R3) with believable demo students.

Creates roster rows, student accounts and profiles with a career path across
all eight schools and two graduating batches, so `/admin/outcomes` has
something to show. The mix per school is invented but plausible: computing
and technology lean to placements, law to competitive exams and higher
studies, business to family business and entrepreneurship.

    python manage.py seed_outcomes_demo                 # batches 2026 and 2027
    python manage.py seed_outcomes_demo --batch 2026    # one batch only
    python manage.py seed_outcomes_demo --reset         # remove the demo students

Demo data only, and easy to remove:

- every PRN has `99` as its third and fourth digits, and every email starts
  `outcomes.demo.`; `--reset` deletes only rows matching both
- the accounts have no usable password, so nobody can sign in as them
- it is deterministic and idempotent: a re-run updates the same students

Run `seed_demo` first if you also want the admin login that views the page.
"""

from __future__ import annotations

import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from profiles.models import CareerPath, StudentProfile
from roster.models import Student
from roster.reference import PROGRAMMES, SCHOOLS

EMAIL_PREFIX = "outcomes.demo."
EMAIL_DOMAIN = "college.edu"
DEFAULT_BATCHES = (2026, 2027)

#: Students per school, per batch.
SCHOOL_SIZES = {
    "computing_data_science": 30,
    "technology": 22,
    "artificial_intelligence": 16,
    "business": 18,
    "law": 14,
    "arts_sciences": 16,
    "media": 10,
    "allied_health": 12,
}

#: Relative weights per career path, per school (final-year batch). The
#: later batch shifts weight to "undecided": students choose late.
PATH_WEIGHTS = {
    #                         plc  bus  hst  ent  res  fam  exm  oth  und
    "computing_data_science": (55, 2, 15, 5, 3, 2, 3, 3, 12),
    "technology":             (50, 3, 18, 4, 3, 4, 5, 3, 10),
    "artificial_intelligence": (48, 2, 18, 8, 6, 1, 2, 3, 12),
    "business":               (25, 10, 15, 15, 1, 18, 3, 3, 10),
    "law":                    (15, 1, 25, 2, 4, 3, 30, 8, 12),
    "arts_sciences":          (15, 2, 40, 3, 15, 2, 8, 5, 10),
    "media":                  (35, 5, 12, 12, 2, 4, 3, 15, 12),
    "allied_health":          (30, 2, 35, 3, 10, 1, 6, 3, 10),
}
PATH_ORDER = (
    CareerPath.PLACEMENT,
    CareerPath.BUSINESS,
    CareerPath.HIGHER_STUDIES,
    CareerPath.ENTREPRENEURSHIP,
    CareerPath.RESEARCH,
    CareerPath.FAMILY_BUSINESS,
    CareerPath.COMPETITIVE_EXAMS,
    CareerPath.OTHER,
    CareerPath.UNDECIDED,
)
#: Extra undecided weight per year a batch still has before it graduates.
#: The cohort closest to graduating has had the most time to decide, so the
#: weight is counted from the earliest batch seeded, not the latest.
UNDECIDED_PER_YEAR_OUT = 25

FIRST_NAMES = (
    "Aarav", "Aditi", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Kabir",
    "Meera", "Neha", "Nikhil", "Priya", "Rahul", "Riya", "Rohan", "Saanvi",
    "Sana", "Siddharth", "Tanvi", "Varun", "Vihaan", "Zara", "Aditya", "Isha",
)
LAST_NAMES = (
    "Banerjee", "Deshmukh", "Gupta", "Iyer", "Joshi", "Kulkarni", "Menon",
    "Mehta", "Nair", "Patel", "Qureshi", "Rao", "Reddy", "Shah", "Sharma",
    "Singh", "Verma", "Pillai", "Chatterjee", "Kapoor",
)

#: For a few non-placement students: the plan is X, but they will still sit
#: placements as a fallback.
ALSO_ATTENDING_SHARE = 0.3
VERIFIED_SHARE = 0.6


def demo_prn(batch: int, school_index: int, n: int) -> str:
    """Nine digits: batch year, `99` (the demo marker), school, serial."""
    return f"{batch % 100:02d}99{school_index}{n:04d}"


def is_demo(student: Student) -> bool:
    return student.prn[2:4] == "99" and student.email.startswith(EMAIL_PREFIX)


def department_for(programme: str) -> str:
    """'B.Tech Computer Science (AI)' -> 'Computer Science (AI)'."""
    head, _, rest = programme.partition(" ")
    return rest or head


class Command(BaseCommand):
    help = "Create demo students with career paths for the outcomes dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch", type=int, action="append", dest="batches",
            help=f"Graduating year to seed; repeat for several (default: {', '.join(map(str, DEFAULT_BATCHES))}).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete the demo students (and only them), then stop.",
        )

    @transaction.atomic
    def handle(self, *args, batches=None, reset=False, **options):
        if reset:
            removed = self._reset()
            self.stdout.write(self.style.WARNING(f"Removed {removed} demo students."))
            return

        batches = sorted(set(batches or DEFAULT_BATCHES))
        earliest = min(batches)
        created = updated = 0
        for batch in batches:
            for school_index, school in enumerate(SCHOOLS):
                # Seeded per batch and school, so adding a batch never
                # reshuffles the students already there.
                rng = random.Random(f"outcomes-demo:{batch}:{school}")
                weights = list(PATH_WEIGHTS[school])
                weights[-1] += UNDECIDED_PER_YEAR_OUT * (batch - earliest)
                programmes = [p for p in PROGRAMMES[school] if not p.startswith("Ph.D")] or PROGRAMMES[school]
                for n in range(1, SCHOOL_SIZES[school] + 1):
                    path = rng.choices(PATH_ORDER, weights=weights)[0]
                    was_created = self._upsert(
                        prn=demo_prn(batch, school_index, n),
                        batch=batch,
                        school=school,
                        programme=rng.choice(programmes),
                        name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                        cgpa=Decimal(str(round(rng.uniform(6.2, 9.6), 2))),
                        path=path,
                        attending=(
                            path not in (CareerPath.PLACEMENT, CareerPath.UNDECIDED)
                            and rng.random() < ALSO_ATTENDING_SHARE
                        ),
                        verified=rng.random() < VERIFIED_SHARE,
                    )
                    created += was_created
                    updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f"Outcomes demo: {created} students created, {updated} updated, "
            f"batches {', '.join(map(str, batches))}."
        ))
        self.stdout.write("View it at /admin/outcomes (sign in as the seed_demo admin).")

    def _upsert(self, *, prn, batch, school, programme, name, cgpa, path, attending, verified) -> bool:
        email = f"{EMAIL_PREFIX}{prn}@{EMAIL_DOMAIN}"
        student, created = Student.objects.update_or_create(
            prn=prn,
            defaults={
                "email": email,
                "full_name": name,
                "department": department_for(programme),
                "batch": batch,
                "cgpa": cgpa,
                "school": school,
                "programme": programme,
                "year_of_study": max(1, 4 - (batch - DEFAULT_BATCHES[0])),
                "is_placement_eligible": True,
            },
        )

        user = User.objects.filter(prn=prn).first()
        if user is None:
            # No password: these accounts exist only to be counted.
            user = User.objects.create_user(email=email, password=None, prn=prn, full_name=name)
            user.mark_verified()

        profile, _ = StudentProfile.objects.get_or_create(user=user, student=student)
        profile.career_path = path
        profile.also_attending_placements = attending
        profile.is_verified = verified
        profile.verified_at = timezone.now() if verified else None
        profile.save(update_fields=[
            "career_path", "also_attending_placements", "is_verified", "verified_at", "updated_at",
        ])
        return created

    def _reset(self) -> int:
        demo = [s for s in Student.objects.filter(email__startswith=EMAIL_PREFIX) if is_demo(s)]
        prns = [s.prn for s in demo]
        User.objects.filter(role=Role.STUDENT, prn__in=prns).delete()
        Student.objects.filter(prn__in=prns).delete()
        return len(prns)
