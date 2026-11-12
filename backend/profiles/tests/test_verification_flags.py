"""
Verification flags reach admins, and nobody else.

The flags, and the resume's age, DOB and CGPA behind them, are admin-only
(RESUME_INTELLIGENCE_PLAN.md §2). Each payload a student or a company can
fetch is checked for every key and every value, with a reading that holds
all of them.
"""

import datetime
import json

import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from matching import llm
from matching.testing import FakeLLMClient, resume_reply
from profiles import analysis as analysis_service
from profiles.analysis import resume_digest
from profiles.models import ExperienceEntry, ProjectEntry, ResumeAnalysis
from profiles.verification import verification_checks, verification_inputs

RESUME = """Aarav Mehta
aarav.mehta@college.edu | +91 91234 56780
Age: 23  DOB: 09/07/2003  CGPA: 9.41/10

EXPERIENCE
Backend Developer Intern, Loadstar Logistics, Jan 2024 - Dec 2024

EDUCATION
B.Tech in Computer Engineering, 2022 - 2026
"""

#: Values that exist only on the resume. None may reach a student or company.
SECRET_VALUES = ("9.41", "2003-07-09", "9123456780", "aarav.personal@gmail.com")
ADMIN_ONLY_KEYS = {
    "verification_checks", "warning_count", "resume_facts_admin", "age", "date_of_birth",
    "dob", "phones", "emails", "facts", "regex_facts",
}


def full_reply(**overrides):
    return resume_reply(
        **{
            "emails": ["aarav.personal@gmail.com"],
            "phones": ["+91 91234 56780"],
            "age": 23,
            "date_of_birth": "2003-07-09",
            "cgpa": 9.41,
            "experience": [
                {"role": "Backend Developer Intern", "organization": "Loadstar Logistics",
                 "kind": "internship", "start": "2024-01", "end": "2024-12", "is_current": False,
                 "summary": None},
            ],
            **overrides,
        }
    )


@pytest.fixture
def llm_on(monkeypatch):
    def _install(client):
        monkeypatch.setattr(llm, "llm_enabled", lambda: True)
        monkeypatch.setattr(llm, "get_client", lambda: client)
        return client

    return _install


@pytest.fixture
def analysed(llm_on):
    """A profile whose resume reading holds every admin-only value."""

    def _analyse(profile, reply=None, text=RESUME):
        profile.resume.save("cv.pdf", ContentFile(b"%PDF-1.4 stub"), save=False)
        profile.resume_filename = "cv.pdf"
        profile.resume_text = text
        profile.save()
        llm_on(FakeLLMClient([reply or full_reply()]))
        analysis, _ = analysis_service.analyse(profile, today=datetime.date(2026, 10, 19))
        assert analysis.facts["cgpa"] == 9.41
        return profile

    return _analyse


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def assert_no_admin_only_data(body):
    assert not set(_keys(body)) & ADMIN_ONLY_KEYS
    dumped = json.dumps(body)
    for value in SECRET_VALUES:
        assert value not in dumped, value


# --- the helper ----------------------------------------------------------------


