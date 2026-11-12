#!/usr/bin/env python
"""
Halfway checkpoint E2E (agents.md, after Phase 3), re-runnable against a live server.

The original run's script was never committed, only its output (SMOKE_TESTS.md,
30 checks / 196 requests). This rebuilds it against today's API: profiles are
addressed by student UUID, tokens carry `roles[]`, companies are an entity.

    cd backend
    ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py seed_demo
    OTP_THROTTLE_RATE=1000/hour ../.venv/bin/python manage.py runserver 127.0.0.1:8765
    ../.venv/bin/python checkpoints/e2e_phase_0_3.py --base-url http://127.0.0.1:8765

Needs: the server in DEBUG (or EXPOSE_OTP_IN_RESPONSE=1) so the signup code
comes back in the response, and an OTP throttle above the default 10/hour,
because this run makes ~25 signup/verify calls from one address. Standard
library only. Exits 1 if any check fails.

Why it creates its own students: the check is "a fresh roster of 10+ students
goes through the whole lifecycle", so it must not lean on whatever the demo
seed happens to contain. It uses synthetic PRNs 220200960..989 only. Each run
burns 13 of those (10 students + 3 for the rejection cases), so `--block 0`
and `--block 1` give two runs against the same database; a fresh database
can use block 0 every time.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

RESUME_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "resumes"
PASSWORD = "E2e-Pass!2026x"
DEPARTMENTS = [
    "B.Tech Computer Science",
    "B.Tech Data Science",
    "B.Tech Artificial Intelligence",
    "BBA (Hons.)",
]


class Run:
    """Collects every request's status and timing, and every check's verdict."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.statuses: list[int] = []
        self.timings: dict[str, list[float]] = {}
        self.checks: list[tuple[str, bool, str]] = []

    # --- HTTP -------------------------------------------------------------

    def call(self, method, path, *, token=None, body=None, files=None, op="other"):
        """Returns (status, parsed JSON or None). Never raises on HTTP errors."""
        headers = {"Accept": "application/json"}
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
        url = path if path.startswith("http") else self.base + path
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        self.timings.setdefault(op, []).append((time.perf_counter() - started) * 1000)
        self.statuses.append(status)
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, None

    def pages(self, path, *, token, op="other"):
        """Every row of a paginated list, following `next`."""
        rows, url = [], path
        while url:
            status, data = self.call("GET", url, token=token, op=op)
            if status != 200:
                return None
            rows += data["results"]
            url = data.get("next")
        return rows

    # --- verdicts ---------------------------------------------------------

    def check(self, name: str, ok: bool, reason: str = "") -> bool:
        self.checks.append((name, bool(ok), reason))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" - {reason}" if reason else ""), flush=True)
        return bool(ok)


def _multipart(boundary: str, files: dict) -> bytes:
    """`files` maps field name -> (filename, bytes) or plain str value."""
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


def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


# --- the synthetic cohort ---------------------------------------------------


