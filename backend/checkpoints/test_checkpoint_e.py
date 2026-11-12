"""
Checkpoint E -- the gate for REQUIREMENTS-ADDENDUM R1 to R5.

Written before the features exist (step E0 of PLAN_PHASE_A_AND_ADDENDUM.md), so
every test here fails today. The shapes asserted are exactly those in
`docs/ADDENDUM_API_CONTRACT.md`; if one has to change, change the contract
first.

A missing URL name or endpoint is reported through `url()` / `missing()` as
"not built yet", never as an import or collection error. Nothing new is
imported at module level.

Run alone:

    cd backend && ../.venv/bin/python -m pytest checkpoints/test_checkpoint_e.py -q
"""

from __future__ import annotations

import csv
import io
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import NoReverseMatch, reverse

from checkpoints.conftest import client_for
from checkpoints.transcript_fixtures import CASES, make_case

CAREER_PATHS = (
    "placement",
    "business",
    "higher_studies",
    "entrepreneurship",
    "research",
    "family_business",
    "competitive_exams",
    "other",
    "undecided",
)

# Synthetic PRNs: YY0200NNN, YY = batch - 4, sequences 930-949.
PRN_MAIN = "220200930"


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


def pdf_upload(path) -> SimpleUploadedFile:
    path = Path(path)
    return SimpleUploadedFile(path.name, path.read_bytes(), content_type="application/pdf")


def upload_transcript(client, path):
    return client.post(url("my-transcript"), {"file": pdf_upload(path)}, format="multipart")


def body_of(response) -> bytes:
    if getattr(response, "streaming", False):
        return b"".join(response.streaming_content)
    return response.content


def audit_count(action: str) -> int:
    from core.models import AuditLog

    return AuditLog.objects.filter(action=action).count()


def media_pdfs(settings) -> list:
    root = Path(settings.MEDIA_ROOT)
    return list(root.rglob("*.pdf")) if root.exists() else []


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def me(make_student):
    """The signed-in student's profile: batch 2026, roster CGPA 8.50."""
    profile = make_student(prn=PRN_MAIN, full_name="Test Student", cgpa="8.50")
    profile.student.school = "computing_data_science"
    profile.student.save()
    return profile


@pytest.fixture
def as_me(me):
    return client_for(me.user)


@pytest.fixture
def uploaded_transcript(me, as_me, tmp_path):
    """Upload a ready-made transcript through the API; returns the response."""

    def _upload(kind="clean"):
        me.student.cgpa = Decimal(CASES[kind].roster_cgpa)
        me.student.save()
        path = make_case(kind, tmp_path, prn=PRN_MAIN, name="Test Student")
        return upload_transcript(as_me, path)

    return _upload


@pytest.fixture
def uploaded_resume(as_me):
    """Upload a real PDF resume; returns (response, original filename)."""
    from matching.management.commands.make_sample_resumes import write_pdf
    from matching.samples import SAMPLES_BY_KEY

    def _upload(lines=None, key="backend_engineer"):
        if lines is None:
            lines = list(SAMPLES_BY_KEY[key].lines)
        path = Path(tempfile.mkdtemp()) / "my_resume.pdf"
        write_pdf(path, lines)
        file = pdf_upload(path)
        response = as_me.post(url("my-resume"), {"file": file}, format="multipart")
        return response, file.name

    return _upload


