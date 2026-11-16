"""
The demo accounts `seed_demo` creates, in one place.

Kept apart from the management command so the demo sign-in endpoint can name
the seeded accounts without importing the command, which pulls in the
matching engine. Every name, address and password here is synthetic.
"""

#: (login email, full name, password). The first admin verifies the seeded
#: student profiles, so new admins are appended, never inserted ahead of it.
ADMINS = [
    ("placement.officer@college.edu", "Priya Kulkarni", "AdminPass!234"),
    # The pilot placement officer: a login of their own, with its own ADM- id,
    # so their activity is not mixed into the shared demo admin's audit trail.
    ("pilot.officer@college.edu", "Anika Verma", "PilotPass!234"),
]
PILOT_OFFICER_EMAIL = ADMINS[1][0]

#: (organisation name, organisation email, recruiter login, recruiter name, password)
COMPANIES = [
    ("Acme Tech", "careers@acmetech.example",
     "recruiter@acmetech.example", "Priya Raman", "CompanyPass!234"),
    ("Nimbus Analytics", "careers@nimbusanalytics.example",
     "talent@nimbusanalytics.example", "Dev Menon", "CompanyPass!234"),
]

STUDENT_PASSWORD = "StudentPass!234"

#: The student the "student" demo persona signs in as: the first of the
#: `--with-students` demo students (public and verified).
DEMO_STUDENT_PRN = "220200901"