class Cohort:
    def __init__(self, block: int):
        base = 960 + 15 * block
        self.students = []
        for i in range(10):
            self.students.append(
                {
                    "i": i,
                    "prn": f"220200{base + i}",
                    "email": f"e2e.student{base + i}@college.edu",
                    "name": f"E2E Student {base + i}",
                    "department": DEPARTMENTS[i % 4],
                    "cgpa": f"{6.5 + 0.3 * i:.2f}",
                    # Python for most, Django for three of those: lets the
                    # skills filter prove "python AND django" is narrower.
                    "skills": ["Python", "Git"] * (i in {0, 1, 2, 3, 5, 7, 8})
                    + ["Django"] * (i in {0, 1, 5})
                    + ["Excel"] * (i in {4, 6, 9}),
                    "chatbot": i in {1, 4, 8},
                }
            )
        self.ineligible = {
            "prn": f"220200{base + 10}", "email": f"e2e.student{base + 10}@college.edu",
            "name": f"E2E Student {base + 10}", "department": DEPARTMENTS[0], "cgpa": "7.00",
        }
        self.mismatch_target = {
            "prn": f"220200{base + 11}", "email": f"e2e.student{base + 11}@college.edu",
            "name": f"E2E Student {base + 11}", "department": DEPARTMENTS[0], "cgpa": "7.50",
        }
        # Never uploaded: the "PRN not on the roster" case.
        self.ghost = {"prn": f"220200{base + 12}", "email": f"e2e.ghost{base + 12}@college.edu"}

    def roster_csv(self) -> bytes:
        lines = ["prn,email,full_name,department,school,year_of_study,batch,cgpa,phone,is_placement_eligible"]
        for s in self.students + [self.mismatch_target]:
            lines.append(f"{s['prn']},{s['email']},{s['name']},{s['department']},,4,2026,{s['cgpa']},,true")
        e = self.ineligible
        lines.append(f"{e['prn']},{e['email']},{e['name']},{e['department']},,4,2026,{e['cgpa']},,false")
        return ("\n".join(lines) + "\n").encode()

    # Visibility spread, same shape as the original run (4 / 3 / 3). Each case
    # exists to prove a different clause of the visibility rule:
    #   all         every company sees it
    #   shortlisted only the company that shortlisted it while public sees it
    #   hidden      nobody but the student and admin sees it
    @property
    def public(self): return self.students[0:4]
    @property
    def shortlisted_only(self): return self.students[4:7]
    @property
    def hidden(self): return self.students[7:10]
    @property
    def verified_idx(self): return {0, 2, 4, 6, 8}


# --- the checkpoint ----------------------------------------------------------


