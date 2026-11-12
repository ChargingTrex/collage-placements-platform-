"""
Seed the accounts and roster a demo or smoke-test run needs.

Idempotent: safe to run repeatedly against the same database.

It also seeds a few demo job descriptions as role categories, so a dev
database has categories to show (plan Task 7, cold start). With the LLM on
each JD is read and embedded like a recruiter's; with it off (the default)
the categories are made from the hand-written readings in DEMO_JOBS, the
facts the LLM would return. A role that already has a category is skipped.

    python manage.py seed_demo
    python manage.py seed_demo --reset          # wipe seeded data first
    python manage.py seed_demo --with-students  # also four populated students
"""

import datetime
import tempfile

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Company, Role, User
from matching import llm
from matching.categories import record_job_description
from matching.embeddings import get_embedder
from matching.models import RoleCategory, normalise_role
from matching.samples import SAMPLE_JOB_DESCRIPTION
from roster.importers import import_roster_csv
from roster.models import FlaggedSignup, Student

DEFAULT_ROSTER = Path(settings.BASE_DIR) / "fixtures" / "roster_sample.csv"

ADMINS = [
    ("placement.officer@college.edu", "Priya Kulkarni", "AdminPass!234"),
]
#: (organisation name, organisation email, recruiter login, recruiter name)
COMPANIES = [
    ("Acme Tech", "careers@acmetech.example",
     "recruiter@acmetech.example", "Priya Raman", "CompanyPass!234"),
    ("Nimbus Analytics", "careers@nimbusanalytics.example",
     "talent@nimbusanalytics.example", "Dev Menon", "CompanyPass!234"),
]

#: Demo JDs with the reading an LLM would give them (`JobFacts` data).
DEMO_JOBS = [
    (
        SAMPLE_JOB_DESCRIPTION,
        {"title": "Backend Engineer", "canonical_role": "Backend Engineer",
         "required_skills": ["Python", "Django", "Django REST Framework", "PostgreSQL", "Docker", "Git"],
         "nice_to_have": ["Celery", "AWS"], "min_experience_years": 2, "education_levels": ["UG"]},
    ),
    (
        "Data Analyst. Build dashboards and reports for the operations team. Required: strong SQL, "
        "Python with pandas, Excel, and a feel for statistics. Power BI or Tableau is a plus.",
        {"title": "Data Analyst", "canonical_role": "Data Analyst",
         "required_skills": ["SQL", "Python", "pandas", "Excel"], "nice_to_have": ["Power BI", "Tableau"],
         "min_experience_years": None, "education_levels": ["UG"]},
    ),
    (
        "Frontend Developer Intern. Build responsive pages in React and TypeScript from Figma designs. "
        "Required: React, TypeScript, HTML, CSS. Tailwind CSS experience is a plus.",
        {"title": "Frontend Developer Intern", "canonical_role": "Frontend Developer",
         "required_skills": ["React", "TypeScript", "HTML", "CSS"], "nice_to_have": ["Tailwind CSS"],
         "min_experience_years": None, "education_levels": []},
    ),
    (
        "Graduate Design Engineer. Model sheet metal and moulded parts for automotive assemblies. "
        "Required: SolidWorks, AutoCAD, GD&T. FEA with ANSYS is a plus. B.E. in Mechanical Engineering.",
        {"title": "Graduate Design Engineer", "canonical_role": "Mechanical Design Engineer",
         "required_skills": ["SolidWorks", "AutoCAD", "GD&T"], "nice_to_have": ["ANSYS"],
         "min_experience_years": None, "education_levels": ["UG"]},
    ),
]


STUDENT_PASSWORD = "StudentPass!234"

