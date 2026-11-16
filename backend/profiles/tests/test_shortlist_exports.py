"""Stage 4: `?shortlisted=true`, the CV zip and the contact zip (unit level)."""

import base64
import csv
import io
import logging
import zipfile

import pyzipper
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from core.models import AuditLog
from profiles import exports
from profiles.models import CompanyShortlist

pytestmark = pytest.mark.django_db


def pick(company, profile):
    CompanyShortlist.objects.update_or_create(
        company=company, profile=profile, defaults={"source": "manual"}
    )


def with_resume(profile, name="cv.pdf", data=b"%PDF-1.4 resume"):
    profile.resume.save(name, ContentFile(data), save=False)
    profile.resume_filename = name
    profile.save()


def body(response):
    return b"".join(response.streaming_content) if response.streaming else response.content


def contacts(payload):
    archive = pyzipper.AESZipFile(io.BytesIO(base64.b64decode(payload["zip_base64"])))
    archive.setpassword(payload["password"].encode())
    return list(csv.DictReader(io.StringIO(archive.read("contacts.csv").decode())))


# --- the filename rule -----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Aditi Verma", "Aditi Verma"),
        ("../../etc/passwd", "_.._etc_passwd"),
        ("a/b\\c", "a_b_c"),
        ("..", "student"),
        ("  .hidden", "hidden"),
        ("Nul\x00l\nName", "Nul_l_Name"),
        ("", "student"),
    ],
)
def test_safe_part_cannot_escape_or_be_empty(raw, expected):
    cleaned = exports.safe_part(raw)
    assert "/" not in cleaned and "\\" not in cleaned and not cleaned.startswith(".")
    assert cleaned == expected


def test_safe_part_is_bounded():
    assert len(exports.safe_part("x" * 500)) <= 80


@pytest.mark.parametrize("name, ext", [("cv.PDF", "pdf"), ("cv", "bin"), ("a.p/d", "bin"), ("a.tar.gz", "gz")])
def test_safe_extension(name, ext):
    assert exports.safe_extension(name) == ext


