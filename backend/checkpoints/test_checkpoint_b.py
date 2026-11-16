"""
Checkpoint B -- the gate for Phase B (agents.md Phase 4) and Addendum 2
stages 2 to 4.

Written before the features exist, so every test here fails today. The shapes
asserted are exactly those in `docs/OPPORTUNITIES_API_CONTRACT.md`; if one has
to change, change the contract first.

A missing URL name, model or command is reported through `url()`, `model()`
and `missing()` as "not built yet", never as an import or collection error.
Nothing new is imported at module level. Fixtures only touch what exists
today, so a test fails (it never errors during setup).

Run alone:

    cd backend && ../.venv/bin/python -m pytest checkpoints/test_checkpoint_b.py -q
"""

from __future__ import annotations

import base64
import csv
import io
import json
import zipfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from checkpoints.conftest import client_for

# Synthetic PRNs: YY0200NNN, YY = batch - 4, sequences 940-959.
CS = "B.Tech Computer Science"
DS = "B.Tech Data Science"
ECON = "B.A. (Hons.) Economics"

MARKETING_JD = (
    "Marketing Executive. Plan and run brand campaigns, social media content, "
    "email newsletters and SEO. Report on campaign performance, manage the "
    "content calendar and work with agencies and the sales team. Communication "
    "and creativity matter more than any programming."
)

FORBIDDEN_KEY_PREFIXES = (
    "marks_",
    "marksheet",
    "confirmed_cgpa",
    "parsed_cgpa",
    "recomputed_cgpa",
    "career_path",
    "transcript",
    "personal_email",
    "also_attending_placements",
    "completion_percent",
)

COMPANY_APPLICATION_KEYS = {
    "id", "status", "applied_at", "score", "similarity", "eligible",
    "eligibility_reasons", "opportunity", "prn", "full_name", "department",
    "programme", "school", "batch", "year_of_study", "cgpa_at_apply", "skills",
    "resume_url", "contact", "contact_available",
}

CONTACT_COLUMNS = [
    "prn", "full_name", "department", "programme", "batch", "cgpa", "email",
    "phone", "contact_available", "shortlisted_on",
]
APPLICANT_COLUMNS = [
    "prn", "full_name", "department", "programme", "school", "batch",
    "cgpa_at_apply", "status", "score", "applied_at", "email", "phone",
    "contact_available",
]


# --- helpers ---------------------------------------------------------------


def missing(what: str) -> None:
    """Fail with the thing that is absent, not with a traceback."""
    pytest.fail(f"not built yet: {what}")


def url(name: str, *args) -> str:
    """Resolve a URL name, or fail saying it is not built yet."""
    try:
        return reverse(name, args=list(args))
    except NoReverseMatch:
        missing(name)


def model(app: str, name: str):
    """Look a model up, or fail saying it is not built yet."""
    try:
        return apps.get_model(app, name)
    except LookupError:
        missing(f"{app}.{name}")


def body_of(response) -> bytes:
    if getattr(response, "streaming", False):
        return b"".join(response.streaming_content)
    return response.content


def rows(response) -> list:
    """The list rows of a paginated or plain list response."""
    payload = response.json()
    return payload["results"] if isinstance(payload, dict) else payload


def audit_count(action: str) -> int:
    from core.models import AuditLog

    return AuditLog.objects.filter(action=action).count()


def last_audit(action: str):
    from core.models import AuditLog

    return AuditLog.objects.filter(action=action).order_by("-created_at").first()


def dec(value) -> Decimal:
    return Decimal(str(value))


def all_keys(obj):
    """Every dict key anywhere in a JSON value, nested included."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from all_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from all_keys(item)


def assert_allow_list(payload) -> None:
    for key in all_keys(payload):
        assert not key.startswith(FORBIDDEN_KEY_PREFIXES), f"forbidden key {key!r} in company payload"


def today():
    return timezone.localdate()


def opp_body(company=None, **over) -> dict:
    from matching.samples import SAMPLE_JOB_DESCRIPTION

    body = {
        "title": "Backend Engineer",
        "description": SAMPLE_JOB_DESCRIPTION,
        "role_type": "full_time",
        "location": "Pune",
        "openings": 2,
        "required_skills": ["Python", "Django", "PostgreSQL"],
        "eligible_departments": [CS, DS],
        "min_cgpa": "7.00",
        "min_experience_years": "2.0",
        "required_education_levels": ["UG"],
        "salary_disclosed": True,
        "salary_min": 40000,
        "salary_max": 60000,
        "salary_period": "month",
        "salary_currency": "INR",
        "deadline": str(today() + timedelta(days=30)),
    }
    if company is not None:
        body["company"] = str(company.id)
    body.update(over)
    return body


def create_open(admin_client, company, **over) -> dict:
    """An admin creates an opportunity; it must be `open` at once (D28)."""
    response = admin_client.post(url("opportunity-list"), opp_body(company, **over), format="json")
    assert response.status_code == 201, response.content
    assert response.json()["status"] == "open"
    return response.json()


def create_draft(recruiter_client, **over) -> dict:
    response = recruiter_client.post(url("opportunity-list"), opp_body(**over), format="json")
    assert response.status_code == 201, response.content
    assert response.json()["status"] == "draft"
    return response.json()


def make_pending(recruiter_client, **over) -> dict:
    opp = create_draft(recruiter_client, **over)
    response = recruiter_client.post(url("opportunity-submit", opp["id"]))
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "pending_review"
    return opp


def orm_opportunity(company, **over):
    """An opportunity written straight to the ORM, for states the API will not make."""
    from matching.samples import SAMPLE_JOB_DESCRIPTION

    fields = dict(
        company=company,
        title="Seeded Posting",
        description=SAMPLE_JOB_DESCRIPTION,
        role_type="full_time",
        deadline=today() + timedelta(days=30),
        status="open",
        required_skills=[],
        eligible_departments=[CS],
        min_cgpa=Decimal("7.00"),
    )
    fields.update(over)
    return model("opportunities", "Opportunity").objects.create(**fields)


def apply_to(client, opp_id):
    return client.post(url("opportunity-apply", opp_id))


def applied(client, opp_id) -> dict:
    response = apply_to(client, opp_id)
    assert response.status_code == 201, response.content
    return response.json()


def move(client, app_id, status, note=None):
    body = {"status": status}
    if note:
        body["note"] = note
    return client.post(url("application-status", app_id), body, format="json")


def walk(client, app_id, *statuses):
    for status in statuses:
        response = move(client, app_id, status)
        assert response.status_code == 200, response.content


def shortlist_row(company, profile):
    return model("profiles", "CompanyShortlist").objects.filter(company=company, profile=profile).first()


def csv_rows(response) -> list[dict]:
    return list(csv.DictReader(io.StringIO(body_of(response).decode("utf-8"))))


# --- fixtures --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_matching_caches(settings):
    """Reset the skill graph and vector store, pinned to the local store."""
    from matching.skills import reset_skill_graph
    from matching.vectorstore import reset_vector_store

    settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "local"}
    reset_skill_graph()
    reset_vector_store()
    yield
    reset_skill_graph()
    reset_vector_store()


@pytest.fixture(autouse=True)
def _llm_off_and_fast_hasher(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.LLM = {**settings.LLM, "ENABLED": False}


@pytest.fixture
def nimbus(db):
    from accounts.models import Company

    return Company.objects.create(name="Nimbus Labs", email="jobs@nimbuslabs.example")


@pytest.fixture
def nimbus_user(db, nimbus):
    from accounts.models import User

    return User.objects.create_company(
        email="recruiter@nimbuslabs.example",
        password="CompanyPass!234",
        full_name="Nimbus Recruiter",
        company=nimbus,
    )


@pytest.fixture
def as_admin(admin_user):
    return client_for(admin_user)


@pytest.fixture
def as_acme(company_user):
    return client_for(company_user)


@pytest.fixture
def as_nimbus(nimbus_user):
    return client_for(nimbus_user)


@pytest.fixture
def as_bare(recruiter):
    """A recruiter login with no company."""
    return client_for(recruiter)


@pytest.fixture
def anon():
    from rest_framework.test import APIClient

    return APIClient()


def _upload_resume(profile, tmp_path, key):
    from matching.management.commands.make_sample_resumes import write_pdf
    from matching.samples import SAMPLES_BY_KEY

    path = Path(tmp_path) / f"{profile.student.prn}.pdf"
    write_pdf(path, list(SAMPLES_BY_KEY[key].lines))
    upload = SimpleUploadedFile(path.name, path.read_bytes(), content_type="application/pdf")
    response = client_for(profile.user).post(reverse("my-resume"), {"file": upload}, format="multipart")
    assert response.status_code < 300, response.content
    profile.refresh_from_db()


@pytest.fixture
def people(make_student, tmp_path):
    """
    Five students with resumes (D has none), all on roster batch 2026.

    A matches the backend posting; B is on the wrong programme; C is eligible
    but a marketing profile; D has no resume; E has a roster CGPA below 7.0.
    """
    from profiles.models import ProfileSkill

    def build(prn, name, programme, cgpa, key):
        profile = make_student(prn=prn, full_name=name, department=programme, cgpa=cgpa)
        profile.student.programme = programme
        profile.student.school = "computing_data_science" if programme == CS else ""
        profile.student.year_of_study = 4
        profile.student.save()
        if key:
            _upload_resume(profile, tmp_path, key)
        return profile

    a = build("220200940", "Aditi Verma", CS, "8.50", "backend_engineer")
    for skill in ("Python", "Django", "PostgreSQL"):
        ProfileSkill.objects.create(profile=a, name=skill)
    b = build("220200941", "Bhaskar Nair", ECON, "8.00", "marketing_executive")
    c = build("220200942", "Chitra Rao", CS, "7.50", "marketing_executive")
    d = build("220200943", "Dev Malhotra", CS, "8.00", None)
    e = build("220200944", "Esha Kulkarni", CS, "6.00", "backend_engineer")
    for profile in (a, b, c, d, e):
        profile.phone = "90000" + profile.student.prn[-5:]
        profile.save()
    return SimpleNamespace(a=a, b=b, c=c, d=d, e=e)


@pytest.fixture
def as_a(people):
    return client_for(people.a.user)


@pytest.fixture
def as_b(people):
    return client_for(people.b.user)


@pytest.fixture
def as_c(people):
    return client_for(people.c.user)


@pytest.fixture
def as_d(people):
    return client_for(people.d.user)


@pytest.fixture
def as_e(people):
    return client_for(people.e.user)


@pytest.fixture
def opportunity_settings(settings):
    """Merge into settings.OPPORTUNITIES, which does not exist yet."""

    def _set(**over):
        settings.OPPORTUNITIES = {
            "DEADLINE_NOTICE_DAYS": 3,
            "EXPORT_MAX_ROWS": 500,
            **getattr(settings, "OPPORTUNITIES", {}),
            **over,
        }

    return _set


@pytest.fixture
def suggestion_settings(settings):
    def _set(**over):
        settings.SUGGESTIONS = {"MIN_SCORE": 0, "MAX_RESULTS": 10, **getattr(settings, "SUGGESTIONS", {}), **over}

    return _set


@pytest.fixture
def rates(settings):
    def _set(**over):
        settings.REST_FRAMEWORK = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **over},
        }

    return _set


# ===========================================================================
# agents.md Phase 4 smoke test, step by step
# ===========================================================================


class TestPhase4Smoke:
    def test_step1_admin_creates_an_opportunity_that_is_open_at_once(self, as_admin, admin_user, company):
        """agents.md Phase 4 smoke step 1, and D28 (admin postings open at once)."""
        no_company = as_admin.post(url("opportunity-list"), opp_body(), format="json")
        assert no_company.status_code == 400  # contract: admin must send `company`
        opp = create_open(as_admin, company)
        assert opp["company"] in (str(company.id), company.name) or opp["company"]["id"] == str(company.id)
        assert opp["required_skills"] == ["python", "django", "postgresql"]
        row = model("opportunities", "Opportunity").objects.get(id=opp["id"])
        assert row.approved_by_id == admin_user.id and row.approved_at is not None

    def test_step2_the_matching_student_is_eligible_and_scores_above_the_other(
        self, as_admin, company, as_a, as_b, people
    ):
        """agents.md Phase 4 smoke step 2: matching student ranks higher and is eligible."""
        opp = create_open(as_admin, company)
        feed_a = {r["id"]: r for r in rows(as_a.get(url("opportunity-feed")))}[opp["id"]]
        feed_b = {r["id"]: r for r in rows(as_b.get(url("opportunity-feed")))}[opp["id"]]
        assert feed_a["eligible"] is True
        assert feed_b["eligible"] is False
        assert feed_a["score"] > feed_b["score"]
        assert "python" in [str(s).lower() for s in feed_a["matched_skills"]]
        assert isinstance(feed_a["missing_skills"], list) and "components" in feed_a

    def test_step2_the_feed_is_ordered_by_score_descending(self, as_admin, company, as_a):
        """agents.md Phase 4 smoke step 2, feed ordering (contract: feed)."""
        backend = create_open(as_admin, company)
        marketing = create_open(
            as_admin, company, title="Marketing Executive", description=MARKETING_JD,
            eligible_departments=[], min_cgpa=None, required_skills=["SEO"],
        )
        feed = rows(as_a.get(url("opportunity-feed")))
        scores = [r["score"] for r in feed]
        assert scores == sorted(scores, reverse=True)
        assert [r["id"] for r in feed][0] == backend["id"]
        assert marketing["id"] in [r["id"] for r in feed]

    def test_step3_the_matching_student_applies_and_gets_applied(self, as_admin, company, as_a, people):
        """agents.md Phase 4 smoke step 3."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        assert app["status"] == "applied"
        feed = {r["id"]: r for r in rows(as_a.get(url("opportunity-feed")))}[opp["id"]]
        assert feed["has_applied"] is True and feed["application_status"] == "applied"

    def test_step4_screening_excludes_the_non_matching_applicant(
        self, as_admin, company, as_a, as_c, people
    ):
        """agents.md Phase 4 smoke step 4: threshold plus minimum experience."""
        opp = create_open(as_admin, company)
        app_a = applied(as_a, opp["id"])
        app_c = applied(as_c, opp["id"])  # eligible, but a marketing resume
        response = as_admin.post(
            url("opportunity-screen", opp["id"]),
            {"threshold": 20, "min_experience_years": 2},
            format="json",
        )
        assert response.status_code == 200, response.content
        result = response.json()
        assert set(result) == {"shortlisted", "below_threshold", "filtered_out"}
        shortlisted = [r["application_id"] for r in result["shortlisted"]]
        assert app_a["id"] in shortlisted
        assert app_c["id"] not in shortlisted
        assert app_c["id"] in [r["application_id"] for r in result["filtered_out"] + result["below_threshold"]]
        row = result["shortlisted"][0]
        assert set(row) == {
            "application_id", "prn", "full_name", "score", "experience_years", "education_levels", "reasons",
        }

    def test_step5_shortlisting_is_visible_to_the_student(self, as_admin, company, as_a, people):
        """agents.md Phase 4 smoke step 5."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        assert move(as_admin, app["id"], "shortlisted").status_code == 200
        mine = as_a.get(url("application-detail", app["id"])).json()
        assert mine["status"] == "shortlisted"
        listed = rows(as_a.get(url("application-list")))
        assert [r["status"] for r in listed] == ["shortlisted"]

    def test_step6_the_export_has_the_prn_first_and_contains_the_applicant(
        self, as_admin, company, as_a, people
    ):
        """agents.md Phase 4 smoke step 6."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        response = as_admin.get(url("opportunity-applicants-export", opp["id"]))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        text = body_of(response).decode()
        assert text.splitlines()[0].split(",")[0] == "prn"
        assert text.splitlines()[0].split(",") == APPLICANT_COLUMNS
        assert text.splitlines()[1].split(",")[0] == "220200940"