def run(args) -> int:
    r = Run(args.base_url)
    cohort = Cohort(args.block)
    mine = {s["prn"] for s in cohort.students}

    status, _ = r.call("GET", "/api/health")
    if not r.check("0. server answers /api/health with 200", status == 200, f"HTTP {status}"):
        print("Is the server up at", args.base_url, "?")
        return 1

    # ---- 1. fresh roster ---------------------------------------------------
    status, data = r.call("POST", "/api/auth/login", body={"identifier": args.admin_email, "password": args.admin_password}, op="login")
    admin = data["tokens"]["access"] if status == 200 else None
    r.check("1. seeded admin can log in", admin is not None, f"HTTP {status}")
    if admin is None:
        print("Run `manage.py seed_demo` first, or pass --admin-email/--admin-password.")
        return 1
    roles = data["user"]["roles"]
    r.check("1. admin token carries roles[] containing 'placement_admin'", "placement_admin" in roles, f"roles={roles}")

    status, data = r.call(
        "POST", "/api/roster/upload", token=admin,
        files={"file": ("e2e_roster.csv", cohort.roster_csv())},
    )
    r.check(
        "1. roster CSV of 12 synthetic rows uploaded with no rejected rows",
        status == 200 and data and data["processed"] == 12 and data["error_count"] == 0,
        f"HTTP {status} {({k: data[k] for k in ('created', 'updated', 'unchanged', 'error_count')} if data else '')}",
    )
    status, data = r.call("GET", "/api/roster/students?prns=" + ",".join(mine), token=admin)
    r.check("1. 10 placement-eligible students are on the roster", status == 200 and data["count"] == 10, f"count={data and data.get('count')}")

    # ---- 2. signup -> verify -> login; two invalid pairs -------------------
    tokens: dict[str, str] = {}
    sid: dict[str, str] = {}
    failures = []
    for s in cohort.students:
        status, data = r.call("POST", "/api/auth/signup", body={"prn": s["prn"], "email": s["email"]}, op="signup")
        otp = (data or {}).get("debug_otp")
        if status != 201 or not otp:
            failures.append(f"{s['prn']} signup HTTP {status}" + (" (no debug_otp: enable DEBUG)" if status == 201 else ""))
            if status == 429:
                failures[-1] += " (throttled: start the server with OTP_THROTTLE_RATE=1000/hour)"
            continue
        status, data = r.call("POST", "/api/auth/verify", body={"identifier": s["prn"], "code": otp, "password": PASSWORD}, op="verify")
        if status != 200:
            failures.append(f"{s['prn']} verify HTTP {status}")
            continue
        status, data = r.call("POST", "/api/auth/login", body={"identifier": s["prn"], "password": PASSWORD}, op="login")
        if status != 200:
            failures.append(f"{s['prn']} login HTTP {status}")
            continue
        tokens[s["prn"]] = data["tokens"]["access"]
        s["roles"] = data["user"]["roles"]
    r.check("2. all 10 students sign up, verify and log in", not failures, "; ".join(failures) or "10/10")
    r.check("2. student tokens carry roles == ['student']", all(s.get("roles") == ["student"] for s in cohort.students), "")

    ghost, mismatch = cohort.ghost, cohort.mismatch_target
    s1, d1 = r.call("POST", "/api/auth/signup", body={"prn": ghost["prn"], "email": ghost["email"]}, op="signup")
    s2, d2 = r.call("POST", "/api/auth/signup", body={"prn": mismatch["prn"], "email": "impostor." + mismatch["email"]}, op="signup")
    r.check("2. PRN not on the roster is rejected", s1 == 403 and d1.get("reason") == "no_such_prn", f"HTTP {s1} {d1 and d1.get('reason')}")
    r.check("2. roster PRN with someone else's email is rejected", s2 == 403 and d2.get("reason") == "email_mismatch", f"HTTP {s2} {d2 and d2.get('reason')}")
    s3, d3 = r.call("POST", "/api/auth/signup", body={"prn": cohort.ineligible["prn"], "email": cohort.ineligible["email"]}, op="signup")
    r.check("2. a roster row marked not placement-eligible cannot sign up", s3 == 403 and d3.get("reason") == "not_eligible", f"HTTP {s3} {d3 and d3.get('reason')}")

    flagged = r.pages("/api/roster/flagged?search=e2e", token=admin) or []
    flagged_pairs = {(f["prn"], f["reason"]) for f in flagged}
    r.check(
        "2. both rejected pairs appear in the admin's flagged queue",
        {(ghost["prn"], "no_such_prn"), (mismatch["prn"], "email_mismatch")} <= flagged_pairs,
        f"{len(flagged)} flagged row(s) matching 'e2e'",
    )
    s4, _ = r.call("POST", "/api/auth/login", body={"identifier": ghost["prn"], "password": PASSWORD}, op="login")
    s5, _ = r.call("POST", "/api/auth/login", body={"identifier": mismatch["prn"], "password": PASSWORD}, op="login")
    r.check("2. rejected pairs never produce a working login", s4 == 401 and s5 in (401, 403), f"HTTP {s4} / {s5}")

    if failures:
        print("Cannot build profiles without logged-in students; stopping.")
        return finish(r)

    # ---- 3. profiles: experience, projects, skills, resume -----------------
    reference = json.loads((RESUME_DIR / "reference.json").read_text())
    resume_names = list(reference)
    build_problems, extraction_rows = [], []
    for s in cohort.students:
        t = tokens[s["prn"]]
        i = s["i"]
        st, me = r.call("GET", "/api/profiles/me", token=t, op="profile_read")
        sid[s["prn"]] = me["student_id"] if st == 200 else None
        calls = [
            ("PATCH", "/api/profiles/me", {"headline": f"E2E headline {i}", "summary": "Synthetic profile for the halfway checkpoint."}),
            ("POST", "/api/profiles/me/experience", {"role": "Intern", "organization": f"Acme {i}", "kind": "internship", "start_date": "2025-05-01", "end_date": "2025-08-01", "skills_used": ["Python"]}),
            ("POST", "/api/profiles/me/experience", {"role": "Part-time developer", "organization": f"Globex {i}", "kind": "part_time", "start_date": "2025-09-01"}),
            ("POST", "/api/profiles/me/projects", {"title": "Smart e2echatbot assistant" if s["chatbot"] else "Inventory manager", "description": "Built for the checkpoint.", "tech_stack": ["Python"], "repo_url": "https://example.com/repo"}),
            ("POST", "/api/profiles/me/projects", {"title": f"Side project {i}", "description": "Second project.", "tech_stack": ["Git"]}),
        ] + [("POST", "/api/profiles/me/skills", {"name": name}) for name in s["skills"]]
        for method, path, body in calls:
            st, _ = r.call(method, path, token=t, body=body, op="profile_write")
            if st not in (200, 201):
                build_problems.append(f"{s['prn']} {method} {path} HTTP {st}")

        name = resume_names[i % len(resume_names)]
        path = RESUME_DIR / name
        if not path.exists():
            build_problems.append(f"missing {path} (run `manage.py make_sample_resumes`)")
            continue
        st, data = r.call("POST", "/api/profiles/me/resume", token=t, files={"file": (name, path.read_bytes())}, op="resume_upload")
        if st != 201:
            build_problems.append(f"{s['prn']} resume HTTP {st}")
            continue
        if i < 5:  # the spot-check set: first five students, one reference resume each
            profile = data["profile"]
            want = reference[name]
            got_years = float(profile["parsed_experience_years"])
            got_levels = set(profile["parsed_education_levels"])
            prefilled = float(profile["experience_years"])
            ok = got_years == want["experience_years"] and got_levels == set(want["education_levels"]) and prefilled == got_years
            extraction_rows.append((s["prn"], name, got_years, want["experience_years"], sorted(got_levels), want["education_levels"], ok))

    r.check("3. every student built a full profile (details, experience, projects, skills, resume)", not build_problems, "; ".join(build_problems[:3]) or "10/10")
    for prn, name, gy, wy, gl, wl, ok in extraction_rows:
        print(f"      {prn}  {name:<34} exp {gy} (want {wy})  edu {gl} (want {wl})  {'ok' if ok else 'MISMATCH'}")
    r.check(
        "3. resume-derived experience and education match the hand-checked reference for 5 students",
        len(extraction_rows) == 5 and all(row[-1] for row in extraction_rows),
        f"{sum(row[-1] for row in extraction_rows)}/5 match, and the profile was pre-filled with the parsed years",
    )

    verified_ok = True
    for i in sorted(cohort.verified_idx):
        s = cohort.students[i]
        st, data = r.call("POST", f"/api/profiles/admin/{sid[s['prn']]}/verification", token=admin, body={"is_verified": True})
        verified_ok &= st == 200 and data["is_verified"] is True
    r.check("3. admin verifies half the profiles (5 of 10)", verified_ok, "")

    # ---- 4. companies, visibility, filters ---------------------------------
    companies = {}
    for key, (email, password) in {"A": (args.company_a_email, args.company_a_password), "B": (args.company_b_email, args.company_b_password)}.items():
        st, data = r.call("POST", "/api/auth/login", body={"identifier": email, "password": password}, op="login")
        companies[key] = data["tokens"]["access"] if st == 200 else None
    r.check("4. both seeded company accounts log in", all(companies.values()), "")
    if not all(companies.values()):
        return finish(r)
    ca, cb = companies["A"], companies["B"]

    # Everyone starts public so company A is allowed to shortlist them; it can
    # only shortlist what it can see, and that is the point of the third case.
    for s in cohort.students:
        r.call("PUT", "/api/profiles/me/visibility", token=tokens[s["prn"]], body={"visibility": "all"})
    short_status = [r.call("POST", f"/api/profiles/students/{sid[s['prn']]}/shortlist", token=ca, body={"note": "e2e"})[0] for s in cohort.shortlisted_only]
    r.check("4. company A shortlists three students while they are public", short_status == [201, 201, 201], f"HTTP {short_status}")

    for group, setting in ((cohort.public, "all"), (cohort.shortlisted_only, "shortlisted"), (cohort.hidden, "hidden")):
        for s in group:
            st, _ = r.call("PUT", "/api/profiles/me/visibility", token=tokens[s["prn"]], body={"visibility": setting})
            assert st == 200, f"visibility PUT HTTP {st}"

    def visible(token):
        rows = r.pages("/api/profiles/students", token=token, op="search")
        return {row["prn"] for row in rows or []} & mine

    want_a = {s["prn"] for s in cohort.public + cohort.shortlisted_only}
    want_b = {s["prn"] for s in cohort.public}
    seen_a, seen_b = visible(ca), visible(cb)
    r.check("4. company A sees all-companies plus the profiles it shortlisted", seen_a == want_a, f"sees {len(seen_a)}, expected {len(want_a)}")
    r.check("4. company B (shortlisted nobody) sees only all-companies profiles", seen_b == want_b, f"sees {len(seen_b)}, expected {len(want_b)}")
    r.check("4. no hidden profile is visible to either company", not ({s["prn"] for s in cohort.hidden} & (seen_a | seen_b)), "")

    hidden_sid = sid[cohort.hidden[0]["prn"]]
    st_a, _ = r.call("GET", f"/api/profiles/students/{hidden_sid}", token=ca)
    r.check("4. a hidden profile cannot be fetched directly (404, not 403)", st_a == 404, f"HTTP {st_a}")
    one_short = sid[cohort.shortlisted_only[0]["prn"]]
    st_b, _ = r.call("GET", f"/api/profiles/students/{one_short}", token=cb)
    r.check("4. one company's shortlist does not expose the profile to another", st_b == 404, f"HTTP {st_b}")
    st_b2, _ = r.call("POST", f"/api/profiles/students/{one_short}/shortlist", token=cb, body={})
    r.check("4. a company cannot shortlist its way into a profile it cannot see", st_b2 == 404, f"HTTP {st_b2}")
    st_ad, rows = r.call("GET", "/api/profiles/admin?search=E2E", token=admin)
    r.check("4. admin still sees all 10 regardless of visibility", st_ad == 200 and rows["count"] >= 10, f"count={rows and rows.get('count')}")

    # A few free-text searches, mainly so the search timing has a sample.
    searches_ok = all(
        r.call("GET", "/api/profiles/students?search=" + term, token=ca, op="search")[0] == 200
        for term in ("python", "intern", "e2echatbot", "inventory", "E2E")
    )
    r.check("4. free-text search answers 200 for company A", searches_ok, "5 queries")

    # Filters (company A). The expected set is worked out from the cohort we
    # built, not just "is a subset of what A can see", so a filter that
    # silently ignores its parameter fails.
    A = [s for s in cohort.students if s["prn"] in want_a]

    def filtered(query):
        rows = r.pages("/api/profiles/students?" + query, token=ca, op="filter")
        return None if rows is None else {row["prn"] for row in rows} & mine

    dept = DEPARTMENTS[0]
    cases = [
        ("department", "department=" + urllib.parse.quote(dept), {s["prn"] for s in A if s["department"] == dept}),
        ("skill python", "skills=python", {s["prn"] for s in A if "Python" in s["skills"]}),
        ("skills python+django", "skills=python,django", {s["prn"] for s in A if "Django" in s["skills"]}),
        ("cgpa 8.0-9.2", "cgpa_min=8&cgpa_max=9.2", {s["prn"] for s in A if 8.0 <= float(s["cgpa"]) <= 9.2}),
        ("project keyword", "project_keyword=e2echatbot", {s["prn"] for s in A if s["chatbot"]}),
        ("verified only", "verified=true", {s["prn"] for s in A if s["i"] in cohort.verified_idx}),
    ]
    for label, query, expected in cases:
        got = filtered(query)
        r.check(f"4. filter by {label} returns exactly the expected visible profiles", got == expected, f"got {None if got is None else len(got)}, expected {len(expected)}")

    # ---- 5. edit and delete, success and failure ---------------------------
    s0, s1_ = cohort.students[0], cohort.students[1]
    t0, t1 = tokens[s0["prn"]], tokens[s1_["prn"]]
    entries = r.pages("/api/profiles/me/experience", token=t0) or []
    entry = entries[0]["id"] if entries else None
    st, _ = r.call("PATCH", f"/api/profiles/me/experience/{entry}", token=t0, body={"role": "Senior intern"}, op="profile_write")
    r.check("5. a student edits their own experience entry", st == 200, f"HTTP {st}")
    st, _ = r.call("PATCH", f"/api/profiles/me/experience/{entry}", token=t1, body={"role": "Hijacked"})
    r.check("5. another student editing that entry is refused (404)", st == 404, f"HTTP {st}")
    st, _ = r.call("DELETE", f"/api/profiles/me/experience/{entry}", token=t1)
    r.check("5. another student deleting that entry is refused (404)", st == 404, f"HTTP {st}")
    after = {e["id"]: e for e in r.pages("/api/profiles/me/experience", token=t0) or []}
    r.check("5. the entry survived both hostile attempts, unchanged", entry in after and after[entry]["role"] == "Senior intern", "")
    projects = r.pages("/api/profiles/me/projects", token=t0) or []
    st, _ = r.call("DELETE", f"/api/profiles/me/projects/{projects[0]['id']}", token=t0)
    r.check("5. a student deletes their own project", st == 204, f"HTTP {st}")
    st, _ = r.call("POST", "/api/profiles/me/experience", token=t0, body={"role": "X", "organization": "Y", "start_date": "2025-09-01", "end_date": "2025-01-01"})
    r.check("5. an invalid entry (ends before it starts) is refused with 400", st == 400, f"HTTP {st}")
    st, _ = r.call("POST", f"/api/profiles/admin/{sid[s0['prn']]}/verification", token=t0, body={"is_verified": True})
    r.check("5. a student cannot verify their own profile (403)", st == 403, f"HTTP {st}")
    st, _ = r.call("GET", "/api/profiles/admin", token=ca)
    r.check("5. a company cannot reach the admin profile list (403)", st == 403, f"HTTP {st}")
    st, _ = r.call("GET", "/api/profiles/students")
    r.check("5. an unauthenticated request to a protected endpoint is refused (401)", st == 401, f"HTTP {st}")

    return finish(r)