#: Four demo students from roster_sample.csv, one per visibility case a
#: company can run into. A reset database otherwise shows companies an empty
#: browse page and gives nobody a student login to try.
#: `shortlisted_by` is an index into COMPANIES.
#: School results per PRN: (class 10 %, board, year, class 12 %, board, year).
#: Marks only -- the marksheet files are the student's to upload, and seeding
#: a fake scan would put a document on record that nobody issued.
DEMO_SCHOOL_RESULTS = {
    "220200901": ("92.40", "cbse", 2020, "88.60", "cbse", 2022),
    "220200904": ("89.00", "state", 2020, "91.20", "state", 2022),
    "220200903": ("78.50", "icse", 2020, "74.80", "icse", 2022),
    "220200902": ("85.20", "cbse", 2020, "83.00", "cbse", 2022),
}

#: What the student says their CGPA is. Rohan's disagrees with the roster on
#: purpose, so the placement cell's CGPA panel has a live disagreement to show.
DEMO_STUDENT_CGPA = {
    "220200901": "8.72",
    "220200904": "8.05",
    "220200903": "8.90",
    "220200902": "7.10",
}

DEMO_STUDENTS = [
    {   # public and verified: appears in every company's search
        "prn": "220200901", "visibility": "all", "verified": True,
        "resume": "aarav_mehta_backend.pdf",
        "headline": "Backend developer, Python and Django",
        "summary": "Final-year computer science student who has built and deployed REST APIs.",
        "skills": ["Python", "Django", "PostgreSQL", "Docker", "Git"],
        "experience": [("Backend Intern", "Acme Logistics", "internship",
                        datetime.date(2025, 5, 1), datetime.date(2025, 8, 1), ["Python", "Django"])],
        "projects": [("Placement tracker API", ["Django", "DRF", "PostgreSQL"]),
                     ("Dockerised blog engine", ["Docker", "Python"])],
    },
    {   # second public and verified student, from a different department
        "prn": "220200904", "visibility": "all", "verified": True,
        "resume": "sana_qureshi_data.docx",
        "headline": "Data analyst, SQL and pandas",
        "summary": "Data science student who likes turning messy spreadsheets into dashboards.",
        "skills": ["SQL", "Python", "pandas", "Excel", "Power BI"],
        "experience": [("Data Analyst Intern", "Nimbus Retail", "internship",
                        datetime.date(2025, 6, 1), datetime.date(2025, 9, 1), ["SQL", "pandas"])],
        "projects": [("Campus footfall dashboard", ["Power BI", "SQL"]),
                     ("Churn prediction notebook", ["Python", "pandas"])],
    },
    {   # "shortlisted only": visible to the first company only, because it
        # shortlisted this student while the profile was still public
        "prn": "220200903", "visibility": "shortlisted", "verified": True,
        "shortlisted_by": 0,
        "resume": "kabir_nair_frontend.pdf",
        "headline": "Frontend developer, React and TypeScript",
        "summary": "Likes building small, fast interfaces.",
        "skills": ["React", "TypeScript", "HTML", "CSS"],
        "experience": [("Web Development Intern", "Pixel Studio", "internship",
                        datetime.date(2025, 6, 1), datetime.date(2025, 7, 15), ["React"])],
        "projects": [("Portfolio site", ["React", "Tailwind CSS"]),
                     ("Expense splitter", ["TypeScript", "React"])],
    },
    {   # hidden and unverified: no company can see it, an admin still can
        "prn": "220200902", "visibility": "hidden", "verified": False,
        "resume": "ishita_banerjee_marketing.pdf",
        "headline": "Computer science student",
        "summary": "Still working on this profile.",
        "skills": ["Python", "Java"],
        "experience": [("Open-source Contributor", "Community project", "volunteer",
                        datetime.date(2025, 1, 1), None, ["Python"])],
        "projects": [("Library management system", ["Java", "MySQL"]),
                     ("Weather CLI", ["Python"])],
    },
]