# ===========================================================================
# Postings (Stage 2)
# ===========================================================================


class TestPostings:
    def test_a_recruiters_posting_is_a_draft_for_their_company(self, as_acme, company):
        """Contract: POST opportunity-list, recruiter -> draft."""
        opp = create_draft(as_acme)
        row = model("opportunities", "Opportunity").objects.get(id=opp["id"])
        assert row.company_id == company.id and row.status == "draft"

    def test_a_recruiter_cannot_post_for_another_company(self, as_acme, company, nimbus):
        """Contract: a recruiter acts for request.user.company."""
        response = as_acme.post(url("opportunity-list"), opp_body(nimbus), format="json")
        row = model("opportunities", "Opportunity").objects.get(id=response.json()["id"])
        assert row.company_id == company.id

    def test_submit_moves_a_draft_to_pending_review(self, as_acme):
        """Contract: submit, draft -> pending_review."""
        opp = make_pending(as_acme)
        row = model("opportunities", "Opportunity").objects.get(id=opp["id"])
        assert row.submitted_at is not None

    def test_a_pending_posting_is_invisible_to_students_until_approved(
        self, as_acme, as_admin, as_a, people
    ):
        """Stage 2: only `open` is visible to students, and approval makes it so."""
        opp = make_pending(as_acme)
        assert opp["id"] not in [r["id"] for r in rows(as_a.get(url("opportunity-list")))]
        assert as_a.get(url("opportunity-detail", opp["id"])).status_code == 404
        assert opp["id"] not in [r["id"] for r in rows(as_a.get(url("opportunity-feed")))]
        assert opp["id"] in [r["id"] for r in rows(as_acme.get(url("opportunity-list")))]
        assert as_admin.post(url("opportunity-approve", opp["id"])).status_code == 200
        assert opp["id"] in [r["id"] for r in rows(as_a.get(url("opportunity-list")))]
        assert as_a.get(url("opportunity-detail", opp["id"])).status_code == 200

    def test_approval_is_admin_only_and_records_who(self, as_acme, as_admin, admin_user):
        """Contract: approve, admin; approved_by recorded; audited."""
        opp = make_pending(as_acme)
        assert as_acme.post(url("opportunity-approve", opp["id"])).status_code == 403
        before = audit_count("opportunity_approved")
        response = as_admin.post(url("opportunity-approve", opp["id"]))
        assert response.status_code == 200 and response.json()["status"] == "open"
        row = model("opportunities", "Opportunity").objects.get(id=opp["id"])
        assert row.approved_by_id == admin_user.id
        assert audit_count("opportunity_approved") == before + 1

    def test_approving_a_draft_is_refused(self, as_acme, as_admin):
        """Contract: approve moves pending_review only."""
        opp = create_draft(as_acme)
        assert as_admin.post(url("opportunity-approve", opp["id"])).status_code == 400

    def test_rejection_needs_a_reason(self, as_acme, as_admin):
        """Contract: reject body `reason` is required."""
        opp = make_pending(as_acme)
        assert as_admin.post(url("opportunity-reject", opp["id"]), {}, format="json").status_code == 400
        assert as_admin.post(url("opportunity-reject", opp["id"]), {"reason": "  "}, format="json").status_code == 400
        response = as_admin.post(url("opportunity-reject", opp["id"]), {"reason": "Salary missing"}, format="json")
        assert response.status_code == 200 and response.json()["status"] == "rejected"
        row = model("opportunities", "Opportunity").objects.get(id=opp["id"])
        assert row.rejection_reason == "Salary missing"

    def test_a_rejected_posting_can_be_fixed_and_resubmitted(self, as_acme, as_admin):
        """Contract: PATCH in `rejected`, and submit from `rejected`."""
        opp = make_pending(as_acme)
        as_admin.post(url("opportunity-reject", opp["id"]), {"reason": "Fix it"}, format="json")
        patched = as_acme.patch(url("opportunity-detail", opp["id"]), {"title": "Fixed"}, format="json")
        assert patched.status_code == 200 and patched.json()["title"] == "Fixed"
        again = as_acme.post(url("opportunity-submit", opp["id"]))
        assert again.status_code == 200 and again.json()["status"] == "pending_review"

    def test_a_recruiter_cannot_edit_a_posting_that_is_pending_or_open(self, as_acme, as_admin):
        """Contract: a recruiter may PATCH only in draft or rejected."""
        opp = make_pending(as_acme)
        assert as_acme.patch(url("opportunity-detail", opp["id"]), {"title": "X"}, format="json").status_code == 400
        as_admin.post(url("opportunity-approve", opp["id"]))
        assert as_acme.patch(url("opportunity-detail", opp["id"]), {"title": "X"}, format="json").status_code == 400

    def test_an_admin_can_edit_any_status_but_closed(self, as_admin, company):
        """Contract: admin PATCH, any status but closed."""
        opp = create_open(as_admin, company)
        assert as_admin.patch(url("opportunity-detail", opp["id"]), {"title": "New"}, format="json").status_code == 200
        as_admin.post(url("opportunity-close", opp["id"]))
        assert as_admin.patch(url("opportunity-detail", opp["id"]), {"title": "Again"}, format="json").status_code == 400

    def test_a_recruiter_cannot_see_or_edit_another_companys_posting(self, as_acme, as_nimbus):
        """Contract: an object outside the caller's scope is a 404."""
        opp = create_draft(as_acme)
        assert as_nimbus.get(url("opportunity-detail", opp["id"])).status_code == 404
        assert as_nimbus.patch(url("opportunity-detail", opp["id"]), {"title": "X"}, format="json").status_code == 404
        assert as_nimbus.delete(url("opportunity-detail", opp["id"])).status_code == 404
        assert as_nimbus.post(url("opportunity-submit", opp["id"])).status_code == 404
        assert as_nimbus.post(url("opportunity-close", opp["id"])).status_code == 404
        assert opp["id"] not in [r["id"] for r in rows(as_nimbus.get(url("opportunity-list")))]

    def test_a_recruiter_with_no_company_gets_403_on_every_company_action(self, as_bare, as_acme):
        """Contract: a recruiter with no company gets 403."""
        opp = create_draft(as_acme)
        assert as_bare.get(url("opportunity-list")).status_code == 403
        assert as_bare.post(url("opportunity-list"), opp_body(), format="json").status_code == 403
        assert as_bare.post(url("opportunity-submit", opp["id"])).status_code in (403, 404)

    def test_only_a_draft_can_be_deleted(self, as_acme, as_admin, company):
        """Contract: DELETE is draft only, otherwise 400."""
        draft = create_draft(as_acme)
        assert as_acme.delete(url("opportunity-detail", draft["id"])).status_code == 204
        pending = make_pending(as_acme)
        assert as_acme.delete(url("opportunity-detail", pending["id"])).status_code == 400
        open_opp = create_open(as_admin, company)
        assert as_admin.delete(url("opportunity-detail", open_opp["id"])).status_code == 400

    def test_close_moves_open_to_closed_and_only_open(self, as_admin, as_acme, company):
        """Contract: close, open -> closed."""
        draft = create_draft(as_acme)
        assert as_acme.post(url("opportunity-close", draft["id"])).status_code == 400
        opp = create_open(as_admin, company)
        response = as_acme.post(url("opportunity-close", opp["id"]))
        assert response.status_code == 200 and response.json()["status"] == "closed"

    def test_a_closed_posting_leaves_the_students_feed(self, as_admin, company, as_a, people):
        """Contract: feed shows open postings only."""
        opp = create_open(as_admin, company)
        as_admin.post(url("opportunity-close", opp["id"]))
        assert opp["id"] not in [r["id"] for r in rows(as_a.get(url("opportunity-feed")))]

    def test_the_feed_hides_postings_past_their_deadline(self, as_admin, company, as_a, people):
        """Contract: feed, deadline today or later."""
        create_open(as_admin, company)
        past = orm_opportunity(company, deadline=today() - timedelta(days=1))
        edge = orm_opportunity(company, deadline=today())
        ids = [r["id"] for r in rows(as_a.get(url("opportunity-feed")))]
        assert str(past.id) not in ids and str(edge.id) in ids

    def test_salary_is_null_when_not_disclosed_and_max_must_not_undercut_min(self, as_admin, company):
        """Contract: salary_disclosed false nulls the salary; max >= min."""
        hidden = as_admin.post(
            url("opportunity-list"), opp_body(company, salary_disclosed=False), format="json"
        )
        assert hidden.status_code == 201
        assert hidden.json()["salary_min"] is None and hidden.json()["salary_max"] is None
        bad = as_admin.post(
            url("opportunity-list"), opp_body(company, salary_min=70000, salary_max=50000), format="json"
        )
        assert bad.status_code == 400

    def test_list_filters_work_and_an_unknown_parameter_is_400(self, as_admin, company, nimbus):
        """Contract: ?status= ?role_type= ?company_id= ?search=, unknown -> 400."""
        create_open(as_admin, company, title="Zebra Engineer")
        create_open(as_admin, nimbus, role_type="internship", title="Intern Role")
        listing = url("opportunity-list")
        assert len(rows(as_admin.get(listing, {"status": "open"}))) == 2
        assert len(rows(as_admin.get(listing, {"status": "draft"}))) == 0
        assert [r["title"] for r in rows(as_admin.get(listing, {"role_type": "internship"}))] == ["Intern Role"]
        assert [r["title"] for r in rows(as_admin.get(listing, {"search": "zebra"}))] == ["Zebra Engineer"]
        assert len(rows(as_admin.get(listing, {"company_id": str(nimbus.id)}))) == 1
        assert as_admin.get(listing, {"colour": "red"}).status_code == 400

    def test_a_student_cannot_create_or_submit_postings(self, as_a, as_acme, people):
        """Contract: POST opportunity-list is recruiter and admin only."""
        assert as_a.post(url("opportunity-list"), opp_body(), format="json").status_code == 403
        opp = create_draft(as_acme)
        assert as_a.post(url("opportunity-submit", opp["id"])).status_code in (403, 404)