def finish(r: Run) -> int:
    # ---- 6. timings and server errors --------------------------------------
    print("\n  operation            n    median      p95       max")
    for op, values in sorted(r.timings.items()):
        print(f"  {op:<16} {len(values):>4} {statistics.median(values):>8.1f}ms {pct(values, .95):>8.1f}ms {max(values):>8.1f}ms")
    print()
    for op in ("search", "filter"):
        values = r.timings.get(op)
        if values:
            median = statistics.median(values)
            r.check(f"6. {op} responds in under 500 ms", median < 500, f"median {median:.0f} ms over {len(values)} calls, p95 {pct(values, .95):.0f} ms")
    five_xx = [s for s in r.statuses if s >= 500]
    r.check("6. no 5xx response in the whole run", not five_xx, f"{len(r.statuses)} requests, {len(five_xx)} server errors")

    passed = sum(1 for _, ok, _ in r.checks if ok)
    print(f"\n{passed}/{len(r.checks)} checks passed")
    return 0 if passed == len(r.checks) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--block", type=int, choices=(0, 1), default=0, help="which PRN block (960-974 or 975-989) to use")
    p.add_argument("--admin-email", default="placement.officer@college.edu")
    p.add_argument("--admin-password", default="AdminPass!234")
    p.add_argument("--company-a-email", default="recruiter@acmetech.example")
    p.add_argument("--company-a-password", default="CompanyPass!234")
    p.add_argument("--company-b-email", default="talent@nimbusanalytics.example")
    p.add_argument("--company-b-password", default="CompanyPass!234")
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