@pytest.mark.django_db
class TestHelper:
    def test_the_inputs_are_the_form_and_the_roster_as_plain_dicts(self, profile):
        profile.student.phone = "+91 98765 43210"
        profile.student.programme = "B.Tech Computer Engineering"
        profile.student.save()
        ExperienceEntry.objects.create(
            profile=profile, role="SDE Intern", organization="Acme",
            start_date=datetime.date(2024, 1, 1), end_date=datetime.date(2024, 7, 1),
        )
        ProjectEntry.objects.create(profile=profile, title="Fleet tracker")

        form, roster = verification_inputs(profile)

        assert form["experience_years"] == 0.0
        assert form["experience"][0]["duration_months"] == 6
        assert form["experience"][0]["organization"] == "Acme"
        assert form["projects"] == ["Fleet tracker"]
        assert roster == {
            "full_name": "Aarav Mehta", "email": profile.student.email, "phone": "+91 98765 43210",
            "cgpa": 8.72, "batch": 2026, "programme": "B.Tech Computer Engineering",
            "department": "Computer Engineering",
        }

    def test_with_no_analysis_there_are_no_flags(self, profile):
        assert verification_checks(profile) == []

    def test_a_pending_analysis_has_no_flags(self, profile):
        ResumeAnalysis.objects.create(profile=profile, regex_facts={"cgpa": 9.9})

        assert verification_checks(profile) == []

    def test_the_flags_are_computed_from_the_current_form(self, profile, analysed):
        analysed(profile)
        before = [f for f in verification_checks(profile) if f.field == "experience"]

        ExperienceEntry.objects.create(
            profile=profile, role="Tutor", organization="Acme Coaching",
            start_date=datetime.date(2023, 6, 1), end_date=datetime.date(2023, 8, 1),
        )
        profile.refresh_from_db()
        after = [f for f in verification_checks(profile) if f.field == "experience"]

        assert len(after) == len(before) + 1

    def test_the_resume_cgpa_is_never_stored_on_the_profile(self, profile, analysed):
        analysed(profile)
        profile.refresh_from_db()
        profile.student.refresh_from_db()

        assert float(profile.student.cgpa) == 8.72
        assert any(f.field == "cgpa" for f in verification_checks(profile))

    def test_with_the_llm_off_the_regex_reading_is_checked(self, profile):
        profile.resume_text = RESUME
        profile.save()
        analysis_service.analyse(profile)

        [flag] = [f for f in verification_checks(profile) if f.field == "cgpa"]
        assert flag.values == {"roster": 8.72, "resume": 9.41}


# --- the admin sees them ---------------------------------------------------------