# ===========================================================================
# Apply
# ===========================================================================


class TestApply:
    def test_applying_creates_the_application_and_the_shortlist_link(
        self, as_admin, company, as_a, people
    ):
        """NEXT_PHASES test 2 and D27: apply creates CompanyShortlist source=application."""
        opp = create_open(as_admin, company)
        before = audit_count("application_created")
        app = applied(as_a, opp["id"])
        assert app["status"] == "applied"
        assert isinstance(app["score"], int) and 0 <= app["score"] <= 100
        row = shortlist_row(company, people.a)
        assert row is not None and row.source == "application"
        assert audit_count("application_created") == before + 1

    def test_the_snapshot_freezes_roster_facts_and_uses_the_roster_cgpa(
        self, as_admin, company, as_a, people
    ):
        """Contract: cgpa_at_apply is the roster CGPA, never confirmed_cgpa."""
        people.a.confirmed_cgpa = Decimal("9.90")
        people.a.save()
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        row = model("opportunities", "Application").objects.get(id=app["id"])
        assert row.cgpa_at_apply == Decimal("8.50")
        assert row.department == CS and row.programme == CS
        assert row.school == "computing_data_science"
        assert row.batch == 2026 and row.year_of_study == 4
        assert row.prn == "220200940" and row.full_name == "Aditi Verma"
        assert row.eligible is True

    def test_the_resume_is_copied_at_apply_time(self, as_admin, company, as_a, people):
        """Stage 2: resume_snapshot is a copy, so later edits do not rewrite it."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        row = model("opportunities", "Application").objects.get(id=app["id"])
        with people.a.resume.open("rb") as current:
            original = current.read()
        assert row.resume_snapshot_filename == people.a.resume_filename
        assert row.resume_snapshot.name != people.a.resume.name
        with row.resume_snapshot.open("rb") as snap:
            assert snap.read() == original

    def test_a_programme_change_after_applying_leaves_the_snapshot_alone(
        self, as_admin, company, as_a, people
    ):
        """NEXT_PHASES test 8, G16."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        people.a.student.programme = DS
        people.a.student.department = DS
        people.a.student.school = "somewhere_else"
        people.a.student.cgpa = Decimal("5.00")
        people.a.student.save()
        row = model("opportunities", "Application").objects.get(id=app["id"])
        assert (row.department, row.programme, row.school) == (CS, CS, "computing_data_science")
        assert row.cgpa_at_apply == Decimal("8.50")
        assert as_admin.get(url("application-detail", app["id"])).json()["programme"] == CS

    def test_refused_when_the_posting_is_not_open(self, as_admin, company, as_a, people):
        """Contract: reason not_open."""
        closed = orm_opportunity(company, status="closed")
        response = apply_to(as_a, closed.id)
        assert response.status_code == 400
        assert response.json()["reason"] == "not_open" and response.json()["detail"]
        assert model("opportunities", "Application").objects.count() == 0

    def test_a_draft_or_pending_posting_is_not_even_visible_to_apply_to(self, as_acme, as_a, people):
        """Contract: students see open postings only (404 outside scope)."""
        pending = make_pending(as_acme)
        assert apply_to(as_a, pending["id"]).status_code == 404

    def test_refused_after_the_deadline(self, company, as_a, people):
        """Contract: reason deadline_passed."""
        late = orm_opportunity(company, deadline=today() - timedelta(days=1))
        response = apply_to(as_a, late.id)
        assert response.status_code == 400 and response.json()["reason"] == "deadline_passed"

    def test_refused_when_already_applied(self, as_admin, company, as_a, people):
        """Contract: reason already_applied, one row per (opportunity, profile)."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        response = apply_to(as_a, opp["id"])
        assert response.status_code == 400 and response.json()["reason"] == "already_applied"
        assert model("opportunities", "Application").objects.count() == 1

    def test_refused_without_a_resume(self, as_admin, company, as_d, people):
        """Contract: reason no_resume."""
        opp = create_open(as_admin, company)
        response = apply_to(as_d, opp["id"])
        assert response.status_code == 400 and response.json()["reason"] == "no_resume"

    def test_refused_for_the_wrong_department(self, as_admin, company, as_b, people):
        """Contract: reason not_eligible, department."""
        opp = create_open(as_admin, company)
        response = apply_to(as_b, opp["id"])
        assert response.status_code == 400 and response.json()["reason"] == "not_eligible"
        assert model("opportunities", "Application").objects.count() == 0

    def test_refused_for_a_roster_cgpa_below_the_cutoff(self, as_admin, company, as_e, people):
        """Contract: reason not_eligible, CGPA, from the roster only."""
        people.e.confirmed_cgpa = Decimal("9.50")  # a typed-in or transcript value must not help
        people.e.save()
        opp = create_open(as_admin, company)
        response = apply_to(as_e, opp["id"])
        assert response.status_code == 400 and response.json()["reason"] == "not_eligible"

    def test_a_student_failing_only_the_experience_minimum_can_still_apply(
        self, as_admin, company, as_c, people
    ):
        """D28: experience is a screening filter, not an apply block."""
        opp = create_open(as_admin, company, min_experience_years="10.0")
        response = apply_to(as_c, opp["id"])
        assert response.status_code == 201, response.content
        assert response.json()["eligible"] is True

    def test_only_students_can_apply(self, as_admin, company, as_acme, people):
        """Contract: apply is student-only."""
        opp = create_open(as_admin, company)
        assert apply_to(as_acme, opp["id"]).status_code == 403
        assert apply_to(as_admin, opp["id"]).status_code == 403

    def test_an_anonymous_caller_cannot_apply(self, as_admin, company, anon, people):
        """Contract: an anonymous caller gets 401."""
        opp = create_open(as_admin, company)
        assert apply_to(anon, opp["id"]).status_code == 401


# ===========================================================================
# D27 shortlist semantics
# ===========================================================================


class TestShortlistSemantics:
    def test_withdraw_sets_withdrawn_keeps_the_application_and_removes_the_grant(
        self, as_admin, company, as_a, people
    ):
        """D27: withdraw removes an application-sourced row, never the application."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        before = audit_count("application_withdrawn")
        response = as_a.post(url("application-withdraw", app["id"]))
        assert response.status_code == 200 and response.json()["status"] == "withdrawn"
        row = model("opportunities", "Application").objects.get(id=app["id"])
        assert row.status == "withdrawn"
        assert shortlist_row(company, people.a) is None
        assert audit_count("application_withdrawn") == before + 1
        events = model("opportunities", "ApplicationEvent").objects.filter(application=row)
        assert events.filter(to_status="withdrawn").exists()

    def test_withdraw_keeps_a_manual_row(self, as_admin, as_acme, company, as_a, people):
        """D27: only an application-sourced row is deleted on withdraw."""
        assert as_acme.post(url("company-profile-shortlist", people.a.student_id)).status_code == 201
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        assert shortlist_row(company, people.a).source == "manual"
        as_a.post(url("application-withdraw", app["id"]))
        assert shortlist_row(company, people.a).source == "manual"

    def test_withdraw_keeps_the_row_while_another_application_is_active(
        self, as_admin, company, as_a, people
    ):
        """D27: deleted only if there is no other non-withdrawn application to that company."""
        first = create_open(as_admin, company, title="First")
        second = create_open(as_admin, company, title="Second")
        app1 = applied(as_a, first["id"])
        app2 = applied(as_a, second["id"])
        as_a.post(url("application-withdraw", app1["id"]))
        assert shortlist_row(company, people.a) is not None
        as_a.post(url("application-withdraw", app2["id"]))
        assert shortlist_row(company, people.a) is None

    def test_only_the_applicant_can_withdraw(self, as_admin, company, as_a, as_c, as_acme, people):
        """Contract: withdraw is the student who applied."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        assert as_c.post(url("application-withdraw", app["id"])).status_code == 404
        assert as_acme.post(url("application-withdraw", app["id"])).status_code in (403, 404)
        assert as_admin.post(url("application-withdraw", app["id"])).status_code in (403, 404)

    def test_withdrawing_from_a_final_status_is_400(self, as_admin, company, as_a, as_c, people):
        """Contract: withdraw from a final status is 400."""
        opp = create_open(as_admin, company)
        offered = applied(as_a, opp["id"])
        walk(as_admin, offered["id"], "shortlisted", "interview", "offer")
        assert as_a.post(url("application-withdraw", offered["id"])).status_code == 400
        rejected = applied(as_c, opp["id"])
        walk(as_admin, rejected["id"], "rejected")
        assert as_c.post(url("application-withdraw", rejected["id"])).status_code == 400
        again = applied(as_a, create_open(as_admin, company, title="Other")["id"])
        assert as_a.post(url("application-withdraw", again["id"])).status_code == 200
        assert as_a.post(url("application-withdraw", again["id"])).status_code == 400

    def test_a_withdrawable_status_set_is_applied_shortlisted_interview(
        self, as_admin, company, as_a, people
    ):
        """Contract: withdraw from applied, shortlisted or interview."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        walk(as_admin, app["id"], "shortlisted", "interview")
        assert as_a.post(url("application-withdraw", app["id"])).status_code == 200

    def test_a_manual_shortlist_upgrades_an_application_row(self, as_admin, as_acme, company, as_a, people):
        """D27: POST shortlist is update_or_create(source=manual)."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        assert shortlist_row(company, people.a).source == "application"
        assert as_acme.post(url("company-profile-shortlist", people.a.student_id)).status_code == 201
        assert shortlist_row(company, people.a).source == "manual"

    def test_applying_after_a_manual_shortlist_leaves_the_manual_row(
        self, as_admin, as_acme, company, as_a, people
    ):
        """D27: an existing manual row is left as is on apply."""
        as_acme.post(url("company-profile-shortlist", people.a.student_id))
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        assert shortlist_row(company, people.a).source == "manual"

    def test_unshortlisting_an_active_applicant_keeps_them_visible(
        self, as_admin, as_acme, company, as_a, people
    ):
        """D27: DELETE downgrades to source=application when an application is active."""
        people.a.visibility = "shortlisted"
        people.a.save()
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        as_acme.post(url("company-profile-shortlist", people.a.student_id))
        assert as_acme.delete(url("company-profile-shortlist", people.a.student_id)).status_code == 204
        assert shortlist_row(company, people.a).source == "application"
        assert as_acme.get(url("company-profile-detail", people.a.student_id)).status_code == 200

    def test_unshortlisting_a_non_applicant_deletes_the_row(self, as_acme, as_admin, company, people):
        """D27: otherwise the row is deleted."""
        create_open(as_admin, company)  # the opportunity routes must exist for this gate
        people.d.visibility = "shortlisted"
        people.d.save()
        model("profiles", "CompanyShortlist").objects.create(company=company, profile=people.d, source="manual")
        assert as_acme.delete(url("company-profile-shortlist", people.d.student_id)).status_code == 204
        assert shortlist_row(company, people.d) is None
        assert as_acme.get(url("company-profile-detail", people.d.student_id)).status_code == 404

    def test_shortlisted_only_becomes_visible_to_the_applied_company_and_no_other(
        self, as_admin, as_acme, as_nimbus, company, nimbus, as_a, people
    ):
        """D27 and Phase B box 1: applying reaches the company applied to, and no one else."""
        people.a.visibility = "shortlisted"
        people.a.save()
        detail = url("company-profile-detail", people.a.student_id)
        opp = create_open(as_admin, company)
        assert as_acme.get(detail).status_code == 404
        applied(as_a, opp["id"])
        assert as_acme.get(detail).status_code == 200
        assert as_nimbus.get(detail).status_code == 404
        # The other fixture students are public, so the list is not empty;
        # the "shortlisted only" student is simply not in it.
        assert people.a.prn not in [r["prn"] for r in rows(as_nimbus.get(url("company-profile-list")))]

    def test_a_bare_application_is_not_a_pick(self, as_admin, as_acme, company, as_a, people):
        """D27: is_shortlisted follows the shortlist definition, not the grant row."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        detail = url("company-profile-detail", people.a.student_id)
        assert as_acme.get(detail).json()["is_shortlisted"] is False
        move(as_admin, app["id"], "shortlisted")
        assert as_acme.get(detail).json()["is_shortlisted"] is True


