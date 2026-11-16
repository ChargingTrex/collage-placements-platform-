"""
Recruiter exports of the company's shortlist (Stage 4).

Two downloads, both built on the D27 shortlist and `visible_to`, so a student
who goes hidden after being shortlisted leaves both at once:

* a ZIP of the current resumes (`build_resume_zip`), and
* an AES-256 ZIP holding `contacts.csv` (`build_contacts_zip`), whose random
  password is returned to the caller once and kept nowhere else.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import shutil
import tempfile
import unicodedata
import zipfile

from django.db.models import DateTimeField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from opportunities.models import Application
from opportunities.shortlist import PICK_STATUSES, shortlist_condition
from profiles.models import CompanyShortlist, StudentProfile

CONTACT_COLUMNS = [
    "prn", "full_name", "department", "programme", "batch", "cgpa",
    "email", "phone", "contact_available", "shortlisted_on",
]

#: Characters allowed in a name inside the archive. Everything else (path
#: separators, control characters, quotes, wildcards, ...) becomes "_".
_UNSAFE = re.compile(r"[^\w .'()&-]", re.UNICODE)
_NAME_MAX = 80


def safe_part(value: str, fallback: str = "student") -> str:
    """
    One path component made from user text.

    NFKC-normalised, anything but letters, digits, space and `. ' ( ) & -`
    replaced by `_`, whitespace collapsed, leading dots/spaces/dashes removed
    (no `..`, no hidden file), and cut to 80 characters. Never contains `/`
    or `\\`, so it cannot climb out of the archive.
    """
    text = unicodedata.normalize("NFKC", value or "")
    text = _UNSAFE.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip().lstrip(". -")
    text = text[:_NAME_MAX].rstrip(". ")
    return text or fallback


def safe_extension(filename: str) -> str:
    """The resume's own extension, lower-cased and limited to 1-5 alphanumerics."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if re.fullmatch(r"[a-z0-9]{1,5}", ext) else "bin"


def csv_text(value: str) -> str:
    """Stop a spreadsheet reading student-typed text as a formula."""
    value = value or ""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


_PHONE = re.compile(r"\+?[\d\s().-]+")


def csv_phone(value: str) -> str:
    """A phone may start with `+` (country code); anything else odd is quoted."""
    value = value or ""
    return value if _PHONE.fullmatch(value) else csv_text(value)


def shortlist_profiles(user):
    """
    The company's shortlist: `visible_to(company)` and (manual or picked
    application), one row per profile, ordered by PRN, with `shortlisted_on`.
    """
    picked = (
        Application.objects.filter(
            opportunity__company=user.company_id,
            profile=OuterRef("pk"),
            status__in=PICK_STATUSES,
        )
        .order_by("-updated_at")
        .values("updated_at")[:1]
    )
    manual = (
        CompanyShortlist.objects.filter(
            company=user.company_id,
            profile=OuterRef("pk"),
            source=CompanyShortlist.Source.MANUAL,
        )
        .order_by("-updated_at")
        .values("updated_at")[:1]
    )
    return (
        StudentProfile.objects.visible_to(user)
        .filter(shortlist_condition(user.company_id))
        .select_related("student")
        .annotate(
            shortlisted_on=Coalesce(
                Subquery(manual, output_field=DateTimeField()),
                Subquery(picked, output_field=DateTimeField()),
            )
        )
        .order_by("student__prn")
    )


def build_resume_zip(profiles):
    """
    Returns `(file, count, skipped)`: a rewound temp file holding the ZIP.

    Resumes are copied one at a time into a temporary file, so memory holds
    one chunk, not the shortlist. A student with no resume (or whose file is
    gone from storage) is skipped and listed in `SKIPPED.txt`.
    """
    archive_file = tempfile.TemporaryFile()  # handed to FileResponse, which closes it
    skipped: list[str] = []
    used: set[str] = set()
    count = 0
    with zipfile.ZipFile(archive_file, "w", zipfile.ZIP_DEFLATED) as archive:
        for profile in profiles:
            student = profile.student
            label = f"{student.prn} - {student.full_name}"
            if not profile.resume:
                skipped.append(f"{label}: no resume uploaded")
                continue
            try:
                source = profile.resume.open("rb")
            except OSError:
                skipped.append(f"{label}: resume file unavailable")
                continue
            ext = safe_extension(profile.resume_filename or profile.resume.name)
            stem = f"{safe_part(student.prn, 'prn')}-{safe_part(student.full_name)}"
            name, suffix = f"{stem}.{ext}", 2
            while name.lower() in used:  # defensive: the PRN prefix is already unique
                name = f"{stem}-{suffix}.{ext}"
                suffix += 1
            used.add(name.lower())
            with source, archive.open(name, "w") as target:
                shutil.copyfileobj(source, target, 64 * 1024)
            count += 1
        if skipped:
            lines = ["Students on the shortlist whose resume could not be included:", ""]
            lines += [re.sub(r"[\r\n]+", " ", line) for line in skipped]
            archive.writestr("SKIPPED.txt", "\n".join(lines) + "\n")
    archive_file.seek(0)
    return archive_file, count, len(skipped)


def new_password() -> str:
    """24 url-safe characters (144 bits) from the OS CSPRNG."""
    return secrets.token_urlsafe(18)


def contacts_csv(profiles) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CONTACT_COLUMNS)
    for profile in profiles:
        student = profile.student
        verified = profile.is_verified
        writer.writerow([
            student.prn,
            csv_text(student.full_name),
            csv_text(student.department),
            csv_text(student.programme),
            student.batch if student.batch is not None else "",
            "" if student.cgpa is None else student.cgpa,
            student.email if verified else "",
            csv_phone(profile.phone) if verified else "",
            "true" if verified else "false",
            profile.shortlisted_on.date().isoformat() if profile.shortlisted_on else "",
        ])
    return out.getvalue()


def build_contacts_zip(profiles, password: str) -> bytes:
    """An AES-256 ZIP with `contacts.csv`; the password is used, never stored."""
    import pyzipper

    buffer = io.BytesIO()
    with pyzipper.AESZipFile(
        buffer, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as archive:
        archive.setpassword(password.encode())
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr("contacts.csv", contacts_csv(profiles).encode("utf-8"))
    return buffer.getvalue()
