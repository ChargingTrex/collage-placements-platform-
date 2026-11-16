#!/usr/bin/env python
"""
Demo-script E2E: walks the 15-minute demo (WEEKEND_DEMO_PLAN.md, "Monday: the
demo") against a running server, one group of checks per beat.

    cd backend
    export LLM_ENABLED=false DATABASE_URL=sqlite:////tmp/demo.sqlite3 MEDIA_ROOT=/tmp/demo-media
    ../.venv/bin/python manage.py migrate
    ../.venv/bin/python manage.py seed_demo --with-students
    ../.venv/bin/python manage.py seed_outcomes_demo
    ../.venv/bin/python manage.py runserver 127.0.0.1:8791 --noreload
    ../.venv/bin/python checkpoints/e2e_demo.py --base-url http://127.0.0.1:8791

Modes
    (default)   deterministic: nothing asserts on what the LLM or embeddings
                say, so the output is the same with the LLM off.
    --live-ai   adds the checks that need Gemma and embeddings (the JD is read
                by the model, the vector index answers, a role category is made).
    --public    for a server running with DEBUG off (serve_demo). Runs only the
                public-link security rules and needs no seed data.

Beats 1 and the persona sign-in depend on endpoints another builder is adding
(`/api/auth/admin/users`, `/api/auth/demo/...`). Those checks are in a marked
section and are reported SKIP while the endpoint answers 404.

The audit-log check (beat 4) reads the `core_auditlog` table straight from the
SQLite file (--db, default taken from DATABASE_URL), because the API has no
audit-log endpoint. Without a readable file it is reported SKIP.

Standard library plus, for the transcript PDFs, the backend's own reportlab
(run it with the project venv). Synthetic data only. Exits 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent

#: Seeded by `seed_demo --with-students` (see that command's DEMO_STUDENTS).
AARAV, DIYA, ROHAN, SANA = "220200901", "220200902", "220200903", "220200904"
SEEDED = {
    AARAV: "all",  # public, verified
    SANA: "all",  # public, verified
    ROHAN: "shortlisted",  # shortlisted by Acme only
    DIYA: "hidden",
}
JD = (
    "Backend Engineer. Build and ship REST APIs in Python and Django, backed by PostgreSQL, "
    "deployed with Docker. Git and code review every day. Celery and AWS are a plus."
)
BREAKDOWN_KEYS = {"semantic", "skills"}

PUBLIC_DEBUG_MARKERS = (
    "Django tried these URL patterns",
    "You're seeing this error because you have DEBUG",
    "Traceback (most recent call last)",
    "<title>Page not found at",
)
OTP_KEYS = {"debug_otp", "otp", "otp_code", "code", "sign_in_code", "signin_code", "login_code"}


class Run:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.results: list[tuple[str, str]] = []  # (PASS|FAIL|SKIP, name)
        self.statuses: list[int] = []
        self.bodies: list[tuple[str, int, bytes]] = []  # (path, status, raw)

    def call(self, method, path, *, token=None, body=None, files=None, accept="application/json"):
        """(status, parsed JSON or None, raw bytes, headers). Never raises on HTTP errors."""
        headers = {"Accept": accept}
        data = None
        if files is not None:
            boundary = uuid.uuid4().hex
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            data = _multipart(boundary, files)
        elif body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status, raw, resp_headers = response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            status, raw, resp_headers = exc.code, exc.read(), exc.headers
        self.statuses.append(status)
        self.bodies.append((path, status, raw))
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return status, parsed, raw, resp_headers

    def get(self, path, token=None):
        status, data, _, _ = self.call("GET", path, token=token)
        return status, data

    def pages(self, path, token):
        rows, url = [], path
        while url:
            if url.startswith("http"):
                url = url[len(self.base):]
            status, data = self.get(url, token)
            if status != 200:
                return None
            rows += data["results"]
            url = data.get("next")
        return rows

    def login(self, identifier, password):
        status, data, _, _ = self.call("POST", "/api/auth/login", body={"identifier": identifier, "password": password})
        return data["tokens"]["access"] if status == 200 else None

    def check(self, name: str, ok: bool, reason: str = "") -> bool:
        verdict = "PASS" if ok else "FAIL"
        self.results.append((verdict, name))
        # The reason is printed only on failure, so a passing run's output
        # does not depend on counts or timings that vary between runs.
        print(f"{verdict}  {name}" + (f" - {reason}" if not ok and reason else ""), flush=True)
        return bool(ok)

    def skip(self, name: str, why: str) -> None:
        self.results.append(("SKIP", name))
        print(f"SKIP  {name} - {why}", flush=True)

    def header(self, text: str) -> None:
        print(f"\n== {text}", flush=True)


def _multipart(boundary: str, files: dict) -> bytes:
    out = b""
    for field, value in files.items():
        out += f"--{boundary}\r\n".encode()
        if isinstance(value, tuple):
            filename, content = value
            out += (
                f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode() + content + b"\r\n"
        else:
            out += f'Content-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode()
    return out + f"--{boundary}--\r\n".encode()


# --- audit log (read straight from SQLite) ---------------------------------


class AuditLog:
    def __init__(self, path: str | None):
        self.path = path if path and Path(path).exists() else None

    @classmethod
    def from_args(cls, db: str | None):
        if db:
            return cls(db)
        url = os.environ.get("DATABASE_URL", "")
        if url.startswith("sqlite:///"):
            return cls(url[len("sqlite:///"):])
        default = BACKEND / "db.sqlite3"
        return cls(str(default) if default.exists() else None)

    def count(self, action: str, target: str) -> int | None:
        if not self.path:
            return None
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10) as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM core_auditlog WHERE action=? AND target=?", (action, target)
                ).fetchone()[0]
        except sqlite3.Error:
            return None


# --- helpers ----------------------------------------------------------------


def render_transcript(prn: str, name: str, cgpa: str) -> bytes:
    """A synthetic transcript PDF, drawn with the backend's own fixture code."""
    sys.path.insert(0, str(BACKEND))
    from checkpoints.transcript_fixtures import render_transcript as draw

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.pdf"
        draw(path, prn=prn, name=name, cgpa=cgpa)
        return path.read_bytes()