# ===========================================================================
# D28 hidden student
# ===========================================================================


class TestHiddenStudent:
    def test_a_hidden_student_may_apply_and_the_company_sees_the_application_only(
        self, as_admin, as_acme, company, as_a, people
    ):
        """D28: hidden students may apply; the company sees the application, not the profile."""
        people.a.visibility = "hidden"
        people.a.save()
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        seen = rows(as_acme.get(url("application-list")))
        assert [r["id"] for r in seen] == [app["id"]]
        assert seen[0]["prn"] == "220200940" and seen[0]["resume_url"]
        assert as_acme.get(url("application-detail", app["id"])).status_code == 200
        assert as_acme.get(url("application-resume", app["id"])).status_code == 200

    def test_the_company_cannot_browse_or_search_the_hidden_profile(
        self, as_admin, as_acme, company, as_a, people
    ):
        """D28: browse, search and detail follow visible_to, which excludes hidden."""
        people.a.visibility = "hidden"
        people.a.save()
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        listing = url("company-profile-list")
        assert "220200940" not in [r["prn"] for r in rows(as_acme.get(listing))]
        assert rows(as_acme.get(listing, {"search": "Aditi"})) == []
        assert as_acme.get(url("company-profile-detail", people.a.student_id)).status_code == 404
        search = as_acme.post(
            reverse("matching-search"), {"jd_text": opp["description"]}, format="json"
        )
        assert "220200940" not in json.dumps(search.json())


# ===========================================================================
# The company payload is an allow-list
# ===========================================================================


class TestCompanyPayload:
    @pytest.fixture
    def seeded(self, as_admin, company, as_a, people):
        people.a.confirmed_cgpa = Decimal("9.90")
        people.a.parsed_cgpa = Decimal("9.80")
        people.a.recomputed_cgpa = Decimal("9.70")
        people.a.career_path = "business"
        people.a.personal_email = "aditi.private@example.org"
        people.a.also_attending_placements = True
        people.a.save()
        opp = create_open(as_admin, company)
        return SimpleNamespace(opp=opp, app=applied(as_a, opp["id"]))

    def test_the_company_list_and_detail_hold_only_the_allowed_keys(self, as_acme, seeded):
        """Contract: company application payload, nothing else."""
        listed = rows(as_acme.get(url("application-list")))[0]
        detail = as_acme.get(url("application-detail", seeded.app["id"])).json()
        for payload in (listed, detail):
            assert_allow_list(payload)
            assert set(payload) <= COMPANY_APPLICATION_KEYS
            assert set(payload["opportunity"]) == {"id", "title"}
            text = json.dumps(payload)
            assert "9.90" not in text and "aditi.private@example.org" not in text

    def test_contact_is_null_while_the_profile_is_unverified(self, as_acme, seeded):
        """Contract: contact only when is_verified, else null with contact_available false."""
        payload = as_acme.get(url("application-detail", seeded.app["id"])).json()
        assert payload["contact"] is None and payload["contact_available"] is False

    def test_contact_appears_once_the_profile_is_verified(self, as_acme, admin_user, people, seeded):
        """Contract: verified profiles expose {email, phone}."""
        people.a.mark_verified(admin_user)
        payload = as_acme.get(url("application-detail", seeded.app["id"])).json()
        assert payload["contact_available"] is True
        assert payload["contact"] == {"email": "220200940@college.edu", "phone": people.a.phone}

    def test_the_students_own_payload_adds_events_and_the_admins_adds_the_profile_id(
        self, as_a, as_admin, people, seeded
    ):
        """Contract: student adds `events`, admin adds `profile_student_id`."""
        mine = as_a.get(url("application-detail", seeded.app["id"])).json()
        assert [e["to_status"] for e in mine["events"]] == ["applied"]
        theirs = as_admin.get(url("application-detail", seeded.app["id"])).json()
        assert theirs["profile_student_id"] == str(people.a.student_id)

    def test_the_resume_is_the_snapshot_and_company_opens_are_audited(
        self, as_acme, as_a, as_c, as_nimbus, people, seeded
    ):
        """Contract: application-resume serves the snapshot; company opens are document_accessed."""
        row = model("opportunities", "Application").objects.get(id=seeded.app["id"])
        with row.resume_snapshot.open("rb") as snap:
            expected = snap.read()
        before = audit_count("document_accessed")
        response = as_acme.get(url("application-resume", seeded.app["id"]))
        assert response.status_code == 200 and body_of(response) == expected
        assert audit_count("document_accessed") == before + 1
        assert as_a.get(url("application-resume", seeded.app["id"])).status_code == 200
        assert as_c.get(url("application-resume", seeded.app["id"])).status_code == 404
        assert as_nimbus.get(url("application-resume", seeded.app["id"])).status_code == 404

    def test_another_company_cannot_read_or_move_the_application(self, as_nimbus, as_c, seeded):
        """NEXT_PHASES test 6: company B gets 404 on company A's applications."""
        assert as_nimbus.get(url("application-detail", seeded.app["id"])).status_code == 404
        assert rows(as_nimbus.get(url("application-list"))) == []
        assert move(as_nimbus, seeded.app["id"], "shortlisted").status_code == 404
        assert as_c.get(url("application-detail", seeded.app["id"])).status_code == 404

    def test_a_student_sees_only_their_own_applications(self, as_a, as_c, as_admin, company, people, seeded):
        """Contract: application-list is own only for students."""
        applied(as_c, create_open(as_admin, company, title="Second")["id"])
        mine = rows(as_a.get(url("application-list")))
        assert [r["prn"] for r in mine] == ["220200940"]
        assert len(rows(as_admin.get(url("application-list")))) == 2


# ===========================================================================
# Status transitions
# ===========================================================================


