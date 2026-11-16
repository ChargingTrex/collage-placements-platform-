"""
The demo postings `seed_demo` creates: every status, for both demo companies.

Data only; the command turns it into rows. Everything here is synthetic. A
posting that has `apps` gets those students applying through the real
`opportunities.services`, then moving along the listed path, so the seeded
events, scores and snapshots are what the live code would have written.

`apps` entries: (student PRN, [statuses to move through after applying]).
The path may end in "withdrawn". The students are the four `--with-students`
demo students (core.management.commands.seed_demo.DEMO_STUDENTS); PRN 220200903
is "shortlisted only" for the first company alone, so it applies to the first
company's postings only (applying to another would make it visible there).
"""

from matching.samples import SAMPLE_JOB_DESCRIPTION

CS = "B.Tech Computer Science"
DS = "B.Tech Data Science"

BACKEND_JD = SAMPLE_JOB_DESCRIPTION

#: `company` indexes core.demo_accounts.COMPANIES. `deadline_days` is relative
#: to the day the posting is first created (negative: already past).
DEMO_OPPORTUNITIES = [
    # --- Acme Tech --------------------------------------------------------
    {
        "company": 0, "title": "Backend Engineer", "status": "open", "role_type": "full_time",
        "description": BACKEND_JD, "location": "Pune", "openings": 3,
        "required_skills": ["Python", "Django", "PostgreSQL", "Docker", "Git"],
        "eligible_departments": [CS, DS], "min_cgpa": "7.00", "min_experience_years": "1.0",
        "required_education_levels": ["UG"],
        "salary": (600000, 900000, "year"), "deadline_days": 21,
        "apps": [
            ("220200901", ["shortlisted", "interview"]),
            ("220200903", ["shortlisted"]),
            ("220200904", []),
            ("220200902", ["rejected"]),
        ],
    },
    {
        "company": 0, "title": "Frontend Developer Intern", "status": "open",
        "role_type": "internship",
        "description": (
            "Frontend Developer Intern. Build responsive pages in React and TypeScript "
            "from Figma designs. Required: React, TypeScript, HTML, CSS. "
            "Tailwind CSS experience is a plus."
        ),
        "location": "Remote", "openings": 2,
        "required_skills": ["React", "TypeScript", "HTML", "CSS"],
        "eligible_departments": [], "min_cgpa": "6.50", "min_experience_years": None,
        "required_education_levels": [],
        "salary": (20000, 30000, "month"), "deadline_days": 10,
        "apps": [
            ("220200903", ["shortlisted", "interview", "offer"]),
            ("220200901", ["withdrawn"]),
        ],
    },
    {
        "company": 0, "title": "Platform Engineer", "status": "draft", "role_type": "full_time",
        "description": (
            "Platform Engineer. Own the build and deploy pipeline. Required: Docker, "
            "Linux, CI/CD, Python scripting. Kubernetes is a plus."
        ),
        "location": "Pune", "openings": 1,
        "required_skills": ["Docker", "Linux", "Python"],
        "eligible_departments": [CS], "min_cgpa": "7.50", "min_experience_years": None,
        "required_education_levels": [], "salary": None, "deadline_days": 30, "apps": [],
    },
    {
        "company": 0, "title": "QA Automation Engineer", "status": "pending_review",
        "role_type": "full_time",
        "description": (
            "QA Automation Engineer. Write end-to-end tests for web products. Required: "
            "Python, Selenium or Playwright, REST testing, Git."
        ),
        "location": "Pune", "openings": 2,
        "required_skills": ["Python", "Selenium", "Git"],
        "eligible_departments": [CS, DS], "min_cgpa": "6.50", "min_experience_years": None,
        "required_education_levels": [],
        "salary": (450000, 650000, "year"), "deadline_days": 25, "apps": [],
    },
    {
        "company": 0, "title": "Support Engineer", "status": "closed", "role_type": "full_time",
        "description": (
            "Support Engineer. First line technical support for our logistics platform. "
            "Required: SQL, troubleshooting, clear written English."
        ),
        "location": "Mumbai", "openings": 1,
        "required_skills": ["SQL"], "eligible_departments": [], "min_cgpa": None,
        "min_experience_years": None, "required_education_levels": [],
        "salary": (350000, 450000, "year"), "deadline_days": -5,
        "apps": [
            ("220200904", ["rejected"]),
            ("220200901", ["shortlisted", "interview", "offer"]),
        ],
    },
    {
        "company": 0, "title": "DevOps Engineer", "status": "rejected", "role_type": "full_time",
        "description": "DevOps Engineer. We need someone good with servers.",
        "location": "Pune", "openings": 1, "required_skills": [],
        "eligible_departments": [], "min_cgpa": None, "min_experience_years": None,
        "required_education_levels": [], "salary": None, "deadline_days": 20, "apps": [],
        "rejection_reason": "The description is too thin to score anyone against. "
                            "List the skills and tools you actually need.",
    },
    # --- Nimbus Analytics ---------------------------------------------------
    {
        "company": 1, "title": "Data Analyst", "status": "open", "role_type": "full_time",
        "description": (
            "Data Analyst. Build dashboards and reports for the operations team. Required: "
            "strong SQL, Python with pandas, Excel, and a feel for statistics. Power BI or "
            "Tableau is a plus."
        ),
        "location": "Bengaluru", "openings": 2,
        "required_skills": ["SQL", "Python", "pandas", "Excel"],
        "eligible_departments": [DS, CS], "min_cgpa": "7.00", "min_experience_years": None,
        "required_education_levels": ["UG"],
        "salary": (500000, 750000, "year"), "deadline_days": 14,
        "apps": [
            ("220200904", ["shortlisted"]),
            ("220200901", []),
        ],
    },
    {
        "company": 1, "title": "Business Analyst Intern", "status": "open",
        "role_type": "internship",
        "description": (
            "Business Analyst Intern. Support the strategy team with market sizing and "
            "reporting. Required: Excel, clear communication, an analytical mind."
        ),
        "location": "Remote", "openings": 3,
        "required_skills": ["Excel"], "eligible_departments": [], "min_cgpa": None,
        "min_experience_years": None, "required_education_levels": [],
        "salary": None, "deadline_days": 2, "apps": [],
    },
    {
        "company": 1, "title": "ML Engineer", "status": "draft", "role_type": "full_time",
        "description": (
            "ML Engineer. Train and ship recommendation models. Required: Python, "
            "scikit-learn, SQL. PyTorch is a plus."
        ),
        "location": "Bengaluru", "openings": 1,
        "required_skills": ["Python", "scikit-learn", "SQL"],
        "eligible_departments": [DS], "min_cgpa": "8.00", "min_experience_years": None,
        "required_education_levels": [], "salary": None, "deadline_days": 40, "apps": [],
    },
    {
        "company": 1, "title": "Reporting Analyst", "status": "pending_review",
        "role_type": "full_time",
        "description": (
            "Reporting Analyst. Own the weekly business reports. Required: SQL, Excel, "
            "Power BI."
        ),
        "location": "Bengaluru", "openings": 1,
        "required_skills": ["SQL", "Excel", "Power BI"],
        "eligible_departments": [], "min_cgpa": "6.50", "min_experience_years": None,
        "required_education_levels": [],
        "salary": (400000, 550000, "year"), "deadline_days": 18, "apps": [],
    },
    {
        "company": 1, "title": "Data Engineer", "status": "closed", "role_type": "full_time",
        "description": (
            "Data Engineer. Build and run ETL pipelines. Required: Python, SQL, Airflow."
        ),
        "location": "Bengaluru", "openings": 1,
        "required_skills": ["Python", "SQL", "Airflow"],
        "eligible_departments": [DS, CS], "min_cgpa": "7.50", "min_experience_years": None,
        "required_education_levels": [],
        "salary": (700000, 1000000, "year"), "deadline_days": -10,
        "apps": [("220200901", ["rejected"])],
    },
    {
        "company": 1, "title": "Growth Analyst", "status": "rejected", "role_type": "internship",
        "description": "Growth Analyst intern. Help with growth.",
        "location": "Remote", "openings": 1, "required_skills": [],
        "eligible_departments": [], "min_cgpa": None, "min_experience_years": None,
        "required_education_levels": [], "salary": None, "deadline_days": 20, "apps": [],
        "rejection_reason": "Too vague to publish. Say what the intern will do and which "
                            "skills you need.",
    },
]