@pytest.mark.django_db
class TestAdminSeesTheFlags:
    def test_the_admin_detail_carries_the_flags_and_the_resume_facts(self, as_admin, profile, analysed):
        analysed(profile)

        body = as_admin.get(reverse("admin-profile-detail", args=[profile.student_id])).json()

        cgpa = next(flag for flag in body["verification_checks"] if flag["field"] == "cgpa")
        assert cgpa["severity"] == "warning"
        assert cgpa["values"] == {"roster": 8.72, "resume": 9.41}
        assert body["warning_count"] == sum(f["severity"] == "warning" for f in body["verification_checks"])
        assert body["warning_count"] >= 1
        assert body["resume_facts_admin"] == {
            "age": 23,
            "date_of_birth": "2003-07-09",
            "cgpa": 9.41,
            "phones": ["9123456780"],
            "emails": ["aarav.personal@gmail.com", "aarav.mehta@college.edu"],
            "source": "llm",
        }

    def test_the_admin_list_carries_the_warning_count(self, as_admin, profile, analysed):
        analysed(profile)

        [row] = as_admin.get(reverse("admin-profile-list")).json()["results"]

        assert row["warning_count"] >= 1
        assert "resume_facts_admin" not in row

    def test_a_profile_never_analysed_has_no_flags_and_no_facts(self, as_admin, profile):
        body = as_admin.get(reverse("admin-profile-detail", args=[profile.student_id])).json()

        assert body["verification_checks"] == []
        assert body["warning_count"] == 0
        assert body["resume_facts_admin"] is None

    def test_the_admin_list_reads_every_analysis_in_the_page_query(self, as_admin, make_student, analysed):
        """No N+1: the analysis rides the profile query, and the form's
        children come from one prefetch each, however many rows there are."""
        for index in range(3):
            profile = make_student(prn=f"22020090{index + 1}", full_name=f"Student {index}")
            analysed(profile)
            ExperienceEntry.objects.create(
                profile=profile, role="Intern", organization=f"Org {index}",
                start_date=datetime.date(2024, 1, 1), end_date=datetime.date(2024, 6, 1),
            )

        with CaptureQueriesContext(connection) as captured:
            response = as_admin.get(reverse("admin-profile-list"))

        assert response.status_code == 200
        assert len(response.json()["results"]) == 3
        sql = [query["sql"] for query in captured.captured_queries]
        assert not [q for q in sql if 'FROM "profiles_resumeanalysis"' in q]
        assert len([q for q in sql if 'FROM "profiles_experienceentry"' in q]) == 1
        assert len([q for q in sql if 'FROM "profiles_projectentry"' in q]) == 1

    def test_the_admin_list_query_count_does_not_grow_with_the_rows(self, as_admin, make_student, company):
        """`shortlisted_by_count` is annotated on the page query, not counted per row."""
        from accounts.models import Company
        from profiles.models import CompanyShortlist

        other = Company.objects.create(name="Globex", email="jobs@globex.example")

        def page_queries():
            with CaptureQueriesContext(connection) as captured:
                response = as_admin.get(reverse("admin-profile-list"))
            assert response.status_code == 200
            return len(captured.captured_queries), response.json()["results"]

        for index in range(9):
            profile = make_student(prn=f"2202009{index + 10}", full_name=f"Student {index}")
            if index == 0:
                CompanyShortlist.objects.create(company=company, profile=profile)
                CompanyShortlist.objects.create(company=other, profile=profile)
            if index == 2:
                few, rows = page_queries()
        many, rows = page_queries()

        assert many == few
        counts = {row["student"]["prn"]: row["shortlisted_by_count"] for row in rows}
        assert counts["220200910"] == 2
        assert sum(counts.values()) == 2

    def test_the_admin_detail_still_counts_the_shortlists(self, as_admin, profile, company):
        from profiles.models import CompanyShortlist

        CompanyShortlist.objects.create(company=company, profile=profile)
        body = as_admin.get(reverse("admin-profile-detail", args=[profile.student_id])).json()
        assert body["shortlisted_by_count"] == 1

    def test_flags_never_block_mark_verified(self, as_admin, admin_user, profile, analysed):
        analysed(profile)

        response = as_admin.post(
            reverse("admin-profile-verification", args=[profile.student_id]),
            {"is_verified": True},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["is_verified"] is True
        assert response.json()["warning_count"] >= 1
        profile.refresh_from_db()
        assert profile.is_verified is True


@pytest.mark.django_db
class TestOnlyAdminsReachTheAdminEndpoints:
    @pytest.mark.parametrize("who", ["as_student", "as_company"])
    def test_a_non_admin_gets_403_on_the_admin_list_and_detail(self, request, who, profile, analysed):
        analysed(profile)
        client = request.getfixturevalue(who)

        assert client.get(reverse("admin-profile-list")).status_code == 403
        assert client.get(reverse("admin-profile-detail", args=[profile.student_id])).status_code == 403


# --- nobody else does ------------------------------------------------------------


@pytest.mark.django_db
class TestNoOtherPayloadCarriesThem:
    def test_the_students_own_profile(self, as_student, profile, analysed):
        analysed(profile)

        assert_no_admin_only_data(as_student.get(reverse("my-profile")).json())

    def test_the_company_list_detail_and_search(self, as_company, profile, analysed):
        analysed(profile)

        listed = as_company.get(reverse("company-profile-list")).json()
        detail = as_company.get(reverse("company-profile-detail", args=[profile.student_id])).json()
        searched = as_company.get(reverse("company-profile-list"), {"search": "Aarav"}).json()

        assert listed["results"] and searched["results"]
        for body in (listed, detail, searched):
            assert_no_admin_only_data(body)

    def test_the_analyze_and_analysis_responses(self, as_student, profile, llm_on):
        profile.resume.save("cv.pdf", ContentFile(b"%PDF-1.4 stub"), save=False)
        profile.resume_text = RESUME
        profile.save()
        ResumeAnalysis.objects.create(profile=profile, resume_sha256=resume_digest(RESUME))
        llm_on(FakeLLMClient([full_reply()]))

        posted = as_student.post(reverse("my-resume-analyze")).json()
        polled = as_student.get(reverse("my-resume-analysis")).json()

        assert posted["status"] == "done"
        for body in (posted, polled):
            assert_no_admin_only_data(body)

    def test_the_upload_response(self, as_student, profile, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from matching.management.commands.make_sample_resumes import write_pdf

        path = tmp_path / "cv.pdf"
        write_pdf(path, RESUME.splitlines())
        upload = SimpleUploadedFile("cv.pdf", path.read_bytes(), content_type="application/pdf")

        response = as_student.post(reverse("my-resume"), {"file": upload}, format="multipart")

        assert response.status_code == 201
        assert_no_admin_only_data(response.json())