class TestStatusTransitions:
    @pytest.fixture
    def app(self, as_admin, company, as_a, people):
        opp = create_open(as_admin, company)
        return applied(as_a, opp["id"])

    def test_creating_an_application_writes_the_first_event(self, app, people):
        """Contract: an event on create, '' -> applied."""
        event = model("opportunities", "ApplicationEvent").objects.get(application_id=app["id"])
        assert (event.from_status, event.to_status) == ("", "applied")

    def test_every_valid_move_writes_an_event_and_an_audit_row(self, as_admin, admin_user, app):
        """Contract: valid moves write an ApplicationEvent and an audit row."""
        events = model("opportunities", "ApplicationEvent").objects.filter(application_id=app["id"])
        before = audit_count("application_status_changed")
        chain = [("applied", "shortlisted"), ("shortlisted", "interview"), ("interview", "offer")]
        for old, new in chain:
            assert move(as_admin, app["id"], new, note=f"to {new}").status_code == 200
            event = events.order_by("-created_at").first()
            assert (event.from_status, event.to_status, event.note) == (old, new, f"to {new}")
            assert event.actor_id == admin_user.id
        assert audit_count("application_status_changed") == before + 3

    def test_rejection_is_allowed_from_each_active_status(self, as_admin, company, as_a, as_c, as_e, people):
        """Contract: applied, shortlisted and interview may each go to rejected."""
        opp = create_open(as_admin, company, min_cgpa=None)
        first = applied(as_a, opp["id"])
        second = applied(as_c, opp["id"])
        third = applied(as_e, opp["id"])
        walk(as_admin, first["id"], "rejected")
        walk(as_admin, second["id"], "shortlisted", "rejected")
        walk(as_admin, third["id"], "shortlisted", "interview", "rejected")

    @pytest.mark.parametrize(
        "path, bad",
        [
            ((), "offer"),
            ((), "interview"),
            ((), "withdrawn"),
            ((), "applied"),
            (("shortlisted",), "offer"),
            (("shortlisted",), "applied"),
            (("shortlisted", "interview"), "shortlisted"),
            (("rejected",), "shortlisted"),
            (("shortlisted", "interview", "offer"), "rejected"),
            ((), "nonsense"),
        ],
    )
    def test_an_invalid_move_is_400_and_writes_nothing(self, as_admin, app, path, bad):
        """Contract: anything outside the allowed transitions is 400."""
        walk(as_admin, app["id"], *path)
        events = model("opportunities", "ApplicationEvent").objects.filter(application_id=app["id"])
        count = events.count()
        assert move(as_admin, app["id"], bad).status_code == 400
        assert events.count() == count

    def test_the_student_cannot_change_status_and_sees_the_new_one(self, as_a, as_acme, app):
        """NEXT_PHASES test 4: owner moves it, the student sees it and the event."""
        assert move(as_a, app["id"], "shortlisted").status_code == 403
        assert move(as_acme, app["id"], "shortlisted", note="Good fit").status_code == 200
        mine = as_a.get(url("application-detail", app["id"])).json()
        assert mine["status"] == "shortlisted"
        assert [e["to_status"] for e in mine["events"]] == ["applied", "shortlisted"]

    def test_a_withdrawn_application_cannot_be_moved(self, as_admin, as_a, app):
        """Contract: withdrawn is not a state the company can move."""
        as_a.post(url("application-withdraw", app["id"]))
        assert move(as_admin, app["id"], "shortlisted").status_code == 400


# ===========================================================================
# Eligibility is a flag, separate from the score
# ===========================================================================


class TestEligibility:
    def test_an_ineligible_student_still_has_a_score(self, as_admin, company, as_b, people):
        """D28: the score is computed and shown whatever the eligibility."""
        opp = create_open(as_admin, company)
        row = {r["id"]: r for r in rows(as_b.get(url("opportunity-feed")))}[opp["id"]]
        assert row["eligible"] is False
        assert isinstance(row["score"], int) and 0 <= row["score"] <= 100
        assert row["eligibility_reasons"] and all(isinstance(r, str) and r for r in row["eligibility_reasons"])
        assert any("department" in r.lower() or "programme" in r.lower() for r in row["eligibility_reasons"])

    def test_a_cgpa_failure_is_named_in_plain_words(self, as_admin, company, as_e, people):
        """Contract: eligibility_reasons names each failure."""
        opp = create_open(as_admin, company)
        row = {r["id"]: r for r in rows(as_e.get(url("opportunity-feed")))}[opp["id"]]
        assert row["eligible"] is False and row["score"] is not None
        assert any("cgpa" in r.lower() for r in row["eligibility_reasons"])

    def test_the_roster_cgpa_decides_not_a_confirmed_one(self, as_admin, company, as_e, people):
        """Contract and D24: confirmed_cgpa never feeds eligibility."""
        people.e.confirmed_cgpa = Decimal("9.90")
        people.e.save()
        opp = create_open(as_admin, company)
        row = {r["id"]: r for r in rows(as_e.get(url("opportunity-feed")))}[opp["id"]]
        assert row["eligible"] is False

    def test_empty_departments_and_a_null_cutoff_pass_everyone(self, as_admin, company, as_b, people):
        """Contract: empty eligible_departments means all, null min_cgpa passes."""
        opp = create_open(as_admin, company, eligible_departments=[], min_cgpa=None)
        row = {r["id"]: r for r in rows(as_b.get(url("opportunity-feed")))}[opp["id"]]
        assert row["eligible"] is True and row["eligibility_reasons"] == []

    def test_a_null_roster_cgpa_fails_a_non_null_cutoff(self, as_admin, company, as_c, people):
        """Contract: a null roster CGPA fails a non-null cutoff."""
        people.c.student.cgpa = None
        people.c.student.save()
        opp = create_open(as_admin, company)
        row = {r["id"]: r for r in rows(as_c.get(url("opportunity-feed")))}[opp["id"]]
        assert row["eligible"] is False
        assert apply_to(as_c, opp["id"]).json()["reason"] == "not_eligible"

    def test_failing_only_experience_leaves_a_student_eligible(self, as_admin, company, as_c, people):
        """D28: experience is a screening filter and never touches `eligible`."""
        opp = create_open(as_admin, company, min_experience_years="20.0")
        row = {r["id"]: r for r in rows(as_c.get(url("opportunity-feed")))}[opp["id"]]
        assert row["eligible"] is True


# ===========================================================================
# Ranking is backend independent
# ===========================================================================


@pytest.fixture(params=["spacy", "tfidf"])
def each_backend(request, settings):
    """Run the test on one MATCHING_BACKEND, as test_match_score's each_engine does."""
    from matching.backends import get_backend
    from matching.engine import reset_engine

    try:
        backend = get_backend(request.param)
    except (ImportError, RuntimeError, OSError):
        pytest.skip(f"the {request.param} backend is not installed here")
    if backend.name != request.param:
        pytest.skip(f"the {request.param} backend is not installed here")
    settings.MATCHING = {**settings.MATCHING, "BACKEND": request.param}
    reset_engine()
    yield request.param
    reset_engine()


class TestRankingOnEachBackend:
    def test_the_matching_student_outranks_the_other_on_each_backend(
        self, each_backend, as_admin, company, as_a, as_b, as_c, people
    ):
        """Phase B box 3 and Stage 2 tests: ranking holds on spaCy and on TF-IDF."""
        backend = create_open(as_admin, company)
        marketing = create_open(
            as_admin, company, title="Marketing Executive", description=MARKETING_JD,
            eligible_departments=[], min_cgpa=None, required_skills=["SEO"],
        )

        def by_id(client):
            return {r["id"]: r for r in rows(client.get(url("opportunity-feed")))}

        a, b, c = by_id(as_a), by_id(as_b), by_id(as_c)
        assert a[backend["id"]]["score"] > b[backend["id"]]["score"]
        assert a[backend["id"]]["score"] > c[backend["id"]]["score"]
        assert a[backend["id"]]["eligible"] and not b[backend["id"]]["eligible"]
        assert c[marketing["id"]]["score"] > a[marketing["id"]]["score"]
        assert [r["id"] for r in rows(as_a.get(url("opportunity-feed")))][0] == backend["id"]
        assert [r["id"] for r in rows(as_c.get(url("opportunity-feed")))][0] == marketing["id"]


# ===========================================================================
# Screening and exports of one posting's applicants
# ===========================================================================


class TestScreening:
    @pytest.fixture
    def pool(self, as_admin, company, as_a, as_c, people):
        opp = create_open(as_admin, company)
        return SimpleNamespace(opp=opp, a=applied(as_a, opp["id"]), c=applied(as_c, opp["id"]))

    def test_the_request_value_wins_over_the_postings(self, as_admin, pool):
        """Contract: request > posting > settings, so a zero minimum lets the junior through."""
        result = as_admin.post(
            url("opportunity-screen", pool.opp["id"]),
            {"threshold": 0, "min_experience_years": 0, "required_education_levels": []},
            format="json",
        ).json()
        assert {r["application_id"] for r in result["shortlisted"]} == {pool.a["id"], pool.c["id"]}
        assert result["filtered_out"] == []

    def test_the_postings_own_minimum_applies_when_the_request_names_none(self, as_admin, pool):
        """Contract: posting min_experience_years is the fallback (2.0 here)."""
        result = as_admin.post(url("opportunity-screen", pool.opp["id"]), {"threshold": 0}, format="json").json()
        assert pool.c["id"] in [r["application_id"] for r in result["filtered_out"]]
        assert pool.a["id"] in [r["application_id"] for r in result["shortlisted"]]

    def test_a_threshold_of_100_leaves_nobody_shortlisted(self, as_admin, pool):
        """Contract: below_threshold holds those under the cut."""
        result = as_admin.post(
            url("opportunity-screen", pool.opp["id"]),
            {"threshold": 100, "min_experience_years": 0},
            format="json",
        ).json()
        assert result["shortlisted"] == []
        assert len(result["below_threshold"]) == 2

    def test_the_posting_threshold_is_used_when_the_request_names_none(self, as_admin, company, as_a, people):
        """Contract: posting similarity_threshold beats the settings default."""
        opp = create_open(as_admin, company, similarity_threshold=100, min_experience_years=None)
        app = applied(as_a, opp["id"])
        result = as_admin.post(url("opportunity-screen", opp["id"]), {}, format="json").json()
        assert app["id"] in [r["application_id"] for r in result["below_threshold"]]

    def test_screening_reads_the_resume_snapshot_not_the_current_resume(
        self, as_admin, as_a, people, pool, tmp_path
    ):
        """Contract: screen runs over the applicants' resume snapshots."""
        _upload_resume(people.a, tmp_path, "marketing_executive")
        result = as_admin.post(
            url("opportunity-screen", pool.opp["id"]),
            {"threshold": 20, "min_experience_years": 2},
            format="json",
        ).json()
        assert pool.a["id"] in [r["application_id"] for r in result["shortlisted"]]

    def test_only_the_owner_company_or_an_admin_may_screen(self, as_acme, as_nimbus, as_a, pool):
        """Contract: screen is owner company and admin; others 404."""
        assert as_acme.post(url("opportunity-screen", pool.opp["id"]), {}, format="json").status_code == 200
        assert as_nimbus.post(url("opportunity-screen", pool.opp["id"]), {}, format="json").status_code == 404
        assert as_a.post(url("opportunity-screen", pool.opp["id"]), {}, format="json").status_code == 403

    def test_screening_is_throttled_on_the_matching_scope(self, as_admin, pool, rates):
        """Contract: screen uses MatchingThrottle."""
        rates(matching="1/hour")
        body = {"threshold": 0}
        assert as_admin.post(url("opportunity-screen", pool.opp["id"]), body, format="json").status_code == 200
        assert as_admin.post(url("opportunity-screen", pool.opp["id"]), body, format="json").status_code == 429


