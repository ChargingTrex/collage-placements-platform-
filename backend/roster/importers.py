"""
Roster CSV import.

Designed around the failure case rather than the happy one: a placement
officer uploading 400 rows from a spreadsheet needs to know exactly which
rows were wrong and why, not that "the upload failed". Every row is validated
independently; good rows are saved, bad rows come back with per-field errors
and their 1-based line number as it appears in the spreadsheet.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from roster.models import Student, normalise_email, normalise_prn
from roster.reference import is_known_programme, is_known_school, school_for_programme

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"prn", "email", "full_name", "department", "batch"}
OPTIONAL_COLUMNS = {"cgpa", "phone", "is_placement_eligible", "school", "year_of_study"}
KNOWN_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS

TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY = {"0", "false", "no", "n", "f"}


class RosterFormatError(Exception):
    """The file is unusable as a whole -- wrong columns, not a CSV, empty."""


@dataclass
class RowError:
    row: int  # 1-based line number in the uploaded file, header included
    prn: str
    errors: dict[str, list[str]]

    def as_dict(self) -> dict:
        return {"row": self.row, "prn": self.prn, "errors": self.errors}


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[RowError] = field(default_factory=list)
    # Rows saved as given whose department/school is not in roster.reference.
    # Not errors: the admin decides whether the code list or the file is wrong.
    unknown_codes: list[dict] = field(default_factory=list)

    @property
    def processed(self) -> int:
        return self.created + self.updated + self.unchanged

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "processed": self.processed,
            "error_count": len(self.errors),
            "errors": [error.as_dict() for error in self.errors],
            "unknown_codes": list(self.unknown_codes),
        }


def _decode(upload) -> str:
    raw = upload.read() if hasattr(upload, "read") else upload
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RosterFormatError("File is not readable as text. Save it as UTF-8 CSV.")


def _parse_cgpa(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError("Enter a number between 0 and 10.")


def _parse_bool(value: str, default: bool = True) -> bool:
    value = (value or "").strip().lower()
    if not value:
        return default
    if value in TRUTHY:
        return True
    if value in FALSY:
        return False
    raise ValueError("Enter true or false.")


def _parse_batch(value: str) -> int:
    value = (value or "").strip()
    if not value:
        raise ValueError("This field is required.")
    try:
        return int(float(value))  # spreadsheets export 2026 as "2026.0"
    except ValueError:
        raise ValueError("Enter a graduating year, e.g. 2026.")


def _parse_year_of_study(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        year = int(float(value))
    except ValueError:
        raise ValueError("Enter a year of study, e.g. 3.")
    if not 1 <= year <= 10:
        raise ValueError("Enter a year of study, e.g. 3.")
    return year


def _check_codes(
    result: ImportResult, line: int, prn: str, department: str, school: str
) -> None:
    """Record (never fix) a department or school that is not in the code list."""
    unknown = []
    if department and not is_known_programme(department):
        unknown.append(("department", department))
    if school and not is_known_school(school):
        unknown.append(("school", school))
    for field_name, value in unknown:
        result.unknown_codes.append(
            {"row": line, "prn": prn, "field": field_name, "value": value}
        )
        # The raw value goes in the log so it can be searched for later.
        logger.warning(
            "Roster row %s (PRN %s): unknown %s %r stored as given.",
            line, prn, field_name, value,
        )


def import_roster_csv(upload, *, dry_run: bool = False) -> ImportResult:
    """
    Parse and apply a roster CSV.

    Upsert by PRN: an existing student is updated in place, so re-uploading a
    corrected spreadsheet is the normal way to fix data rather than an error.
    """
    text = _decode(upload)
    if not text.strip():
        raise RosterFormatError("The file is empty.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise RosterFormatError("No header row found.")

    headers = {(name or "").strip().lower() for name in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise RosterFormatError(
            "Missing required column(s): "
            + ", ".join(sorted(missing))
            + ". Expected header: "
            + ", ".join(sorted(REQUIRED_COLUMNS | OPTIONAL_COLUMNS))
            + "."
        )

    result = ImportResult()

    with transaction.atomic():
        for offset, raw_row in enumerate(reader, start=2):  # line 1 is the header
            row = {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in raw_row.items()
                if key is not None
            }
            errors = _apply_row(row, result, offset)
            if errors:
                result.errors.append(
                    RowError(row=offset, prn=row.get("prn", ""), errors=errors)
                )

        if dry_run:
            transaction.set_rollback(True)

    return result


def _apply_row(
    row: dict[str, str], result: ImportResult, line: int = 0
) -> dict[str, list[str]]:
    """Validate and save one row. Returns per-field errors, empty when saved."""
    errors: dict[str, list[str]] = {}

    prn = normalise_prn(row.get("prn", ""))
    email = normalise_email(row.get("email", ""))
    if not prn:
        errors["prn"] = ["This field is required."]
    if not email:
        errors["email"] = ["This field is required."]

    for parser, key in (
        (_parse_batch, "batch"),
        (_parse_cgpa, "cgpa"),
        (_parse_year_of_study, "year_of_study"),
    ):
        try:
            row[key] = parser(row.get(key, ""))  # type: ignore[assignment]
        except ValueError as exc:
            errors.setdefault(key, []).append(str(exc))

    try:
        eligible = _parse_bool(row.get("is_placement_eligible", ""))
    except ValueError as exc:
        errors.setdefault("is_placement_eligible", []).append(str(exc))
        eligible = True

    if errors:
        return errors

    # The email may already belong to a *different* PRN -- two roster rows
    # cannot share one college mailbox, and letting this through would make
    # roster matching ambiguous at signup.
    clash = Student.objects.filter(email=email).exclude(prn=prn).first()
    if clash:
        return {"email": [f"Already on the roster under PRN {clash.prn}."]}

    student = Student.objects.filter(prn=prn).first()
    is_new = student is None
    if is_new:
        student = Student(prn=prn)

    before = _snapshot(student)
    student.email = email
    student.full_name = row.get("full_name", "")
    student.department = row.get("department", "")
    student.batch = row["batch"]  # type: ignore[assignment]
    student.cgpa = row["cgpa"]  # type: ignore[assignment]
    student.phone = row.get("phone", "")
    student.is_placement_eligible = eligible

    # `school` / `year_of_study` are optional columns. When blank, school is
    # derived from the programme if that is unambiguous; otherwise the stored
    # value is kept so re-uploading an old-format file does not wipe it.
    school = row.get("school", "") or school_for_programme(student.department) or ""
    if school:
        student.school = school
    if row.get("year_of_study") is not None:
        student.year_of_study = row["year_of_study"]  # type: ignore[assignment]

    try:
        student.full_clean()
    except ValidationError as exc:
        return {field: [str(m) for m in messages] for field, messages in exc.message_dict.items()}

    student.save()
    _check_codes(result, line, prn, student.department, row.get("school", ""))

    if is_new:
        result.created += 1
    elif _snapshot(student) != before:
        result.updated += 1
    else:
        result.unchanged += 1
    return {}


def _snapshot(student: Student) -> tuple:
    return (
        student.email,
        student.full_name,
        student.department,
        student.batch,
        student.cgpa,
        student.phone,
        student.is_placement_eligible,
        student.school,
        student.year_of_study,
    )
