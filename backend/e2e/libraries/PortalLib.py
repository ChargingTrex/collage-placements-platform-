"""
Python keyword library for the Robot suites: the things that are awkward in
Robot syntax. Assertions stay in the .robot files; this only fetches, builds
and decodes.

Everything that touches the server's state (manage.py, the audit table) reads
the SAME environment the server was started with: run.py launches Robot with
the server's environment, so DATABASE_URL, MEDIA_ROOT and the rest match.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from robot.api import logger
from robot.api.deco import keyword, library

BACKEND = Path(__file__).resolve().parent.parent.parent
PRN_PREFIX = "220200"
FIRST_SEQ, LAST_SEQ = 800, 899  # this suite's PRN range; see E2E_SUITE_PLAN.md

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _sqlite_path() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("sqlite:///"):
        raise AssertionError(f"DATABASE_URL is not a sqlite file: {url!r}")
    return url[len("sqlite:///"):]


@library(scope="GLOBAL", auto_keywords=False)
class PortalLib:
    # --- setup done through manage.py (always labelled) ---------------------

    @keyword
    def setup_via_manage_py(self, label: str, *args: str) -> str:
        """Run `manage.py <args>` with the server's environment. Labelled SETUP."""
        python = os.environ.get("E2E_PYTHON", sys.executable)
        logger.console(f"\n    SETUP (manage.py {' '.join(args)[:50]}): {label}")
        done = subprocess.run(
            [python, "manage.py", *args], cwd=BACKEND, env=os.environ.copy(),
            capture_output=True, text=True, timeout=300,
        )
        logger.info(f"SETUP {label}\n{done.stdout}\n{done.stderr}")
        if done.returncode != 0:
            raise AssertionError(f"setup '{label}' failed ({done.returncode}): {done.stderr[-600:]}")
        return done.stdout

    @keyword
    def setup_via_manage_py_shell(self, label: str, code: str) -> str:
        """Run Python in `manage.py shell` as labelled setup. Returns stdout."""
        return self.setup_via_manage_py(label, "shell", "-c", code)

    # --- audit log (no API endpoint exists, so read the table) --------------

    @keyword
    def audit_count(self, action: str, target: str | None = None) -> int:
        sql, args = "SELECT COUNT(*) FROM core_auditlog WHERE action=?", [action]
        if target:
            sql, args = sql + " AND target=?", args + [target]
        with sqlite3.connect(f"file:{_sqlite_path()}?mode=ro", uri=True, timeout=10) as conn:
            return conn.execute(sql, args).fetchone()[0]

    @keyword
    def audit_rows(self, action: str, target: str | None = None) -> list:
        """Every audit row for an action (optionally one target), as dicts."""
        sql, args = "SELECT * FROM core_auditlog WHERE action=?", [action]
        if target:
            sql, args = sql + " AND target=?", args + [target]
        with sqlite3.connect(f"file:{_sqlite_path()}?mode=ro", uri=True, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, args).fetchall()]

    @keyword
    def stored_files(self, pattern: str = "**/*.pdf") -> list:
        """Files under MEDIA_ROOT, as paths relative to it."""
        root = Path(os.environ["MEDIA_ROOT"])
        return sorted(str(p.relative_to(root)) for p in root.glob(pattern) if p.is_file())

    # --- synthetic data -----------------------------------------------------

    @keyword
    def make_students(self, first: int, count: int, batch: int, cgpa: str = "8.50",
                      department: str = "B.Tech Computer Science",
                      school: str = "computing_data_science", tag: str = "e2e") -> list:
        """`count` roster rows, PRN sequences first..first+count-1 (800-899 only)."""
        first, count, batch = int(first), int(count), int(batch)
        if first < FIRST_SEQ or first + count - 1 > LAST_SEQ:
            raise AssertionError(f"PRN sequences must stay in {FIRST_SEQ}-{LAST_SEQ}")
        rows = []
        for seq in range(first, first + count):
            rows.append({
                "prn": f"{PRN_PREFIX}{seq}", "email": f"{tag}.student{seq}@college.edu",
                "name": f"E2E Student {seq}", "department": department, "school": school,
                "batch": batch, "cgpa": cgpa, "phone": f"98200{seq:05d}"[:10],
            })
        return rows

    @keyword
    def roster_csv(self, students: list, eligible: bool = True) -> bytes:
        lines = ["prn,email,full_name,department,school,year_of_study,batch,cgpa,phone,is_placement_eligible"]
        for s in students:
            lines.append(
                f"{s['prn']},{s['email']},{s['name']},{s['department']},{s['school']},4,"
                f"{s['batch']},{s['cgpa']},{s['phone']},{'true' if eligible else 'false'}"
            )
        return ("\n".join(lines) + "\n").encode()

    @keyword
    def render_transcript(self, prn: str, name: str, cgpa: str = "8.50") -> bytes:
        """A synthetic transcript PDF (the backend's own fixture code)."""
        from checkpoints.transcript_fixtures import render_transcript

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.pdf"
            render_transcript(path, prn=prn, name=name, cgpa=cgpa)
            return path.read_bytes()

    @keyword
    def sample_resume(self, index: int = 0) -> tuple:
        """(filename, bytes) of one generated sample resume."""
        directory = BACKEND / "fixtures" / "resumes"
        names = list(json.loads((directory / "reference.json").read_text()))
        name = names[int(index) % len(names)]
        return name, (directory / name).read_bytes()

    # --- tokens -------------------------------------------------------------

    @keyword
    def token_claims(self, token: str) -> dict:
        """The claims of a JWT, WITHOUT verifying it."""
        import jwt

        return jwt.decode(token, options={"verify_signature": False})

    @keyword
    def verify_token_against_jwks(self, token: str, jwks: dict) -> dict:
        """Verify signature, issuer and audience with the published key. Returns the claims."""
        import jwt

        unverified = jwt.decode(token, options={"verify_signature": False})
        kid = jwt.get_unverified_header(token).get("kid")
        match = [k for k in jwks["keys"] if k.get("kid") == kid]
        if not match:
            raise AssertionError(f"kid {kid!r} is not in the JWKS ({[k.get('kid') for k in jwks['keys']]})")
        key = jwt.PyJWK(match[0]).key
        return jwt.decode(token, key, algorithms=["RS256"], audience=unverified["aud"], issuer=unverified["iss"])

    # --- generic inspection -------------------------------------------------

    @keyword
    def keys_starting_with(self, document, *prefixes: str) -> list:
        """Every key anywhere in a JSON document that starts with one of the prefixes."""
        found = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if any(str(key).startswith(p) for p in prefixes):
                        found.append(key)
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(document)
        return found

    @keyword
    def parse_csv(self, text: str) -> list:
        return list(csv.reader(io.StringIO(text)))

    @keyword
    def decode_base64(self, value: str) -> bytes:
        return base64.b64decode(value)

    @keyword
    def bytes_to_text(self, data: bytes) -> str:
        return data.decode("utf-8", errors="replace")

    # --- the AES contact zip and the plain CV zip ---------------------------

    @keyword
    def read_aes_zip(self, data: bytes, password: str) -> dict:
        """{name: bytes} of every member, opened with the password (pyzipper)."""
        import pyzipper

        with pyzipper.AESZipFile(io.BytesIO(data)) as archive:
            archive.setpassword(password.encode())
            return {name: archive.read(name) for name in archive.namelist()}

    @keyword
    def aes_zip_refuses_without_password(self, data: bytes) -> bool:
        """True when reading a member with no password, and with a wrong one, is refused."""
        import pyzipper

        for pw in (None, b"definitely-not-the-password"):
            with pyzipper.AESZipFile(io.BytesIO(data)) as archive:
                if pw:
                    archive.setpassword(pw)
                try:
                    archive.read(archive.namelist()[0])
                except Exception:  # noqa: BLE001 - any refusal counts
                    continue
                return False
        return True

    @keyword
    def aes_zip_is_aes256(self, data: bytes) -> bool:
        """True when every member carries the WinZip-AES extra field with strength 3 (256-bit)."""
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            for info in infos:
                extra, ok = info.extra, False
                while len(extra) >= 4:
                    header, size = int.from_bytes(extra[:2], "little"), int.from_bytes(extra[2:4], "little")
                    # data: version (2), vendor "AE" (2), strength (1), real method (2)
                    if header == 0x9901 and size >= 7 and extra[4 + 4] == 3:
                        ok = True
                    extra = extra[4 + size:]
                if not ok:
                    return False
            return bool(infos)

    @keyword
    def zip_names(self, data: bytes) -> list:
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return archive.namelist()

    @keyword
    def zip_member(self, data: bytes, name: str) -> bytes:
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return archive.read(name)