class TestApplicantsExport:
    def test_the_csv_has_the_contract_columns_sorted_by_score_then_prn(
        self, as_admin, as_acme, company, as_a, as_c, people
    ):
        """Contract: columns, PRN first, sorted by score desc then PRN."""
        opp = create_open(as_admin, company)
        app_a, app_c = applied(as_a, opp["id"]), applied(as_c, opp["id"])
        response = as_acme.get(url("opportunity-applicants-export", opp["id"]))
        assert response.status_code == 200
        parsed = csv_rows(response)
        assert list(parsed[0].keys()) == APPLICANT_COLUMNS
        scores = [int(r["score"]) for r in parsed]
        assert scores == sorted(scores, reverse=True)
        assert {r["prn"] for r in parsed} == {"220200940", "220200942"}
        assert {r["cgpa_at_apply"] for r in parsed} == {"8.50", "7.50"}
        assert app_a["id"] and app_c["id"]

    def test_unverified_applicants_have_blank_contacts(self, as_admin, company, as_a, people):
        """Contract: contact only when verified, contact_available false otherwise."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        row = csv_rows(as_admin.get(url("opportunity-applicants-export", opp["id"])))[0]
        assert row["email"] == "" and row["phone"] == "" and row["contact_available"].lower() == "false"

    def test_verified_applicants_carry_their_contacts(self, as_admin, admin_user, company, as_a, people):
        """Contract: verified profiles expose email and phone."""
        people.a.mark_verified(admin_user)
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        row = csv_rows(as_admin.get(url("opportunity-applicants-export", opp["id"])))[0]
        assert row["email"] == "220200940@college.edu" and row["phone"] == people.a.phone
        assert row["contact_available"].lower() == "true"

    def test_the_export_is_audited(self, as_admin, company, as_a, people):
        """Contract: audited as applications_exported."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        before = audit_count("applications_exported")
        as_admin.get(url("opportunity-applicants-export", opp["id"]))
        assert audit_count("applications_exported") == before + 1

    def test_another_company_and_students_cannot_export(self, as_admin, as_nimbus, as_a, company, people):
        """Contract: owner company and admin only; other company 404."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        assert as_nimbus.get(url("opportunity-applicants-export", opp["id"])).status_code == 404
        assert as_a.get(url("opportunity-applicants-export", opp["id"])).status_code == 403


# ===========================================================================
# Admin stats
# ===========================================================================


class TestAdminStats:
    def test_stats_has_the_contract_keys_and_the_seeded_counts(
        self, as_admin, as_acme, company, nimbus, as_a, as_c, people
    ):
        """Contract: opportunity-stats shape, counts match the seeded data."""
        first = create_open(as_admin, company, title="First")
        second = create_open(as_admin, nimbus, title="Second", eligible_departments=[])
        create_draft(as_acme)
        make_pending(as_acme)
        assert as_admin.get(url("opportunity-stats")).json()["median_hours_to_shortlist"] is None
        app_a = applied(as_a, first["id"])
        applied(as_c, first["id"])
        applied(as_a, second["id"])
        move(as_admin, app_a["id"], "shortlisted")
        stats = as_admin.get(url("opportunity-stats")).json()
        assert set(stats) == {
            "opportunities_by_status", "applications_by_status", "per_opportunity", "median_hours_to_shortlist",
        }
        by_status = stats["opportunities_by_status"]
        assert (by_status.get("open"), by_status.get("draft"), by_status.get("pending_review")) == (2, 1, 1)
        apps = stats["applications_by_status"]
        assert (apps.get("applied"), apps.get("shortlisted")) == (2, 1)
        per = {r["id"]: r for r in stats["per_opportunity"]}
        assert set(per[first["id"]]) >= {"id", "title", "company", "applicants", "by_status"}
        assert per[first["id"]]["applicants"] == 2 and per[second["id"]]["applicants"] == 1
        assert per[first["id"]]["by_status"].get("shortlisted") == 1
        assert per[first["id"]]["title"] == "First"
        assert isinstance(stats["median_hours_to_shortlist"], float)

    def test_stats_is_admin_only(self, as_acme, as_a, anon, people):
        """Contract: stats is admin only."""
        assert as_acme.get(url("opportunity-stats")).status_code == 403
        assert as_a.get(url("opportunity-stats")).status_code == 403
        assert anon.get(url("opportunity-stats")).status_code == 401


# ===========================================================================
# Notifications (D26)
# ===========================================================================


class TestNotifications:
    @staticmethod
    def recipients(opp_id, kind):
        found = model("notifications", "Notification").objects.filter(opportunity_id=opp_id, kind=kind)
        return set(found.values_list("recipient__prn", flat=True))

    @pytest.fixture
    def extras(self, make_student):
        """F is suspended, G is not placement eligible: both must be skipped."""
        f = make_student(prn="220200945", full_name="Farah Sheikh", department=CS, cgpa="8.00")
        f.user.set_status("suspended")
        g = make_student(prn="220200946", full_name="Gaurav Iyer", department=CS, cgpa="8.00")
        g.student.is_placement_eligible = False
        g.student.save()
        return SimpleNamespace(f=f, g=g)

    def test_approval_notifies_only_eligible_active_students(
        self, as_acme, as_admin, people, extras
    ):
        """D26 trigger 1: account, active, placement eligible and passes eligibility."""
        opp = make_pending(as_acme)
        assert self.recipients(opp["id"], "new_opportunity") == set()
        assert as_admin.post(url("opportunity-approve", opp["id"])).status_code == 200
        # A, C and D pass; B is the wrong programme, E is under the CGPA cutoff.
        assert self.recipients(opp["id"], "new_opportunity") == {"220200940", "220200942", "220200943"}

    def test_an_admin_created_posting_notifies_too(self, as_admin, company, people):
        """D26: a posting reaching open, by approval or admin creation."""
        opp = create_open(as_admin, company)
        assert self.recipients(opp["id"], "new_opportunity") == {"220200940", "220200942", "220200943"}

    def test_a_rejected_posting_notifies_nobody(self, as_acme, as_admin, people):
        """D26: only reaching open fires trigger 1."""
        opp = make_pending(as_acme)
        as_admin.post(url("opportunity-reject", opp["id"]), {"reason": "No"}, format="json")
        assert model("notifications", "Notification").objects.count() == 0

    def test_approving_creates_no_scoring_pass_inside_the_request(self, as_acme, as_admin, people, monkeypatch):
        """D26: trigger 1 uses the hard check only, no scoring in the request."""
        import profiles.match as match

        def boom(*args, **kwargs):
            raise AssertionError("scored a profile inside the approve request")

        monkeypatch.setattr(match, "score_profile", boom)
        opp = make_pending(as_acme)
        assert as_admin.post(url("opportunity-approve", opp["id"])).status_code == 200

    def test_notify_deadlines_reaches_eligible_non_applicants_once(
        self, as_a, people, extras, company, admin_user, opportunity_settings
    ):
        """D26 trigger 2: eligible non-applicants in the window, idempotent."""
        opportunity_settings(DEADLINE_NOTICE_DAYS=3)
        soon = orm_opportunity(company, deadline=today() + timedelta(days=2))
        far = orm_opportunity(company, deadline=today() + timedelta(days=30), title="Far")
        closed = orm_opportunity(company, deadline=today() + timedelta(days=2), status="closed", title="Closed")
        assert apply_to(as_a, soon.id).status_code == 201
        try:
            call_command("notify_deadlines")
            first = model("notifications", "Notification").objects.filter(kind="deadline_soon").count()
            call_command("notify_deadlines")
        except CommandError:
            missing("manage.py notify_deadlines")
        second = model("notifications", "Notification").objects.filter(kind="deadline_soon").count()
        assert self.recipients(soon.id, "deadline_soon") == {"220200942", "220200943"}  # not A: applied
        assert self.recipients(far.id, "deadline_soon") == set()
        assert self.recipients(closed.id, "deadline_soon") == set()
        assert first == second == 2

    def test_a_user_sees_only_their_own_notifications(self, as_acme, as_admin, as_a, as_c, as_b, people):
        """Contract: notification-list is own only, with the contract row shape."""
        opp = make_pending(as_acme)
        as_admin.post(url("opportunity-approve", opp["id"]))
        mine = rows(as_a.get(url("notification-list")))
        assert len(mine) == 1
        assert set(mine[0]) >= {"id", "kind", "opportunity", "created_at", "read_at"}
        assert mine[0]["kind"] == "new_opportunity" and mine[0]["read_at"] is None
        assert mine[0]["opportunity"] == {"id": opp["id"], "title": opp["title"]}
        assert len(rows(as_c.get(url("notification-list")))) == 1
        assert rows(as_b.get(url("notification-list"))) == []

    def test_mark_read_and_read_all(self, as_acme, as_admin, as_a, as_c, people):
        """Contract: read is 204 and own only, read-all is 204, ?unread=true filters."""
        for title in ("One", "Two"):
            as_admin.post(url("opportunity-approve", make_pending(as_acme, title=title)["id"]))
        mine = rows(as_a.get(url("notification-list")))
        assert len(mine) == 2
        theirs = rows(as_c.get(url("notification-list")))
        assert as_c.post(url("notification-read", mine[0]["id"])).status_code == 404
        assert as_a.post(url("notification-read", mine[0]["id"])).status_code == 204
        assert len(rows(as_a.get(url("notification-list"), {"unread": "true"}))) == 1
        assert as_a.post(url("notification-read-all")).status_code == 204
        assert rows(as_a.get(url("notification-list"), {"unread": "true"})) == []
        assert len(rows(as_c.get(url("notification-list"), {"unread": "true"}))) == len(theirs)

    def test_notification_routes_reject_anonymous_callers_and_unknown_parameters(self, anon, as_a, people):
        """Contract rules: 401 for anonymous, unknown query parameter is 400."""
        assert anon.get(url("notification-list")).status_code == 401
        assert as_a.get(url("notification-list"), {"colour": "red"}).status_code == 400


# ===========================================================================
# Stage 3: suggestions
# ===========================================================================


class TestSuggestions:
    def test_nothing_open_gives_no_open_postings(self, as_a, people, suggestion_settings):
        """Stage 3: reason no_open_postings, open_count 0."""
        suggestion_settings()
        body = as_a.get(url("opportunity-suggestions")).json()
        assert body == {"results": [], "open_count": 0, "reason": "no_open_postings"}

    def test_nothing_clearing_the_bar_gives_none_match(self, as_admin, company, as_a, people, suggestion_settings):
        """Stage 3: reason none_match, open_count still counts the postings."""
        suggestion_settings(MIN_SCORE=101)
        create_open(as_admin, company)
        body = as_a.get(url("opportunity-suggestions")).json()
        assert body["results"] == [] and body["open_count"] == 1 and body["reason"] == "none_match"

    def test_a_match_leaves_the_reason_null_and_the_rows_share_the_feed_shape(
        self, as_admin, company, as_a, people, suggestion_settings
    ):
        """Stage 3: row shape matches feed, and the cache gives the same score."""
        suggestion_settings(MIN_SCORE=0)
        opp = create_open(as_admin, company)
        body = as_a.get(url("opportunity-suggestions")).json()
        assert body["reason"] is None and body["open_count"] == 1
        feed_row = rows(as_a.get(url("opportunity-feed")))[0]
        assert set(body["results"][0]) == set(feed_row)
        assert body["results"][0]["id"] == opp["id"]
        assert body["results"][0]["score"] == feed_row["score"]

    def test_the_threshold_comes_from_settings_and_is_inclusive(
        self, as_admin, company, as_a, people, suggestion_settings
    ):
        """Stage 3: score >= SUGGESTIONS['MIN_SCORE'], read from settings."""
        suggestion_settings(MIN_SCORE=0)
        backend = create_open(as_admin, company)
        marketing = create_open(
            as_admin, company, title="Marketing Executive", description=MARKETING_JD,
            eligible_departments=[], min_cgpa=None, required_skills=["SEO"],
        )
        feed = {r["id"]: r["score"] for r in rows(as_a.get(url("opportunity-feed")))}
        assert feed[backend["id"]] > feed[marketing["id"]]
        listed = [r["id"] for r in as_a.get(url("opportunity-suggestions")).json()["results"]]
        assert listed == [backend["id"], marketing["id"]]
        suggestion_settings(MIN_SCORE=feed[backend["id"]])
        cut = as_a.get(url("opportunity-suggestions")).json()
        assert [r["id"] for r in cut["results"]] == [backend["id"]]

    def test_a_postings_own_threshold_beats_the_settings_one(
        self, as_admin, company, as_a, people, suggestion_settings
    ):
        """Contract: score >= (posting.similarity_threshold or MIN_SCORE)."""
        suggestion_settings(MIN_SCORE=0)
        strict = create_open(as_admin, company, similarity_threshold=100)
        suggestion_settings(MIN_SCORE=101)
        lax = create_open(as_admin, company, title="Lax", similarity_threshold=0)
        listed = [r["id"] for r in as_a.get(url("opportunity-suggestions")).json()["results"]]
        assert listed == [lax["id"]] and strict["id"] not in listed

    def test_the_list_is_capped_at_max_results(self, as_admin, company, as_a, people, suggestion_settings):
        """Contract: capped at SUGGESTIONS['MAX_RESULTS'], sorted by score desc."""
        suggestion_settings(MIN_SCORE=0, MAX_RESULTS=1)
        create_open(as_admin, company)
        create_open(as_admin, company, title="Second")
        body = as_a.get(url("opportunity-suggestions")).json()
        assert len(body["results"]) == 1 and body["open_count"] == 2

    def test_past_deadline_and_closed_postings_are_not_suggested(
        self, company, as_a, people, suggestion_settings
    ):
        """Contract: open postings, deadline today or later."""
        suggestion_settings(MIN_SCORE=0)
        orm_opportunity(company, deadline=today() - timedelta(days=1))
        orm_opportunity(company, status="closed", title="Closed")
        body = as_a.get(url("opportunity-suggestions")).json()
        assert body["results"] == [] and body["reason"] == "no_open_postings"

    def test_the_response_never_says_probability(self, as_admin, company, as_a, people, suggestion_settings):
        """Stage 3: a guide, not a prediction, in every branch."""
        suggestion_settings(MIN_SCORE=101)
        empty = as_a.get(url("opportunity-suggestions"))
        create_open(as_admin, company)
        none_match = as_a.get(url("opportunity-suggestions"))
        suggestion_settings(MIN_SCORE=0)
        full = as_a.get(url("opportunity-suggestions"))
        for response in (empty, none_match, full):
            assert response.status_code == 200
            assert "probab" not in response.content.decode().lower()

    def test_it_works_with_the_llm_off(self, as_admin, company, as_a, people, suggestion_settings, settings):
        """Contract: everything works with LLM_ENABLED=false."""
        settings.LLM = {**settings.LLM, "ENABLED": False}
        suggestion_settings(MIN_SCORE=0)
        create_open(as_admin, company)
        response = as_a.get(url("opportunity-suggestions"))
        assert response.status_code == 200 and response.json()["results"]

    def test_students_only_and_unknown_parameters_are_400(self, as_acme, as_a, anon, people):
        """Contract: student only, 401 anonymous, unknown query parameter 400."""
        assert as_acme.get(url("opportunity-suggestions")).status_code == 403
        assert anon.get(url("opportunity-suggestions")).status_code == 401
        assert as_a.get(url("opportunity-suggestions"), {"colour": "red"}).status_code == 400

    def test_suggestions_are_throttled_on_the_matching_scope(self, as_a, people, rates):
        """Contract: suggestions uses MatchingThrottle."""
        rates(matching="1/hour")
        assert as_a.get(url("opportunity-suggestions")).status_code == 200
        assert as_a.get(url("opportunity-suggestions")).status_code == 429


# ===========================================================================
# Stage 4: recruiter exports
# ===========================================================================


@pytest.fixture
def shortlisted(as_admin, as_acme, admin_user, company, as_a, as_c, people):
    """
    Acme's shortlist: A (shortlisted application), D (manual pick, no resume).

    C has only applied, which is not a pick. A is verified; D is not.
    """
    people.a.mark_verified(admin_user)
    opp = create_open(as_admin, company)
    app_a = applied(as_a, opp["id"])
    app_c = applied(as_c, opp["id"])
    move(as_admin, app_a["id"], "shortlisted")
    assert as_acme.post(url("company-profile-shortlist", people.d.student_id)).status_code == 201
    return SimpleNamespace(opp=opp, app_a=app_a, app_c=app_c)


def open_contacts(payload):
    import pyzipper

    raw = base64.b64decode(payload["zip_base64"])
    return raw, pyzipper.AESZipFile(io.BytesIO(raw))


def read_contacts(payload):
    raw, archive = open_contacts(payload)
    archive.setpassword(payload["password"].encode())
    return list(csv.DictReader(io.StringIO(archive.read("contacts.csv").decode("utf-8"))))


class TestShortlistListing:
    def test_shortlisted_true_is_the_d27_shortlist_not_every_applicant(self, as_acme, shortlisted, people):
        """D27 and Stage 4: manual picks plus shortlisted-or-later applications, not bare ones."""
        listing = url("company-profile-list")
        picked = rows(as_acme.get(listing, {"shortlisted": "true"}))
        assert {r["prn"] for r in picked} == {"220200940", "220200943"}
        everyone = {r["prn"]: r for r in rows(as_acme.get(listing))}
        assert everyone["220200942"]["is_shortlisted"] is False
        assert everyone["220200940"]["is_shortlisted"] is True

    def test_interview_and_offer_applications_stay_on_the_shortlist(
        self, as_admin, as_acme, company, as_a, as_c, people
    ):
        """D27: status shortlisted, interview or offer all count."""
        opp = create_open(as_admin, company)
        first, second = applied(as_a, opp["id"]), applied(as_c, opp["id"])
        walk(as_admin, first["id"], "shortlisted", "interview")
        walk(as_admin, second["id"], "shortlisted", "interview", "offer")
        picked = rows(as_acme.get(url("company-profile-list"), {"shortlisted": "true"}))
        assert {r["prn"] for r in picked} == {"220200940", "220200942"}

    def test_a_rejected_or_withdrawn_application_is_not_a_pick(
        self, as_admin, as_acme, company, as_a, as_c, people
    ):
        """D27: only shortlisted, interview and offer count."""
        opp = create_open(as_admin, company)
        first, second = applied(as_a, opp["id"]), applied(as_c, opp["id"])
        walk(as_admin, first["id"], "shortlisted", "rejected")
        as_c.post(url("application-withdraw", second["id"]))
        assert rows(as_acme.get(url("company-profile-list"), {"shortlisted": "true"})) == []

    def test_another_companys_shortlist_is_not_mine(self, as_nimbus, shortlisted):
        """Stage 4: the shortlist is per company."""
        assert rows(as_nimbus.get(url("company-profile-list"), {"shortlisted": "true"})) == []

    def test_a_hidden_student_is_off_the_shortlist_listing(self, as_acme, shortlisted, people):
        """Stage 4: the shortlist is intersected with visible_to."""
        people.a.visibility = "hidden"
        people.a.save()
        picked = rows(as_acme.get(url("company-profile-list"), {"shortlisted": "true"}))
        assert {r["prn"] for r in picked} == {"220200943"}

    def test_is_shortlisted_costs_no_query_per_row(self, as_acme, shortlisted, people, django_assert_max_num_queries):
        """Stage 4: is_shortlisted is annotated on the page query, no per-row EXISTS."""
        listing = url("company-profile-list")
        as_acme.get(listing)  # warm caches
        with django_assert_max_num_queries(12) as _:
            as_acme.get(listing, {"shortlisted": "true"})

    def test_a_bad_shortlisted_value_is_400(self, as_acme, shortlisted):
        """Contract: filters are validated, unknown parameters are 400."""
        assert as_acme.get(url("company-profile-list"), {"shortlisted": "maybe"}).status_code == 400
        assert as_acme.get(url("company-profile-list"), {"shortlisted": "true", "colour": "x"}).status_code == 400


class TestCvZip:
    def test_the_zip_holds_current_resumes_named_prn_and_name(self, as_acme, shortlisted, people):
        """Stage 4: `<PRN>-<full name>.<ext>`, the current resume, a SKIPPED.txt for the rest."""
        response = as_acme.get(url("company-shortlist-resumes"))
        assert response.status_code == 200 and response["Content-Type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(body_of(response)))
        assert sorted(archive.namelist()) == ["220200940-Aditi Verma.pdf", "SKIPPED.txt"]
        with people.a.resume.open("rb") as current:
            assert archive.read("220200940-Aditi Verma.pdf") == current.read()
        assert "220200943" in archive.read("SKIPPED.txt").decode()

    def test_students_without_a_resume_are_counted_in_the_header(self, as_acme, shortlisted):
        """Stage 4: X-Skipped-Without-Resume counts the skipped."""
        response = as_acme.get(url("company-shortlist-resumes"))
        assert response["X-Skipped-Without-Resume"] == "1"

    def test_a_bare_applicant_is_not_in_the_zip(self, as_acme, shortlisted):
        """D27: the CV zip is the shortlist, not every applicant."""
        archive = zipfile.ZipFile(io.BytesIO(body_of(as_acme.get(url("company-shortlist-resumes")))))
        assert not any(n.startswith("220200942") for n in archive.namelist())

    def test_a_student_who_goes_hidden_after_being_shortlisted_is_absent(self, as_acme, shortlisted, people):
        """Stage 4 leak test: CV zip follows visible_to."""
        people.a.visibility = "hidden"
        people.a.save()
        response = as_acme.get(url("company-shortlist-resumes"))
        archive = zipfile.ZipFile(io.BytesIO(body_of(response)))
        assert not any(n.startswith("220200940") for n in archive.namelist())

    def test_the_zip_is_audited_with_count_skipped_and_company(self, as_acme, company, shortlisted):
        """Stage 4: documents_bulk_downloaded with {count, skipped, company}."""
        before = audit_count("documents_bulk_downloaded")
        as_acme.get(url("company-shortlist-resumes"))
        assert audit_count("documents_bulk_downloaded") == before + 1
        detail = last_audit("documents_bulk_downloaded").detail
        assert detail["count"] == 1 and detail["skipped"] == 1
        assert str(detail["company"]) in (str(company.id), company.name, company.company_id)

    def test_another_company_gets_its_own_empty_shortlist_not_mine(self, as_nimbus, shortlisted):
        """Stage 4: a company cannot export another company's shortlist."""
        response = as_nimbus.get(url("company-shortlist-resumes"))
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            assert not any(n.startswith("2202009") and n != "SKIPPED.txt"
                           for n in zipfile.ZipFile(io.BytesIO(body_of(response))).namelist())

    def test_only_companies_with_a_company_may_download(self, as_a, as_admin, as_bare, anon, shortlisted):
        """Stage 4: company-only; anonymous gets 401."""
        route = url("company-shortlist-resumes")
        assert anon.get(route).status_code == 401
        assert as_a.get(route).status_code == 403
        assert as_admin.get(route).status_code == 403
        assert as_bare.get(route).status_code == 403

    def test_the_zip_uses_the_export_throttle(self, as_acme, shortlisted, rates):
        """Stage 4: the export throttle, overridden low, gives 429."""
        rates(export="1/hour")
        route = url("company-shortlist-resumes")
        assert as_acme.get(route).status_code == 200
        assert as_acme.get(route).status_code == 429