def prns(rows) -> set[str]:
    return {row["prn"] for row in rows or []}


def walk_keys(node):
    """Every (key, value) pair in a parsed JSON document."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


# --- the beats --------------------------------------------------------------


def beat_0_server(r: Run) -> bool:
    r.header("0. Server and sign-in")
    status, data = r.get("/api/health")
    if not r.check("server answers /api/health with 200", status == 200, f"HTTP {status}"):
        return False
    return True


def beat_1_all_users(r: Run, admin: str) -> None:
    r.header("1. Officer: All users page and filters (endpoint added by another builder)")
    status, data = r.get("/api/auth/admin/users", admin)
    if status == 404:
        r.skip("1. /api/auth/admin/users lists students, admins and recruiters", "endpoint answers 404 (not merged yet)")
        r.skip("1. the list filters to one school", "endpoint answers 404")
        r.skip("1. /api/auth/admin/users/summary answers", "endpoint answers 404")
    else:
        # TODO(spec): tighten to the final response shape once it lands.
        rows = data.get("results") if isinstance(data, dict) else data
        r.check("1. /api/auth/admin/users lists users", status == 200 and bool(rows), f"HTTP {status}")
        ids = " ".join(json.dumps(row) for row in rows or [])
        r.check("1. the list shows PRN, ADM- and CMP- ids", AARAV in ids and "ADM-" in ids and "CMP-" in ids, "")
        status, filtered = r.get("/api/auth/admin/users?school=computing_data_science", admin)
        frows = filtered.get("results") if isinstance(filtered, dict) else filtered
        r.check("1. the list filters to one school", status == 200 and 0 < len(frows or []) <= len(rows), f"HTTP {status}")
        status, _ = r.get("/api/auth/admin/users/summary", admin)
        r.check("1. /api/auth/admin/users/summary answers 200", status == 200, f"HTTP {status}")
    status, _, _, _ = r.call("GET", "/api/auth/admin/users")
    if status != 404:
        r.check("1. all-users page refuses an anonymous caller", status in (401, 403), f"HTTP {status}")

    r.header("1b. Demo persona sign-in (endpoint added by another builder)")
    probe = r.call("GET", "/api/auth/demo/personas")[0]
    if probe == 404:
        r.skip("1b. persona sign-in under /api/auth/demo/ works", "endpoint answers 404 (not merged yet)")
    else:
        # TODO(spec): drive the persona buttons once the exact spec lands.
        r.check("1b. persona list is reachable", probe == 200, f"HTTP {probe}")


def beat_2_outcomes(r: Run, admin: str, company: str) -> None:
    r.header("2. Outcomes dashboard, batch filter, CSV export")
    status, everyone = r.get("/api/profiles/admin/outcomes", admin)
    ok = status == 200 and everyone["grand_total"] >= 276
    r.check("2. outcomes: every tracked student is counted (>= 276 seeded)", ok, f"HTTP {status}")
    if status != 200:
        return
    schools = {row["school"] for row in everyone["rows"]}
    r.check("2. outcomes: all eight schools have a row", len(schools - {"unassigned"}) == 8, f"{sorted(schools)}")
    r.check(
        "2. outcomes: each row's counts add up to its total",
        all(sum(row["counts"].values()) == row["total"] for row in everyone["rows"]),
        "",
    )
    r.check(
        "2. outcomes: per-school totals add up to the grand total",
        sum(row["total"] for row in everyone["rows"]) == everyone["grand_total"],
        "",
    )
    r.check(
        "2. outcomes: career-path totals add up to the grand total",
        sum(everyone["totals"].values()) == everyone["grand_total"],
        "",
    )
    s26, b26 = r.get("/api/profiles/admin/outcomes?batch=2026", admin)
    s27, b27 = r.get("/api/profiles/admin/outcomes?batch=2027", admin)
    r.check(
        "2. batch filter: 2026 and 2027 are narrower than everyone and add up to it",
        s26 == s27 == 200
        and 0 < b26["grand_total"] < everyone["grand_total"]
        and 0 < b27["grand_total"] < everyone["grand_total"]
        and b26["grand_total"] + b27["grand_total"] <= everyone["grand_total"],
        f"{s26}/{s27}",
    )
    r.check("2. batch filter: the answer records which batch it covers", s26 == 200 and b26["batch"] == 2026, "")
    status, _ = r.get("/api/profiles/admin/outcomes?batch=abc", admin)
    r.check("2. batch filter: a non-numeric batch is a 400", status == 400, f"HTTP {status}")

    status, _, raw, headers = r.call("GET", "/api/profiles/admin/outcomes/export?batch=2026", token=admin, accept="*/*")
    rows = list(csv.reader(io.StringIO(raw.decode()))) if status == 200 else []
    paths = [p["value"] for p in everyone["paths"]]
    r.check("2. CSV export: 200, text/csv, as an attachment",
            status == 200 and "text/csv" in headers.get("Content-Type", "") and "attachment" in headers.get("Content-Disposition", ""),
            f"HTTP {status}")
    r.check("2. CSV export: header row is school, one column per path, total", bool(rows) and rows[0] == ["school", *paths, "total"], f"{rows[:1]}")
    r.check(
        "2. CSV export: the last row's total matches the dashboard for that batch",
        bool(rows) and rows[-1][0] == "total" and int(rows[-1][-1]) == b26["grand_total"],
        f"{rows[-1:]}",
    )
    r.check("2. CSV export: one data row per school on the dashboard", len(rows) == len(b26["rows"]) + 2, f"{len(rows)} rows")
    status, _ = r.get("/api/profiles/admin/outcomes", company)
    r.check("2. outcomes: a recruiter is refused (403)", status == 403, f"HTTP {status}")
    status, _, _, _ = r.call("GET", "/api/profiles/admin/outcomes/export")
    r.check("2. CSV export: an anonymous caller is refused (401)", status == 401, f"HTTP {status}")


def beat_3_profiles(r: Run, admin: str, company: str) -> dict[str, str]:
    r.header("3. Officer: Profiles list with verification checks")
    rows = r.pages("/api/profiles/admin?search=2202009", admin)
    r.check("3. profiles list answers", rows is not None, "")
    rows = rows or []
    by_prn = {row["student"]["prn"]: row for row in rows}
    r.check("3. the four seeded students are listed", {AARAV, DIYA, ROHAN, SANA} <= set(by_prn), f"{sorted(by_prn)}")
    r.check(
        "3. every row carries verification_checks (a list) and a warning_count",
        bool(rows) and all(isinstance(row["verification_checks"], list) and isinstance(row["warning_count"], int) for row in rows),
        "",
    )
    flags = [flag for row in rows for flag in row["verification_checks"]]
    r.check(
        "3. each verification check says what it is about (code, severity, message)",
        all({"code", "severity", "message"} <= set(flag) or {"message"} <= set(flag) for flag in flags),
        f"{flags[:1]}",
    )
    r.check("3. verified state follows the seed (Aarav verified, Diya not)",
            by_prn.get(AARAV, {}).get("is_verified") is True and by_prn.get(DIYA, {}).get("is_verified") is False, "")
    r.check("3. the officer sees the hidden profile too", DIYA in by_prn and by_prn[DIYA]["visibility"] == "hidden", "")
    sids = {prn: row["student_id"] for prn, row in by_prn.items()}

    for name, query, want in (
        ("verified=true", "verified=true&search=2202009", {AARAV, SANA, ROHAN}),
        ("verified=false", "verified=false&search=2202009", {DIYA}),
    ):
        got = {row["student"]["prn"] for row in r.pages("/api/profiles/admin?" + query, admin) or []}
        r.check(f"3. filter {name} returns exactly the seeded students", got == want, f"{sorted(got)}")
    school_rows = r.pages("/api/profiles/admin?school=computing_data_science&search=2202009", admin) or []
    r.check("3. filter school=computing_data_science keeps the four seeded students",
            {AARAV, DIYA, ROHAN, SANA} <= {x["student"]["prn"] for x in school_rows}, "")
    other = r.pages("/api/profiles/admin?school=law&search=2202009", admin)
    r.check("3. filter school=law excludes them", other is not None and not ({AARAV, DIYA} & {x["student"]["prn"] for x in other}), "")
    status, _ = r.get("/api/profiles/admin", company)
    r.check("3. a recruiter cannot reach the officer's profiles list (403)", status == 403, f"HTTP {status}")
    return sids


def beat_4_student_detail(r: Run, admin: str, sids: dict[str, str], audit: AuditLog) -> None:
    r.header("4. Student detail: roster, transcript, self-reported CGPA; resume access log")
    status, detail = r.get(f"/api/profiles/admin/{sids[DIYA]}", admin)
    r.check("4. student detail answers for the officer", status == 200, f"HTTP {status}")
    if status != 200:
        return
    sources = detail.get("cgpa_sources", {})
    values = sources.get("values", {})
    r.check("4. detail carries the roster CGPA (9.10 for Diya)", abs((values.get("roster") or 0) - 9.10) < 0.001, f"{values}")
    r.check("4. detail carries the student's own CGPA (7.10 for Diya)", abs((values.get("student") or 0) - 7.10) < 0.001, f"{values}")
    r.check("4. detail lists the transcript slots (printed, recomputed) beside them",
            {"roster", "transcript_printed", "transcript_recomputed", "student"} <= set(values), f"{sorted(values)}")
    r.check("4. roster and self-reported CGPA disagree, and the detail says so",
            any(set(d["sources"]) == {"roster", "student"} for d in sources.get("disagreements", [])), f"{sources.get('disagreements')}")
    r.check("4. detail carries marksheet fields (class 10 and 12 marks)",
            detail.get("marks_10_percentage") is not None and detail.get("marks_12_percentage") is not None, "")
    r.check("4. detail names the roster's school and department",
            detail["student"].get("school") == "computing_data_science" and bool(detail["student"].get("department")), "")
    r.check("4. detail carries the resume facts the officer alone sees", "resume_facts_admin" in detail, "")

    # Resume download is audited.
    before = audit.count("document_accessed", AARAV)
    status, _, raw, headers = r.call("GET", f"/api/profiles/admin/{sids[AARAV]}/resume", token=admin, accept="*/*")
    r.check("4. the officer downloads Aarav's resume (a PDF)", status == 200 and raw[:5] == b"%PDF-", f"HTTP {status}")
    if before is None:
        r.skip("4. the download wrote a document_accessed row in the audit log", "audit DB not readable (pass --db)")
    else:
        after = audit.count("document_accessed", AARAV)
        r.check("4. the download wrote exactly one document_accessed row", after == before + 1, f"{before} -> {after}")
    before = audit.count("identity_accessed", AARAV)
    r.get(f"/api/profiles/admin/{sids[AARAV]}", admin)
    if before is None:
        r.skip("4. opening the detail wrote an identity_accessed row", "audit DB not readable (pass --db)")
    else:
        r.check("4. opening the detail wrote an identity_accessed row", audit.count("identity_accessed", AARAV) == before + 1, "")


def beat_5_transcript(r: Run, admin: str, sids: dict[str, str], audit: AuditLog, student_pw: str) -> None:
    r.header("5. Transcript: someone else's is refused, the student's own is accepted with a CGPA review")
    token = r.login(AARAV, student_pw)
    if not r.check("5. Aarav signs in with his PRN", token is not None, ""):
        return
    others = render_transcript(DIYA, "Diya Sharma", "8.50")
    before = audit.count("transcript_prn_mismatch", AARAV)
    status, data, _, _ = r.call("POST", "/api/profiles/me/transcript", token=token, files={"file": ("diya.pdf", others)})
    r.check("5. someone else's transcript is refused with 400 prn_mismatch",
            status == 400 and (data or {}).get("reason") == "prn_mismatch", f"HTTP {status} {data}")
    if before is not None:
        r.check("5. the refusal is audited as transcript_prn_mismatch", audit.count("transcript_prn_mismatch", AARAV) == before + 1, "")
    else:
        r.skip("5. the refusal is audited as transcript_prn_mismatch", "audit DB not readable (pass --db)")

    mine = render_transcript(AARAV, "Aarav Mehta", "8.50")  # roster says 8.72, so it is flagged
    status, data, _, _ = r.call("POST", "/api/profiles/me/transcript", token=token, files={"file": ("aarav.pdf", mine)})
    r.check("5. his own transcript is accepted (201)", status == 201, f"HTTP {status} {data}")
    if status != 201:
        return
    r.check("5. the transcript's PRN is his own", data["transcript_prn"] == AARAV, f"{data['transcript_prn']}")
    r.check("5. the printed CGPA was read (8.50) and does not match the roster (8.72)",
            float(data["parsed_cgpa"]) == 8.5 and data["cgpa_matches_roster"] is False, f"{data['parsed_cgpa']} {data['cgpa_matches_roster']}")
    r.check("5. a CGPA review is opened for the officer", data["cgpa_review_status"] == "open", f"{data['cgpa_review_status']}")
    r.check("5. the roster CGPA is untouched by the upload", data["student"]["cgpa"] == "8.72", f"{data['student']['cgpa']}")

    status, detail = r.get(f"/api/profiles/admin/{sids[AARAV]}", admin)
    sources = detail.get("cgpa_sources", {}) if status == 200 else {}
    r.check("5. the officer's detail now shows the transcript beside the roster CGPA",
            status == 200 and detail["cgpa_review_status"] == "open" and sources["values"]["transcript_printed"] == 8.5
            and any(set(d["sources"]) == {"roster", "transcript_printed"} for d in sources["disagreements"]), "")
    before = audit.count("document_accessed", AARAV)
    status, _, raw, _ = r.call("GET", f"/api/profiles/admin/{sids[AARAV]}/transcript", token=admin, accept="*/*")
    r.check("5. the officer opens the transcript (a PDF)", status == 200 and raw[:5] == b"%PDF-", f"HTTP {status}")
    if before is not None:
        r.check("5. opening the transcript is audited too", audit.count("document_accessed", AARAV) == before + 1, "")
    status, _ = r.get(f"/api/profiles/admin/{sids[AARAV]}/transcript")
    r.check("5. an anonymous caller cannot open it (401)", status == 401, f"HTTP {status}")


def beat_6_recruiter(r: Run, acme: str, nimbus: str, sids: dict[str, str], live_ai: bool) -> None:
    r.header("6. Recruiter (Acme): JD search, ranking, score breakdown, role category")
    status, data, _, _ = r.call("POST", "/api/matching/search", token=acme, body={"jd_text": JD, "k": 10})
    r.check("6. Acme's JD search answers 200", status == 200, f"HTTP {status} {data}")
    if status != 200:
        return
    results = data["results"]
    found = prns(results)
    r.check("6. Acme sees Aarav, Sana and Rohan (shortlisted by Acme) and never Diya (hidden)",
            {AARAV, SANA, ROHAN} <= found and DIYA not in found, f"{sorted(found)}")
    scores = [row["match"]["score"] for row in results]
    r.check("6. results are ranked best first", scores == sorted(scores, reverse=True), f"{scores}")
    r.check("6. every score is a whole number from 0 to 100",
            all(isinstance(s, int) and 0 <= s <= 100 for s in scores), f"{scores}")
    r.check("6. every result carries the match breakdown (components with score and weight)",
            all(BREAKDOWN_KEYS <= set(row["match"]["components"]) and
                all({"score", "weight"} <= set(c) for c in row["match"]["components"].values()) for row in results), "")
    r.check("6. the backend-skills student outranks the data-analyst for a backend JD",
            [x for x in (row["prn"] for row in results) if x in (AARAV, SANA)][0] == AARAV, "")
    r.check("6. the JD reading lists the skills it asked for (Python, Django)",
            {"Python", "Django"} <= set(data["job"]["required_skills"]), f"{data['job']['required_skills']}")
    r.check("6. results hide what companies must not see (no age, DOB, resume CGPA or verification flags)",
            not any(k in row for row in results for k in ("verification_checks", "date_of_birth", "age", "parsed_cgpa")), "")
    status, score_data, _, _ = r.call("POST", "/api/matching/score", token=acme, body={"jd_text": JD, "student_ids": [sids[AARAV], sids[DIYA]]})
    r.check("6. scoring named students silently leaves out the hidden one",
            status == 200 and prns(score_data["results"]) == {AARAV}, f"HTTP {status}")
    status, _, _, _ = r.call("POST", "/api/matching/search", token=acme, body={"jd_text": "too short"})
    r.check("6. a too-short JD is a 400", status == 400, f"HTTP {status}")

    status, cats = r.get("/api/matching/categories", acme)
    names = {c["name"] for c in (cats or {}).get("results", [])}
    r.check("6. role categories exist (seed_demo made Backend Engineer)", status == 200 and "Backend Engineer" in names, f"{sorted(names)}")
    r.check("6. a category row shows its JD count and top skills",
            status == 200 and all({"name", "jd_count", "top_skills"} <= set(c) for c in cats["results"]), "")
    if live_ai:
        r.check("6. [live-ai] the model read the JD (canonical role, not the text fallback)",
                data["job"]["canonical_role"] and data["job"]["source"] != "text", f"{data['job']}")
        r.check("6. [live-ai] the vector index answered (no fallback)", data["fallback"] is False, f"fallback={data['fallback']}")
        status, cats2 = r.get("/api/matching/categories", acme)
        r.check("6. [live-ai] the role category exists after the search",
                status == 200 and data["job"]["canonical_role"] in {c["name"] for c in cats2["results"]}, "")
    else:
        r.skip("6. [live-ai] the model reads the JD and a role category is created", "run with --live-ai (needs Gemma and embeddings)")


def beat_7_nimbus(r: Run, acme: str, nimbus: str, sids: dict[str, str], audit: AuditLog) -> None:
    r.header("7. Recruiter (Nimbus): hidden and shortlisted-only students stay out of sight")
    status, data, _, _ = r.call("POST", "/api/matching/search", token=nimbus, body={"jd_text": JD, "k": 10})
    found = prns((data or {}).get("results"))
    r.check("7. Nimbus's JD search answers 200", status == 200, f"HTTP {status}")
    r.check("7. Nimbus sees the two public students", {AARAV, SANA} <= found, f"{sorted(found)}")
    r.check("7. Nimbus does not see the hidden student", DIYA not in found, "")
    r.check("7. Nimbus does not see the one only Acme shortlisted", ROHAN not in found, "")
    listed = prns(r.pages("/api/profiles/students?search=2202009", nimbus))
    r.check("7. the browse list agrees: exactly Aarav and Sana", listed == {AARAV, SANA}, f"{sorted(listed)}")
    for label, prn, want_nimbus, want_acme in (
        ("hidden Diya", DIYA, 404, 404),
        ("shortlisted-only Rohan", ROHAN, 404, 200),
        ("public Aarav", AARAV, 200, 200),
    ):
        got = (r.get(f"/api/profiles/students/{sids[prn]}", nimbus)[0], r.get(f"/api/profiles/students/{sids[prn]}", acme)[0])
        r.check(f"7. direct open of {label}: Nimbus {want_nimbus}, Acme {want_acme}", got == (want_nimbus, want_acme), f"{got}")
    status, _, _, _ = r.call("GET", f"/api/profiles/students/{sids[ROHAN]}/resume", token=nimbus, accept="*/*")
    r.check("7. Rohan's resume is a 404 for Nimbus, not a 403", status == 404, f"HTTP {status}")
    status, _, _, _ = r.call("GET", f"/api/profiles/students/{sids[AARAV]}/transcript", token=acme, accept="*/*")
    r.check("7. no recruiter can open a transcript (404)", status == 404, f"HTTP {status}")
    status, scored, _, _ = r.call("POST", "/api/matching/score", token=nimbus, body={"jd_text": JD, "student_ids": [sids[ROHAN], sids[DIYA]]})
    r.check("7. scoring named students cannot be used to probe for hidden ones", status == 200 and scored["count"] == 0, f"HTTP {status}")


def beat_8_no_5xx(r: Run) -> None:
    r.header("8. Whole run")
    five_xx = [s for s in r.statuses if s >= 500]
    r.check("no 5xx response anywhere in the run", not five_xx, f"{len(five_xx)} server errors")


# --- public mode (E3) -------------------------------------------------------


def run_public(r: Run, args) -> None:
    r.header("P. Public-link rules (server running with DEBUG off)")
    status, data = r.get("/api/health")
    r.check("P. the server answers /api/health with 200", status == 200, f"HTTP {status}")
    r.check("P. /api/health reports debug=false", (data or {}).get("debug") is False, f"{(data or {}).get('debug')}")

    for path in ("/this/page/does/not/exist", "/api/no-such-endpoint", "/django-admin/no/such"):
        status, _, raw, _ = r.call("GET", path, accept="text/html")
        text = raw.decode(errors="replace")
        r.check(f"P. a bad URL ({path}) is a plain 404 with no debug page",
                status == 404 and not any(m in text for m in PUBLIC_DEBUG_MARKERS), f"HTTP {status}")
    # A request that makes the server raise must not leak a traceback either.
    status, _, raw, _ = r.call("POST", "/api/auth/login", body=None, accept="text/html")
    text = raw.decode(errors="replace")
    r.check("P. a malformed login request leaks no traceback", status < 500 and "Traceback" not in text, f"HTTP {status}")

    for path in ("/media/", "/media/resumes/anything.pdf", "/media/transcripts/220200901/t.pdf"):
        status, _, _, _ = r.call("GET", path, accept="*/*")
        r.check(f"P. {path} is a 404 (documents leave only through audited API views)", status == 404, f"HTTP {status}")

    for path in ("/api/auth/demo/personas", "/api/auth/demo/login", "/api/auth/demo/signin"):
        for method in ("GET", "POST"):
            status, _, _, _ = r.call(method, path, body={} if method == "POST" else None)
            r.check(f"P. demo sign-in {method} {path} is a 404", status == 404, f"HTTP {status}")

    # Provoke every place a code could be echoed, then scan every body seen.
    r.call("POST", "/api/auth/otp/request", body={"identifier": args.admin_email})
    r.call("POST", "/api/auth/signup", body={"prn": "220200999", "email": "nobody@college.edu"})
    r.call("POST", "/api/auth/signup", body={"prn": "220200905", "email": "roster.only@college.edu"})
    admin = r.login(args.admin_email, args.admin_password)
    if admin:
        r.get("/api/auth/me", admin)
    leaked = []
    for path, status, raw in r.bodies:
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        for key, value in walk_keys(parsed):
            if key.lower() in OTP_KEYS and value not in (None, "", False):
                leaked.append(f"{path}:{key}")
    r.check("P. no OTP or sign-in code in any response body", not leaked, f"{leaked[:3]}")
    beat_8_no_5xx(r)


# --- main -------------------------------------------------------------------


def run_demo(r: Run, args) -> None:
    audit = AuditLog.from_args(args.db)
    if not beat_0_server(r):
        print("Is the server up at", args.base_url, "?")
        return
    admin = r.login(args.admin_email, args.admin_password)
    acme = r.login(args.company_a_email, args.company_a_password)
    nimbus = r.login(args.company_b_email, args.company_b_password)
    if not r.check("the officer, Acme and Nimbus can sign in (run seed_demo first)", all((admin, acme, nimbus)), ""):
        return

    beat_1_all_users(r, admin)
    beat_2_outcomes(r, admin, acme)
    sids = beat_3_profiles(r, admin, acme)
    if not {AARAV, DIYA, ROHAN, SANA} <= set(sids):
        print("Run `manage.py seed_demo --with-students` first; stopping.")
        return
    beat_4_student_detail(r, admin, sids, audit)
    beat_5_transcript(r, admin, sids, audit, args.student_password)
    beat_6_recruiter(r, acme, nimbus, sids, args.live_ai)
    beat_7_nimbus(r, acme, nimbus, sids, audit)
    beat_8_no_5xx(r)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--public", action="store_true", help="assert the public-link rules against a DEBUG-off server")
    p.add_argument("--live-ai", action="store_true", default=os.environ.get("E2E_LIVE_AI") == "1",
                   help="also assert what needs Gemma and embeddings (env: E2E_LIVE_AI=1)")
    p.add_argument("--db", help="SQLite file to read the audit log from (default: from DATABASE_URL)")
    p.add_argument("--admin-email", default="placement.officer@college.edu")
    p.add_argument("--admin-password", default="AdminPass!234")
    p.add_argument("--company-a-email", default="recruiter@acmetech.example")
    p.add_argument("--company-a-password", default="CompanyPass!234")
    p.add_argument("--company-b-email", default="talent@nimbusanalytics.example")
    p.add_argument("--company-b-password", default="CompanyPass!234")
    p.add_argument("--student-password", default="StudentPass!234")
    args = p.parse_args()

    r = Run(args.base_url)
    print(f"e2e_demo: {'public' if args.public else 'demo'} mode" + (", live-ai" if args.live_ai and not args.public else ""))
    (run_public if args.public else run_demo)(r, args)

    passed = sum(1 for v, _ in r.results if v == "PASS")
    skipped = sum(1 for v, _ in r.results if v == "SKIP")
    failed = sum(1 for v, _ in r.results if v == "FAIL")
    total = passed + failed
    print(f"\n{passed}/{total} checks passed" + (f", {skipped} skipped" if skipped else ""))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