# ---------------------------------------------------------------------------
# R1 -- admin sees a student's full profile and documents
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestR1AdminView:
    def test_admin_sees_a_hidden_profile_with_career_path_and_roster_facts(
        self, me, as_me, as_admin
    ):
        """The placement cell is never subject to the student's visibility setting."""
        from profiles.models import Visibility

        me.visibility = Visibility.HIDDEN
        # Save only this field: `me` was loaded before the API calls above,
        # and a full save() would overwrite what they just wrote.
        me.save(update_fields=["visibility", "updated_at"])
        patched = as_me.patch(url("my-profile"), {"career_path": "research"}, format="json")
        assert patched.status_code == 200, patched.content

        response = as_admin.get(url("admin-profile-detail", me.student_id))

        assert response.status_code == 200
        body = response.json()
        assert body["career_path"] == "research"
        assert body["student"]["prn"] == PRN_MAIN
        assert body["student"]["department"]
        assert body["student"]["batch"] == 2026

    def test_admin_resume_url_is_an_api_url_never_media(self, me, as_admin, uploaded_resume):
        """Documents are served through the audited API, not a public /media/ path."""
        response, _ = uploaded_resume()
        assert response.status_code == 201

        body = as_admin.get(url("admin-profile-detail", me.student_id)).json()

        assert body["resume_url"] == f"/api/profiles/admin/{me.student_id}/resume"
        assert "/media/" not in body["resume_url"]

    def test_admin_downloads_the_resume_with_its_original_filename_and_it_is_audited(
        self, me, as_admin, uploaded_resume
    ):
        """Opening a resume is written to the audit log (R1 last checkbox)."""
        _, filename = uploaded_resume()
        resume_url = url("admin-profile-resume", me.student_id)
        before = audit_count("document_accessed")

        response = as_admin.get(resume_url)

        assert response.status_code == 200
        assert body_of(response).startswith(b"%PDF")
        assert filename in response["Content-Disposition"]
        assert audit_count("document_accessed") == before + 1

    def test_admin_downloads_the_transcript_the_same_way(self, me, as_admin, uploaded_transcript):
        """The transcript is reachable from the admin detail exactly like the resume."""
        assert uploaded_transcript("clean").status_code == 201
        detail = as_admin.get(url("admin-profile-detail", me.student_id)).json()
        assert detail["transcript_url"] == f"/api/profiles/admin/{me.student_id}/transcript"
        assert "/media/" not in detail["transcript_url"]
        before = audit_count("document_accessed")

        response = as_admin.get(url("admin-profile-transcript", me.student_id))

        assert response.status_code == 200
        assert body_of(response).startswith(b"%PDF")
        assert "transcript_clean.pdf" in response["Content-Disposition"]
        assert audit_count("document_accessed") == before + 1

    def test_admin_resume_is_404_when_there_is_none_and_admin_only(
        self, me, as_admin, as_company, as_me
    ):
        """No file is a 404; students and companies cannot use the admin route."""
        target = url("admin-profile-resume", me.student_id)
        assert as_admin.get(target).status_code == 404
        assert as_company.get(target).status_code == 403
        assert as_me.get(target).status_code == 403

    def test_admin_can_verify_and_revoke_for_a_student(self, me, as_admin):
        """Verification applied or revoked for a student reached via admin/<id>."""
        url("admin-profile-resume", me.student_id)  # the R1 surface must exist
        verify = url("admin-profile-verification", me.student_id)

        assert as_admin.post(verify, {"is_verified": True}, format="json").status_code == 200
        assert as_admin.get(url("admin-profile-detail", me.student_id)).json()["is_verified"]
        assert as_admin.post(verify, {"is_verified": False}, format="json").status_code == 200
        assert not as_admin.get(url("admin-profile-detail", me.student_id)).json()["is_verified"]

    def test_own_resume_file_is_served_to_the_student(self, me, as_me, uploaded_resume):
        """The student's own resume_url is the API url and it returns the file."""
        _, filename = uploaded_resume()
        profile = as_me.get(url("my-profile")).json()
        assert profile["resume_url"] == "/api/profiles/me/resume/file"

        response = as_me.get(url("my-resume-file"))

        assert response.status_code == 200
        assert filename in response["Content-Disposition"]

    def test_company_resume_follows_visibility_and_is_audited(
        self, me, as_company, uploaded_resume
    ):
        """A company gets the resume only for a profile visible to it."""
        from profiles.models import Visibility

        uploaded_resume()
        target = url("company-profile-resume", me.student_id)
        me.visibility = Visibility.HIDDEN
        # Save only this field: `me` was loaded before the API calls above,
        # and a full save() would overwrite what they just wrote.
        me.save(update_fields=["visibility", "updated_at"])
        assert as_company.get(target).status_code == 404

        me.visibility = Visibility.ALL
        # Save only this field: `me` was loaded before the API calls above,
        # and a full save() would overwrite what they just wrote.
        me.save(update_fields=["visibility", "updated_at"])
        before = audit_count("document_accessed")
        assert as_company.get(target).status_code == 200
        assert audit_count("document_accessed") == before + 1

    @pytest.mark.parametrize(
        "name",
        [
            "my-resume-file",
            "my-transcript-file",
            "my-transcript",
            "my-onboarding",
            "my-confirm-cgpa",
            "admin-profile-outcomes",
        ],
    )
    def test_anonymous_callers_get_401(self, api_client, name):
        """Every new endpoint answers 401 to an anonymous caller."""
        assert api_client.get(url(name)).status_code == 401