class TestContactExport:
    def test_the_response_has_the_contract_keys(self, as_acme, shortlisted):
        """Contract: 200 JSON {password, filename, zip_base64, row_count}."""
        response = as_acme.post(url("company-shortlist-contacts"))
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {"password", "filename", "zip_base64", "row_count"}
        assert payload["filename"].endswith(".zip") and payload["row_count"] == 2
        assert len(payload["password"]) >= 16

    def test_the_zip_cannot_be_opened_without_the_password(self, as_acme, shortlisted):
        """Stage 4: AES-256, unreadable without the password."""
        payload = as_acme.post(url("company-shortlist-contacts")).json()
        raw, archive = open_contacts(payload)
        with pytest.raises(RuntimeError):
            archive.read("contacts.csv")
        archive.setpassword(b"not-the-password")
        with pytest.raises(RuntimeError):
            archive.read("contacts.csv")
        info = zipfile.ZipFile(io.BytesIO(raw)).infolist()[0]
        assert info.flag_bits & 0x1 and info.compress_type == 99  # WinZip AES
        extra = info.extra
        assert b"\x01\x99" in extra and extra[extra.index(b"\x01\x99") + 8] == 3  # strength 3 = AES-256

    def test_the_password_opens_it_and_is_not_inside(self, as_acme, shortlisted):
        """Stage 4: the password opens it, only contacts.csv inside, password nowhere in the bytes."""
        payload = as_acme.post(url("company-shortlist-contacts")).json()
        raw, archive = open_contacts(payload)
        assert archive.namelist() == ["contacts.csv"]
        archive.setpassword(payload["password"].encode())
        text = archive.read("contacts.csv").decode()
        assert payload["password"].encode() not in raw and payload["password"] not in text
        assert text.splitlines()[0].split(",") == CONTACT_COLUMNS

    def test_each_call_gets_a_fresh_password(self, as_acme, shortlisted):
        """Stage 4: the password is random per export."""
        first = as_acme.post(url("company-shortlist-contacts")).json()["password"]
        second = as_acme.post(url("company-shortlist-contacts")).json()["password"]
        assert first != second

    def test_unverified_students_get_a_blank_row_and_verified_ones_their_contacts(self, as_acme, shortlisted, people):
        """Stage 4: blank contacts and contact_available false when unverified."""
        parsed = {r["prn"]: r for r in read_contacts(as_acme.post(url("company-shortlist-contacts")).json())}
        assert set(parsed) == {"220200940", "220200943"}
        verified, unverified = parsed["220200940"], parsed["220200943"]
        assert verified["email"] == "220200940@college.edu" and verified["phone"] == people.a.phone
        assert verified["contact_available"].lower() == "true"
        assert unverified["email"] == "" and unverified["phone"] == ""
        assert unverified["contact_available"].lower() == "false"
        assert unverified["full_name"] == "Dev Malhotra" and unverified["programme"] == CS
        assert unverified["shortlisted_on"]

    def test_a_student_who_goes_hidden_after_being_shortlisted_is_absent(self, as_acme, shortlisted, people):
        """Stage 4 leak test: the contact export follows visible_to."""
        people.a.visibility = "hidden"
        people.a.save()
        payload = as_acme.post(url("company-shortlist-contacts")).json()
        assert {r["prn"] for r in read_contacts(payload)} == {"220200943"}
        assert payload["row_count"] == 1

    def test_more_than_the_row_cap_is_400(self, as_acme, shortlisted, opportunity_settings):
        """Contract: more than OPPORTUNITIES['EXPORT_MAX_ROWS'] rows is 400."""
        opportunity_settings(EXPORT_MAX_ROWS=1)
        assert as_acme.post(url("company-shortlist-contacts")).status_code == 400

    def test_the_export_is_audited_with_count_and_company(self, as_acme, company, shortlisted):
        """Stage 4: shortlist_exported with {count, company}."""
        before = audit_count("shortlist_exported")
        as_acme.post(url("company-shortlist-contacts"))
        assert audit_count("shortlist_exported") == before + 1
        detail = last_audit("shortlist_exported").detail
        assert detail["count"] == 2
        assert str(detail["company"]) in (str(company.id), company.name, company.company_id)

    def test_another_company_cannot_export_my_shortlist(self, as_nimbus, shortlisted):
        """Stage 4: a company cannot export another company's shortlist."""
        response = as_nimbus.post(url("company-shortlist-contacts"))
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            assert response.json()["row_count"] == 0
            assert read_contacts(response.json()) == []

    def test_post_only_company_only(self, as_acme, as_a, as_admin, as_bare, anon, shortlisted):
        """Stage 4: POST only, company-only, 401 anonymous."""
        route = url("company-shortlist-contacts")
        assert as_acme.get(route).status_code == 405
        assert anon.post(route).status_code == 401
        assert as_a.post(route).status_code == 403
        assert as_admin.post(route).status_code == 403
        assert as_bare.post(route).status_code == 403

    def test_the_export_uses_the_export_throttle(self, as_acme, shortlisted, rates):
        """Stage 4: the export throttle, overridden low, gives 429."""
        rates(export="1/hour")
        route = url("company-shortlist-contacts")
        assert as_acme.post(route).status_code == 200
        assert as_acme.post(route).status_code == 429