class Command(BaseCommand):
    help = "Create demo admin/company accounts and load the sample roster."

    def add_arguments(self, parser):
        parser.add_argument(
            "--roster",
            default=str(DEFAULT_ROSTER),
            help="Roster CSV to load (default: fixtures/roster_sample.csv).",
        )
        parser.add_argument(
            "--with-students",
            action="store_true",
            help="Also create four students with full profiles, accounts and "
            "resumes, spread across the visibility settings.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete students, flagged signups and student accounts first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            User.objects.filter(role=Role.STUDENT).delete()
            FlaggedSignup.objects.all().delete()
            Student.objects.all().delete()
            self.stdout.write(self.style.WARNING("Reset: roster and student accounts cleared."))

        for email, name, password in ADMINS:
            self._upsert(email, name, password, User.objects.create_admin, "admin")
        for org_name, org_email, email, name, password in COMPANIES:
            company, _ = Company.objects.get_or_create(
                name=org_name, defaults={"email": org_email}
            )
            self._upsert(
                email, name, password,
                lambda **kw: User.objects.create_company(company=company, **kw),
                f"recruiter at {company.company_id} {org_name}",
            )

        self._seed_categories()

        roster_path = Path(options["roster"])
        if not roster_path.exists():
            self.stderr.write(self.style.ERROR(f"Roster file not found: {roster_path}"))
            return

        with roster_path.open("rb") as handle:
            result = import_roster_csv(handle)

        self.stdout.write(
            self.style.SUCCESS(
                f"Roster: {result.created} created, {result.updated} updated, "
                f"{result.unchanged} unchanged, {len(result.errors)} rejected."
            )
        )
        for error in result.errors:
            self.stderr.write(f"  row {error.row} ({error.prn}): {error.errors}")

        demo_students = self._seed_students() if options["with_students"] else []

        self.stdout.write("")
        self.stdout.write("Sign in with:")
        for email, _, password in ADMINS:
            self.stdout.write(f"  admin    {email} / {password}")
        for _, _, email, _, password in COMPANIES:
            self.stdout.write(f"  company  {email} / {password}")
        for prn, email, password, visibility, verified in demo_students:
            self.stdout.write(
                f"  student  {prn} / {email} / {password}"
                f"  ({visibility}, {'verified' if verified else 'unverified'})"
            )
        self.stdout.write(
            "  student  sign up at /signup with any PRN + email from the roster"
        )

    def _upsert(self, email, name, password, factory, label):
        user = User.objects.filter(email=email).first()
        if user is None:
            factory(email=email, password=password, full_name=name)
            self.stdout.write(self.style.SUCCESS(f"Created {label}: {email}"))
            return
        # Keep the documented password working across re-runs.
        user.set_password(password)
        user.full_name = name
        user.is_active = True
        user.save(update_fields=["password", "full_name", "is_active"])
        self.stdout.write(f"Updated {label}: {email}")

    def _resume_path(self, filename: str, scratch: Path) -> Path:
        """The fixture path, or a freshly rendered copy.

        The sample resumes are gitignored (they are generated), so a clean
        clone does not have them; render into a scratch dir rather than fail.
        """
        path = Path(settings.BASE_DIR) / "fixtures" / "resumes" / filename
        if path.exists():
            return path
        from matching.management.commands.make_sample_resumes import render_samples

        render_samples(scratch)
        return scratch / filename

    def _seed_students(self):
        from django.core.files import File

        from matching.engine import get_engine
        from profiles.models import (
            CompanyShortlist,
            ExperienceEntry,
            ProfileSkill,
            ProjectEntry,
            StudentProfile,
            slugify_skill,
        )

        admin = User.objects.filter(role=Role.ADMIN, email=ADMINS[0][0]).first()
        companies = [Company.objects.get(name=name) for name, *_ in COMPANIES]
        engine = get_engine()
        shown = []

        with tempfile.TemporaryDirectory() as scratch:
            for spec in DEMO_STUDENTS:
                roster = Student.objects.filter(prn=spec["prn"]).first()
                if roster is None:
                    self.stderr.write(f"Roster has no {spec['prn']}; skipping that demo student.")
                    continue

                user = User.objects.filter(prn=roster.prn).first()
                if user is None:
                    user = User.objects.create_user(
                        email=roster.email, password=STUDENT_PASSWORD,
                        prn=roster.prn, full_name=roster.full_name,
                    )
                else:
                    # Keep the documented password working across re-runs.
                    user.set_password(STUDENT_PASSWORD)
                    user.save(update_fields=["password"])
                user.mark_verified()

                profile, _ = StudentProfile.objects.get_or_create(
                    user=user, student=roster, defaults={"phone": roster.phone}
                )
                profile.headline, profile.summary = spec["headline"], spec["summary"]

                if not profile.resume:
                    path = self._resume_path(spec["resume"], Path(scratch))
                    with path.open("rb") as handle:
                        extracted = engine.parse_resume(handle, path.name)
                        handle.seek(0)
                        profile.resume.save(path.name, File(handle), save=False)
                    profile.resume_filename = path.name
                    profile.apply_parsed_resume(extracted)

                results = DEMO_SCHOOL_RESULTS.get(roster.prn)
                if results:
                    (
                        profile.marks_10_percentage,
                        profile.marks_10_board,
                        profile.marks_10_year,
                        profile.marks_12_percentage,
                        profile.marks_12_board,
                        profile.marks_12_year,
                    ) = results
                # The student's own statement. The marksheet and transcript
                # files stay empty: seeding a scan nobody issued would put a
                # document on record that cannot be checked against anything.
                profile.confirmed_cgpa = DEMO_STUDENT_CGPA.get(roster.prn)
                profile.save()

                for name in spec["skills"]:
                    # Looked up by slug so a re-run adds nothing.
                    if not profile.skills.filter(slug=slugify_skill(name)).exists():
                        ProfileSkill.objects.create(profile=profile, name=name)
                for role, org, kind, start, end, used in spec["experience"]:
                    ExperienceEntry.objects.get_or_create(
                        profile=profile, role=role, organization=org,
                        defaults={"kind": kind, "start_date": start,
                                  "end_date": end, "skills_used": used},
                    )
                for title, stack in spec["projects"]:
                    ProjectEntry.objects.get_or_create(
                        profile=profile, title=title,
                        defaults={"tech_stack": stack,
                                  "description": f"{title}, built for coursework."},
                    )

                # The shortlist is written before visibility narrows, as in
                # real use: a company can only shortlist a profile it can see.
                if "shortlisted_by" in spec:
                    CompanyShortlist.objects.get_or_create(
                        company=companies[spec["shortlisted_by"]], profile=profile,
                        defaults={"note": "Demo shortlist"},
                    )
                profile.visibility = spec["visibility"]
                profile.save(update_fields=["visibility", "updated_at"])
                if spec["verified"] and not profile.is_verified:
                    profile.mark_verified(admin)
                elif not spec["verified"] and profile.is_verified:
                    profile.revoke_verification()

                shown.append((roster.prn, roster.email, STUDENT_PASSWORD,
                              spec["visibility"], spec["verified"]))

        self.stdout.write(self.style.SUCCESS(f"Demo students: {len(shown)} with full profiles."))
        return shown

    def _seed_categories(self):
        taken = set()
        for category in RoleCategory.objects.all():
            taken |= category.spellings()
        client = llm.get_client() if llm.llm_enabled() else None
        embedder = get_embedder(client) if client else None
        created = 0
        for text, data in DEMO_JOBS:
            if normalise_role(data["canonical_role"]) in taken:
                continue
            facts = llm.JobFacts(data=data, model="seed_demo")
            if client is not None:
                try:
                    facts = llm.parse_job_description(text, client=client)
                except llm.LLMUnavailable as exc:
                    self.stderr.write(f"LLM unavailable ({exc}); using the hand-written reading.")
                if normalise_role(facts.canonical_role) in taken:
                    continue
            vector = embedder.try_embed(text) if embedder else None
            category = record_job_description(facts, vector, model=embedder.model if vector else None)
            if category is not None:
                taken |= category.spellings()
                created += 1
        self.stdout.write(
            f"Role categories: {created} demo JD(s) recorded, {RoleCategory.objects.count()} in all."
        )