# ---------------------------------------------------------------------------
# R2 -- career path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestR2CareerPath:
    @pytest.mark.parametrize("value", [v for v in CAREER_PATHS if v != "other"])
    def test_patch_me_accepts_each_career_path(self, as_me, value):
        """All nine values from the fixed list are accepted and echoed back."""
        response = as_me.patch(url("my-profile"), {"career_path": value}, format="json")

        assert response.status_code == 200, response.content
        assert response.json()["career_path"] == value

    def test_patch_me_accepts_other_with_detail(self, as_me):
        """'other' is accepted when the free-text detail is given."""
        response = as_me.patch(
            url("my-profile"),
            {"career_path": "other", "career_path_detail": "Join the family farm"},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert response.json()["career_path"] == "other"
        assert response.json()["career_path_detail"] == "Join the family farm"

    @pytest.mark.parametrize(
        "payload", [{}, {"career_path_detail": ""}, {"career_path_detail": "   "}]
    )
    def test_other_with_blank_detail_is_rejected(self, as_me, payload):
        """'other' without a description is a 400, not a silent save."""
        response = as_me.patch(
            url("my-profile"), {"career_path": "other", **payload}, format="json"
        )

        assert response.status_code == 400

    def test_an_unknown_value_is_rejected(self, as_me):
        """Only the nine listed values are allowed."""
        response = as_me.patch(url("my-profile"), {"career_path": "astronaut"}, format="json")
        assert response.status_code == 400

    def test_leaving_other_clears_the_detail(self, as_me):
        """The detail is stored as an empty string for every non-'other' value."""
        first = as_me.patch(
            url("my-profile"),
            {"career_path": "other", "career_path_detail": "Farming"},
            format="json",
        )
        assert first.status_code == 200, first.content

        response = as_me.patch(
            url("my-profile"),
            {"career_path": "placement", "career_path_detail": "stale"},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["career_path"] == "placement"
        assert response.json()["career_path_detail"] == ""

    def test_default_is_undecided_and_not_attending_placements(self, as_me):
        """A new profile starts undecided with also_attending_placements false."""
        body = as_me.get(url("my-profile")).json()

        assert body["career_path"] == "undecided"
        assert body["also_attending_placements"] is False

    def test_company_payload_never_carries_career_path(self, me, as_me, as_company):
        """Companies must not see why a student is, or is not, seeking placement."""
        from profiles.models import Visibility

        patched = as_me.patch(url("my-profile"), {"career_path": "business"}, format="json")
        assert patched.status_code == 200, patched.content
        me.visibility = Visibility.ALL
        # Save only this field: `me` was loaded before the API calls above,
        # and a full save() would overwrite what they just wrote.
        me.save(update_fields=["visibility", "updated_at"])

        detail = as_company.get(url("company-profile-detail", me.student_id)).json()
        listed = as_company.get(url("company-profile-list")).json()
        rows = listed["results"] if isinstance(listed, dict) else listed

        for payload in [detail, *rows]:
            leaked = [k for k in payload if k.startswith("career_path") or k == "personal_email"]
            assert leaked == []
            assert "also_attending_placements" not in payload
        assert as_me.get(url("my-profile")).json()["career_path"] == "business"

    def test_company_completion_does_not_move_with_career_path(self, me, as_me, as_company):
        """
        Found by the final verifier. completion_percent counts career_path, so
        a company comparing the number before and after could tell a path had
        been chosen. Companies get a completion figure without that item.
        """
        from profiles.models import Visibility

        me.visibility = Visibility.ALL
        me.save(update_fields=["visibility", "updated_at"])
        target = url("company-profile-detail", me.student_id)

        before = as_company.get(target).json()["completion_percent"]
        assert as_me.patch(url("my-profile"), {"career_path": "business"}, format="json").status_code == 200
        after = as_company.get(target).json()["completion_percent"]

        assert before == after, f"company completion moved {before} -> {after} on a career path change"

    def test_completion_includes_career_path_and_undecided_is_not_done(self, as_me):
        """Profile completion gains a career_path item, done only once decided."""
        before = as_me.get(url("my-profile")).json()["completion_detail"]
        assert "career_path" in before, "completion_detail has no career_path item"
        assert before["career_path"] is False

        as_me.patch(url("my-profile"), {"career_path": "higher_studies"}, format="json")
        after = as_me.get(url("my-profile")).json()["completion_detail"]
        assert after["career_path"] is True

        as_me.patch(url("my-profile"), {"career_path": "undecided"}, format="json")
        assert as_me.get(url("my-profile")).json()["completion_detail"]["career_path"] is False

    @pytest.mark.parametrize("value", ["higher_studies", "business", "other"])
    def test_student_keeps_portal_access_whatever_the_path(self, as_me, value):
        """Choosing a non-placement path never locks the student out."""
        payload = {"career_path": value}
        if value == "other":
            payload["career_path_detail"] = "Something else"
        patched = as_me.patch(url("my-profile"), payload, format="json")
        assert patched.status_code == 200
        assert patched.json().get("career_path") == value

        assert as_me.get(url("my-profile")).status_code == 200
        assert as_me.get(url("my-match")).status_code != 403
        edit = as_me.patch(url("my-profile"), {"headline": "Still here"}, format="json")
        assert edit.status_code == 200

    def test_also_attending_placements_round_trips(self, as_me):
        """Students on another path can still say they will attend placements."""
        response = as_me.patch(
            url("my-profile"),
            {"career_path": "higher_studies", "also_attending_placements": True},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["also_attending_placements"] is True


# ---------------------------------------------------------------------------
# R3 -- outcomes dashboard
# ---------------------------------------------------------------------------


@pytest.fixture
def outcomes_data(make_student, db):
    """Call it inside the test, after the URL has been resolved."""
    return lambda: _seed_outcomes(make_student)


def _seed_outcomes(make_student):
    """
    Six roster students with accounts across two schools and two batches, one
    with no profile row and one with a blank school, plus one roster row with
    no account (never counted).
    """
    from accounts.models import Role, User
    from roster.models import Student

    def seed(prn, name, school, batch, path=None):
        profile = make_student(prn=prn, full_name=name, batch=batch, email=f"{prn}@college.edu")
        profile.student.school = school
        profile.student.save()
        if path:
            response = client_for(profile.user).patch(
                url("my-profile"), {"career_path": path}, format="json"
            )
            assert response.status_code == 200, response.content
        return profile

    seed("220200930", "A One", "computing_data_science", 2026, "placement")
    seed("220200931", "B Two", "computing_data_science", 2026)  # default undecided
    seed("220200932", "C Three", "business", 2026, "higher_studies")
    seed("230200934", "E Five", "computing_data_science", 2027, "business")
    seed("220200935", "F Six", "", 2026, "placement")  # blank school

    # An account with no profile row at all.
    student = Student.objects.create(
        prn="220200933",
        email="220200933@college.edu",
        full_name="D Four",
        department="BBA (Hons.)",
        batch=2026,
        school="business",
    )
    user = User.objects.create_user(
        email=student.email,
        password="StudentPass!234",
        role=Role.STUDENT,
        prn=student.prn,
        full_name=student.full_name,
    )
    user.mark_verified()
    # A roster row that never signed up.
    Student.objects.create(
        prn="220200936",
        email="220200936@college.edu",
        full_name="G Seven",
        department="BBA (Hons.)",
        batch=2026,
        school="business",
    )


@pytest.mark.django_db
class TestR3Outcomes:
    def test_rows_per_school_with_unassigned_and_every_path_key(self, as_admin, outcomes_data):
        """One row per school plus 'unassigned'; counts carry every path, zeros included."""
        target = url("admin-profile-outcomes")
        outcomes_data()
        response = as_admin.get(target)

        assert response.status_code == 200, response.content
        body = response.json()
        rows = {row["school"]: row for row in body["rows"]}
        assert set(rows) == {"computing_data_science", "business", "unassigned"}
        assert {p["value"] for p in body["paths"]} == set(CAREER_PATHS)
        for row in body["rows"]:
            assert set(row["counts"]) == set(CAREER_PATHS)
            assert row["total"] == sum(row["counts"].values())
        assert rows["computing_data_science"]["counts"]["placement"] == 1
        assert rows["computing_data_science"]["counts"]["undecided"] == 1
        assert rows["computing_data_science"]["counts"]["business"] == 1
        assert rows["business"]["counts"]["higher_studies"] == 1
        # No profile counts as undecided.
        assert rows["business"]["counts"]["undecided"] == 1
        assert rows["unassigned"]["counts"]["placement"] == 1
        assert (
            rows["computing_data_science"]["school_name"]
            == "School of Computing and Data Science"
        )

    def test_totals_add_up_to_students_with_accounts(self, as_admin, outcomes_data):
        """sum(totals) == grand_total == roster students that have an account."""
        target = url("admin-profile-outcomes")
        outcomes_data()
        body = as_admin.get(target).json()

        assert set(body["totals"]) == set(CAREER_PATHS)
        assert sum(body["totals"].values()) == body["grand_total"] == 6
        assert sum(row["total"] for row in body["rows"]) == 6
        assert "verified" in body and "also_attending_placements" in body

    def test_batch_filter_narrows_the_counts(self, as_admin, outcomes_data):
        """?batch= restricts the base set to that graduating batch."""
        target = url("admin-profile-outcomes")
        outcomes_data()
        body_2026 = as_admin.get(target, {"batch": 2026}).json()
        body_2027 = as_admin.get(target, {"batch": 2027}).json()

        assert body_2026["batch"] == 2026
        assert body_2026["grand_total"] == 5
        assert body_2027["grand_total"] == 1
        assert body_2027["totals"]["business"] == 1
        assert sum(body_2027["totals"].values()) == 1

    def test_export_is_csv_with_header_and_total_row(self, as_admin, outcomes_data):
        """The export is text/csv: school,<paths>,total header and a final total row."""
        target = url("admin-profile-outcomes-export")
        outcomes_data()
        response = as_admin.get(target)

        assert response.status_code == 200, getattr(response, "content", b"")
        assert response["Content-Type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(body_of(response).decode())))
        header, data = rows[0], rows[1:]
        assert header[0] == "school" and header[-1] == "total"
        assert set(header[1:-1]) == set(CAREER_PATHS)
        assert data[-1][0] == "total"
        assert int(data[-1][-1]) == 6
        assert {r[0] for r in data[:-1]} == {"computing_data_science", "business", "unassigned"}

    @pytest.mark.parametrize("name", ["admin-profile-outcomes", "admin-profile-outcomes-export"])
    def test_students_and_companies_are_refused(self, name, as_me, as_company):
        """Outcomes are admin only."""
        target = url(name)
        assert as_me.get(target).status_code == 403
        assert as_company.get(target).status_code == 403


# ---------------------------------------------------------------------------
# R4 -- onboarding
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestR4Onboarding:
    def test_get_shows_read_only_roster_facts_and_not_completed(self, me, as_me):
        """The first-login form shows roster facts the student cannot edit."""
        response = as_me.get(url("my-onboarding"))

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["completed"] is False
        assert body["dismissed"] is False
        assert body["student"]["prn"] == PRN_MAIN
        assert body["student"]["department"]
        assert body["student"]["batch"] == 2026
        for key in (
            "phone",
            "personal_email",
            "career_path",
            "career_path_detail",
            "also_attending_placements",
            "headline",
            "summary",
        ):
            assert key in body

    def test_post_without_phone_is_rejected(self, me, as_me):
        """phone is required."""
        response = as_me.post(url("my-onboarding"), {"career_path": "placement"}, format="json")
        assert response.status_code == 400

    def test_post_without_career_path_is_rejected(self, me, as_me):
        """career_path is required."""
        response = as_me.post(url("my-onboarding"), {"phone": "9876543210"}, format="json")
        assert response.status_code == 400

    def test_personal_email_equal_to_college_email_is_rejected(self, me, as_me):
        """The personal address must be a different mailbox from the college one."""
        response = as_me.post(
            url("my-onboarding"),
            {
                "phone": "9876543210",
                "career_path": "placement",
                "personal_email": me.student.email,
            },
            format="json",
        )
        assert response.status_code == 400

    def test_valid_post_completes_onboarding(self, me, as_me):
        """A valid submission sets completion on both the GET shape and the profile."""
        response = as_me.post(
            url("my-onboarding"),
            {
                "phone": "9876543210",
                "career_path": "business",
                "personal_email": "test.student@example.org",
                "also_attending_placements": True,
            },
            format="json",
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["completed"] is True
        assert body["career_path"] == "business"
        assert body["phone"] == "9876543210"
        profile = as_me.get(url("my-profile")).json()
        assert profile["onboarding_completed"] is True
        assert profile["onboarding_completed_at"] is not None
        assert profile["career_path"] == "business"
        assert as_me.get(url("my-onboarding")).json()["completed"] is True

    def test_other_path_needs_a_detail_in_onboarding_too(self, me, as_me):
        """The R2 rule for 'other' applies on the onboarding form."""
        response = as_me.post(
            url("my-onboarding"),
            {"phone": "9876543210", "career_path": "other"},
            format="json",
        )
        assert response.status_code == 400

    def test_dismiss_returns_204_and_does_not_complete(self, me, as_me):
        """'Later' hides the prompt but the student is still not onboarded."""
        response = as_me.post(url("my-onboarding-dismiss"))

        assert response.status_code == 204
        body = as_me.get(url("my-onboarding")).json()
        assert body["dismissed"] is True
        assert body["completed"] is False

    def test_admin_stats_count_completed_onboarding(self, me, as_me, as_admin):
        """admin/stats gains an onboarding_completed count."""
        url("my-onboarding")  # the feature must exist before the count means anything
        before = as_admin.get(url("admin-profile-stats")).json()
        assert "onboarding_completed" in before, "admin/stats has no onboarding_completed"
        assert before["onboarding_completed"] == 0

        as_me.post(
            url("my-onboarding"),
            {"phone": "9876543210", "career_path": "placement"},
            format="json",
        )

        assert as_admin.get(url("admin-profile-stats")).json()["onboarding_completed"] == 1


# ---------------------------------------------------------------------------
# R5 -- transcript upload and CGPA cross-check
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestR5Transcript:
    def test_clean_transcript_is_accepted_and_needs_no_review(self, me, uploaded_transcript):
        """Printed == recomputed == roster: stored, parsed, nothing to review."""
        response = uploaded_transcript("clean")

        assert response.status_code == 201, response.content
        body = response.json()
        assert Decimal(body["parsed_cgpa"]) == Decimal("8.50")
        assert Decimal(body["recomputed_cgpa"]) == Decimal("8.50")
        assert body["cgpa_matches_roster"] is True
        assert body["cgpa_review_status"] == "not_needed"
        assert body["transcript_prn"] == PRN_MAIN
        assert body["transcript_school"] == "School of Computing and Data Science"
        assert body["transcript_degree"] == "BTech"
        assert body["transcript_filename"] == "transcript_clean.pdf"
        assert body["transcript_url"] == "/api/profiles/me/transcript/file"

    def test_tampered_printed_cgpa_opens_a_review_and_is_audited(self, me, uploaded_transcript):
        """Printed differs from the recomputed value by more than 0.02: flag it."""
        url("my-transcript")
        before = audit_count("cgpa_mismatch_flagged")

        response = uploaded_transcript("tampered")

        assert response.status_code == 201, response.content
        body = response.json()
        assert Decimal(body["parsed_cgpa"]) == Decimal("9.40")
        assert Decimal(body["recomputed_cgpa"]) == Decimal("8.50")
        assert body["cgpa_review_status"] == "open"
        assert audit_count("cgpa_mismatch_flagged") == before + 1

    def test_roster_mismatch_opens_a_review(self, me, uploaded_transcript):
        """Printed matches recomputed but differs from the roster by more than 0.05."""
        response = uploaded_transcript("roster_mismatch")

        assert response.status_code == 201, response.content
        body = response.json()
        assert Decimal(body["parsed_cgpa"]) == Decimal(body["recomputed_cgpa"])
        assert body["cgpa_matches_roster"] is False
        assert body["cgpa_review_status"] == "open"

    def test_image_only_transcript_is_stored_and_flagged_without_a_cgpa(
        self, me, as_me, uploaded_transcript
    ):
        """An unreadable scan is kept for the admin but yields no CGPA and an open review."""
        response = uploaded_transcript("image_only")

        assert response.status_code == 201, response.content
        body = response.json()
        assert body["parsed_cgpa"] is None
        assert body["recomputed_cgpa"] is None
        assert body["cgpa_review_status"] == "open"
        assert as_me.get(url("my-transcript-file")).status_code == 200

    def test_wrong_prn_is_refused_logged_and_not_stored(
        self, me, as_me, uploaded_transcript, settings
    ):
        """A transcript naming another PRN is the binding check: 400, audit row, no file."""
        url("my-transcript")
        before = audit_count("transcript_prn_mismatch")

        response = uploaded_transcript("wrong_prn")

        assert response.status_code == 400
        assert response.json()["reason"] == "prn_mismatch"
        assert "detail" in response.json()
        assert audit_count("transcript_prn_mismatch") == before + 1
        assert media_pdfs(settings) == []
        assert as_me.get(url("my-transcript-file")).status_code == 404
        assert as_me.get(url("my-profile")).json()["transcript_filename"] == ""

    def test_split_semester_with_contd_heading_is_parsed_whole(self, me, uploaded_transcript):
        """A semester continued on a new page must not drop rows or semesters."""
        response = uploaded_transcript("contd_split")

        assert response.status_code == 201, response.content
        body = response.json()
        # Recomputing needs all three semester totals; losing the continued one
        # would move the recomputed value away from the printed 8.50.
        assert Decimal(body["recomputed_cgpa"]) == Decimal("8.50")
        assert Decimal(body["parsed_cgpa"]) == Decimal("8.50")
        assert body["cgpa_review_status"] == "not_needed"

    @pytest.mark.parametrize("kind", list(CASES))
    def test_roster_cgpa_is_never_written(self, me, uploaded_transcript, kind):
        """Student.cgpa belongs to the roster; no upload outcome may change it."""
        url("my-transcript")
        uploaded_transcript(kind)

        me.student.refresh_from_db()
        assert me.student.cgpa == Decimal(CASES[kind].roster_cgpa)

    def test_non_pdf_is_rejected(self, me, as_me):
        """Only PDF transcripts are accepted."""
        fake = SimpleUploadedFile(
            "transcript.txt", b"Cumulative GPA: 9.9", content_type="text/plain"
        )

        response = as_me.post(url("my-transcript"), {"file": fake}, format="multipart")

        assert response.status_code == 400

    def test_missing_file_is_rejected(self, me, as_me):
        """A POST without a file is a 400."""
        assert as_me.post(url("my-transcript"), {}, format="multipart").status_code == 400

    def test_confirm_cgpa_sets_only_the_confirmed_value(self, me, as_me, uploaded_transcript):
        """The student's typed value goes to confirmed_cgpa and nowhere else."""
        uploaded_transcript("tampered")

        response = as_me.post(url("my-confirm-cgpa"), {"cgpa": "8.40"}, format="json")

        assert response.status_code == 200, response.content
        body = as_me.get(url("my-profile")).json()
        assert Decimal(body["confirmed_cgpa"]) == Decimal("8.40")
        assert Decimal(body["parsed_cgpa"]) == Decimal("9.40")
        assert Decimal(body["recomputed_cgpa"]) == Decimal("8.50")
        me.student.refresh_from_db()
        assert me.student.cgpa == Decimal("9.40")  # the roster value, untouched

    @pytest.mark.parametrize("bad", ["10.5", "-1", "abc", ""])
    def test_confirm_cgpa_rejects_out_of_range(self, me, as_me, bad):
        """CGPA is between 0 and 10."""
        response = as_me.post(url("my-confirm-cgpa"), {"cgpa": bad}, format="json")
        assert response.status_code == 400

    def test_admin_resolves_a_cgpa_review(self, me, as_admin, as_me, uploaded_transcript):
        """Resolving needs the admin, sets status to resolved and leaves a trail."""
        from core.models import AuditLog

        uploaded_transcript("tampered")
        target = url("admin-profile-cgpa-review", me.student_id)
        assert as_me.post(target, {"status": "resolved"}, format="json").status_code == 403

        response = as_admin.post(
            target, {"status": "resolved", "note": "Checked the paper copy."}, format="json"
        )

        assert response.status_code == 200, response.content
        detail = as_admin.get(url("admin-profile-detail", me.student_id)).json()
        assert detail["cgpa_review_status"] == "resolved"
        # The resolve itself must be audited. Counting all rows was not enough:
        # the detail read above writes its own identity_accessed row.
        resolved = AuditLog.objects.filter(action="cgpa_review_resolved", target=me.student.prn)
        assert resolved.count() == 1, list(AuditLog.objects.values_list("action", "target"))

    def test_company_never_gets_the_transcript_even_for_a_visible_verified_profile(
        self, me, as_company, as_admin, uploaded_transcript
    ):
        """Companies never see transcripts: the route is always 404."""
        from profiles.models import Visibility

        assert uploaded_transcript("clean").status_code == 201
        me.visibility = Visibility.ALL
        # Save only this field: `me` was loaded before the API calls above,
        # and a full save() would overwrite what they just wrote.
        me.save(update_fields=["visibility", "updated_at"])
        as_admin.post(
            url("admin-profile-verification", me.student_id),
            {"is_verified": True},
            format="json",
        )
        assert as_company.get(url("company-profile-detail", me.student_id)).status_code == 200

        response = as_company.get(url("company-profile-transcript", me.student_id))

        assert response.status_code == 404

    def test_company_payload_has_no_transcript_or_cgpa_fields(
        self, me, as_company, uploaded_transcript
    ):
        """Roster CGPA stays under student.cgpa; the parsed fields are not exposed."""
        from profiles.models import Visibility

        assert uploaded_transcript("clean").status_code == 201
        me.visibility = Visibility.ALL
        # Save only this field: `me` was loaded before the API calls above,
        # and a full save() would overwrite what they just wrote.
        me.save(update_fields=["visibility", "updated_at"])

        body = as_company.get(url("company-profile-detail", me.student_id)).json()

        assert [k for k in body if k.startswith("transcript")] == []
        assert [k for k in body if k.endswith("_cgpa")] == []
        assert "cgpa_matches_roster" not in body
        assert "cgpa_review_status" not in body
        assert body["student"]["cgpa"] is not None

    def test_resume_upload_never_sets_a_cgpa_field(self, me, as_me, uploaded_resume):
        """A resume saying 'CGPA: 9.90' must not reach any *_cgpa field."""
        lines = [
            "Test Student",
            "B.Tech Computer Science",
            "CGPA: 9.90",
            "Cumulative GPA: 9.90",
            "Experience: 2 years of backend development",
        ]

        response, _ = uploaded_resume(lines)

        assert response.status_code == 201, response.content
        body = as_me.get(url("my-profile")).json()
        for key in ("parsed_cgpa", "recomputed_cgpa", "confirmed_cgpa"):
            assert key in body, f"own profile has no {key}"
            assert body[key] is None
        me.student.refresh_from_db()
        assert me.student.cgpa == Decimal("8.50")

    def test_resume_upload_leaves_transcript_cgpa_untouched(
        self, me, as_me, uploaded_transcript, uploaded_resume
    ):
        """A later resume upload cannot overwrite what the transcript established."""
        assert uploaded_transcript("clean").status_code == 201
        before = as_me.get(url("my-profile")).json()

        uploaded_resume(["Test Student", "CGPA: 9.90", "Cumulative GPA: 9.90"])

        after = as_me.get(url("my-profile")).json()
        for key in ("parsed_cgpa", "recomputed_cgpa", "confirmed_cgpa", "cgpa_review_status"):
            assert after[key] == before[key]
        assert Decimal(after["parsed_cgpa"]) == Decimal("8.50")

    def test_own_transcript_file_is_served_and_404_when_absent(
        self, me, as_me, uploaded_transcript
    ):
        """The student can re-open their own transcript."""
        assert as_me.get(url("my-transcript-file")).status_code == 404

        uploaded_transcript("clean")
        response = as_me.get(url("my-transcript-file"))

        assert response.status_code == 200
        assert body_of(response).startswith(b"%PDF")
        assert "transcript_clean.pdf" in response["Content-Disposition"]