# ===========================================================================
# The usual contract rules
# ===========================================================================


class TestContractRules:
    @pytest.mark.parametrize(
        "name, args",
        [
            ("opportunity-list", ()),
            ("opportunity-feed", ()),
            ("opportunity-suggestions", ()),
            ("opportunity-stats", ()),
            ("application-list", ()),
            ("notification-list", ()),
            ("notification-read-all", ()),
            ("company-shortlist-resumes", ()),
            ("company-shortlist-contacts", ()),
        ],
    )
    def test_anonymous_callers_get_401(self, anon, name, args):
        """Contract rules: an anonymous caller gets 401."""
        route = url(name, *args)
        response = anon.post(route) if name in ("notification-read-all", "company-shortlist-contacts") else anon.get(route)
        assert response.status_code == 401

    @pytest.mark.parametrize(
        "name",
        ["opportunity-list", "opportunity-feed", "opportunity-suggestions", "application-list", "notification-list"],
    )
    def test_an_unknown_query_parameter_is_400(self, as_admin, as_a, people, name):
        """Contract rules: an unknown query parameter is a 400."""
        client = as_a if name in ("opportunity-feed", "opportunity-suggestions", "notification-list") else as_admin
        route = url(name)
        assert client.get(route, {"colour": "red"}).status_code == 400

    def test_prns_reports_the_misses_on_the_applications_list(self, as_admin, company, as_a, people):
        """NEXT_PHASES test 7: ?prns= names the misses in unmatched_prns."""
        opp = create_open(as_admin, company)
        applied(as_a, opp["id"])
        response = as_admin.get(url("application-list"), {"prns": "220200940,220200959"})
        assert response.status_code == 200
        payload = response.json()
        assert [r["prn"] for r in payload["results"]] == ["220200940"]
        assert payload["unmatched_prns"] == ["220200959"]

    def test_prn_and_opportunity_and_status_filters_narrow_the_list(
        self, as_admin, company, as_a, as_c, people
    ):
        """Contract: application-list filters ?opportunity= ?status= ?prn=."""
        first = create_open(as_admin, company, title="First")
        second = create_open(as_admin, company, title="Second")
        app_a = applied(as_a, first["id"])
        applied(as_c, second["id"])
        move(as_admin, app_a["id"], "shortlisted")
        route = url("application-list")
        assert [r["prn"] for r in rows(as_admin.get(route, {"prn": "220200942"}))] == ["220200942"]
        assert [r["prn"] for r in rows(as_admin.get(route, {"opportunity": first["id"]}))] == ["220200940"]
        assert [r["prn"] for r in rows(as_admin.get(route, {"status": "shortlisted"}))] == ["220200940"]

    def test_applications_are_never_deleted(self, as_admin, company, as_a, people):
        """Contract: applications are never deleted, not even with the posting's draft rule."""
        opp = create_open(as_admin, company)
        app = applied(as_a, opp["id"])
        as_a.post(url("application-withdraw", app["id"]))
        assert model("opportunities", "Application").objects.filter(id=app["id"]).exists()
        assert as_admin.delete(url("application-detail", app["id"])).status_code in (404, 405)

    def test_the_apis_use_uuids_in_paths_never_prns(self, as_admin, company, people):
        """Contract: UUID in every path; a PRN is not an opportunity id."""
        create_open(as_admin, company)
        assert as_admin.get(url("opportunity-detail", "220200940")).status_code == 404