def test_csv_text_and_phone_neutralise_formulas():
    assert exports.csv_text("=1+1") == "'=1+1"
    assert exports.csv_text("@x") == "'@x" and exports.csv_text("ok") == "ok"
    assert exports.csv_phone("+91 98765 43210") == "+91 98765 43210"
    assert exports.csv_phone("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert exports.csv_phone("+cmd|x") == "'+cmd|x"


def test_the_password_is_long_and_random():
    first, second = exports.new_password(), exports.new_password()
    assert len(first) >= 16 and first != second


# --- the listing -----------------------------------------------------------


def test_query_count_does_not_grow_with_rows(as_company, company, make_student, django_assert_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    listing = reverse("company-profile-list")
    pick(company, make_student(prn="220200911", email="a1@college.edu"))
    with CaptureQueriesContext(connection) as small:
        assert as_company.get(listing, {"shortlisted": "true"}).status_code == 200
    for i in range(2, 8):
        pick(company, make_student(prn=f"22020091{i}", email=f"a{i}@college.edu"))
    with CaptureQueriesContext(connection) as big:
        response = as_company.get(listing, {"shortlisted": "true"})
    assert len(response.json()["results"]) == 7
    assert len(big) == len(small)
    assert all(row["is_shortlisted"] is True for row in response.json()["results"])


def test_shortlisted_false_is_everyone_else(as_company, company, profile, other_profile):
    pick(company, profile)
    rows = as_company.get(reverse("company-profile-list"), {"shortlisted": "false"}).json()["results"]
    assert [r["prn"] for r in rows] == [other_profile.prn]


def test_a_recruiter_without_a_company_has_an_empty_shortlist(profile, company):
    from accounts.models import User
    from conftest import _client_for

    bare = User.objects.create_company(
        email="bare@x.example", password="CompanyPass!234", full_name="Bare"
    )
    pick(company, profile)
    client = _client_for(bare)
    assert client.get(reverse("company-profile-list"), {"shortlisted": "true"}).json()["results"] == []


# --- the exports -----------------------------------------------------------


def test_route_order_shortlist_is_not_a_student_id(as_company):
    assert reverse("company-shortlist-resumes") == "/api/profiles/students/shortlist/resumes"
    assert reverse("company-shortlist-contacts") == "/api/profiles/students/shortlist/contacts"
    # A bare `shortlist` segment is a detail lookup that finds nothing.
    assert as_company.get("/api/profiles/students/shortlist").status_code == 404


def test_zip_names_are_sanitised_and_do_not_escape(as_company, company, make_student):
    evil = make_student(prn="220200911", email="e@college.edu", full_name="../../etc/passwd\\x")
    plain = make_student(prn="220200912", email="p@college.edu", full_name="Plain Name")
    for p in (evil, plain):
        with_resume(p)
        pick(company, p)
    archive = zipfile.ZipFile(io.BytesIO(body(as_company.get(reverse("company-shortlist-resumes")))))
    names = archive.namelist()
    assert len(names) == 2 and len(set(names)) == 2
    for name in names:
        assert "/" not in name and "\\" not in name and not name.startswith(".")
    assert "220200912-Plain Name.pdf" in names


def test_a_missing_file_is_skipped_not_a_500(as_company, company, profile):
    with_resume(profile)
    profile.resume.storage.delete(profile.resume.name)
    pick(company, profile)
    response = as_company.get(reverse("company-shortlist-resumes"))
    assert response.status_code == 200 and response["X-Skipped-Without-Resume"] == "1"
    archive = zipfile.ZipFile(io.BytesIO(body(response)))
    assert archive.namelist() == ["SKIPPED.txt"]


def test_no_skipped_file_when_everyone_has_a_resume(as_company, company, profile):
    with_resume(profile)
    pick(company, profile)
    response = as_company.get(reverse("company-shortlist-resumes"))
    assert response["X-Skipped-Without-Resume"] == "0"
    assert zipfile.ZipFile(io.BytesIO(body(response))).namelist() == [f"{profile.prn}-Aarav Mehta.pdf"]


def test_the_hidden_student_is_in_neither_export_nor_listing(as_company, company, profile, other_profile):
    for p in (profile, other_profile):
        with_resume(p)
        pick(company, p)
    profile.visibility = "hidden"
    profile.save()
    listing = as_company.get(reverse("company-profile-list"), {"shortlisted": "true"}).json()["results"]
    assert [r["prn"] for r in listing] == [other_profile.prn]
    names = zipfile.ZipFile(io.BytesIO(body(as_company.get(reverse("company-shortlist-resumes"))))).namelist()
    assert not any(n.startswith(profile.prn) for n in names)
    payload = as_company.post(reverse("company-shortlist-contacts")).json()
    assert [r["prn"] for r in contacts(payload)] == [other_profile.prn]


def test_another_company_exports_nothing_of_mine(company, profile, make_student):
    from accounts.models import Company, User
    from conftest import _client_for

    pick(company, profile)
    with_resume(profile)
    other = Company.objects.create(name="Other Co", email="o@other.example")
    recruiter = User.objects.create_company(
        email="r@other.example", password="CompanyPass!234", full_name="R", company=other
    )
    client = _client_for(recruiter)
    assert contacts(client.post(reverse("company-shortlist-contacts")).json()) == []
    assert zipfile.ZipFile(io.BytesIO(body(client.get(reverse("company-shortlist-resumes"))))).namelist() == []


def test_contacts_csv_columns_neutralisation_and_cgpa(as_company, company, make_student, admin_user):
    p = make_student(
        prn="220200913", email="f@college.edu", full_name="=HYPERLINK(1)", cgpa="7.50",
        confirmed_cgpa="9.99",
    )
    p.mark_verified(admin_user)
    pick(company, p)
    payload = as_company.post(reverse("company-shortlist-contacts")).json()
    (row,) = contacts(payload)
    assert list(row) == exports.CONTACT_COLUMNS
    assert row["full_name"] == "'=HYPERLINK(1)"
    assert row["cgpa"] == "7.50" and row["email"] == "f@college.edu"
    assert row["contact_available"] == "true"


def test_the_password_is_nowhere_but_the_response(as_company, company, profile, caplog):
    pick(company, profile)
    with caplog.at_level(logging.DEBUG):
        payload = as_company.post(reverse("company-shortlist-contacts")).json()
    password = payload["password"]
    assert len(password) >= 16
    assert password.encode() not in base64.b64decode(payload["zip_base64"])
    assert password not in caplog.text
    for entry in AuditLog.objects.all():
        assert password not in str(entry.detail) and password not in entry.target
    assert AuditLog.objects.get(action="shortlist_exported").detail["count"] == 1


def test_exports_reject_query_parameters(as_company):
    assert as_company.get(reverse("company-shortlist-resumes"), {"x": "1"}).status_code == 400
    assert as_company.post(reverse("company-shortlist-contacts") + "?x=1").status_code == 400
