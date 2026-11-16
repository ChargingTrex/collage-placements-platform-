#!/usr/bin/env python
"""
One command for the API-journey suites (Layer 1 of E2E_SUITE_PLAN.md).

    cd backend
    ../.venv/bin/python e2e/run.py                   # every suite
    ../.venv/bin/python e2e/run.py --suite identity,addendum
    ../.venv/bin/python e2e/run.py --keep            # keep the run folder
    ../.venv/bin/python e2e/run.py --strict          # the final gate

What it does, in order:
  1. Makes a fresh run folder e2e/.runs/<timestamp>/ and points DATABASE_URL,
     MEDIA_ROOT, the cache and the dev signing keys at it. The server, every
     manage.py call and Robot itself share exactly that environment. It never
     touches db.sqlite3 or media/.
  2. Forces a deterministic, offline environment whatever the repo-root .env
     says (the process environment beats .env: settings.py calls
     load_dotenv without override).
  3. Generates the sample resumes and transcripts if they are missing.
  4. migrate + seed_demo, a server on a free port, Robot Framework over the
     selected suites, the server stopped (always), `N/M passed` per suite.

`phase_0_3` runs on its own fresh database and server. The other suites share
a second one. A suite whose feature is "not built yet" (a 404 on its one probe
route) is reported as NOT BUILT, separately from failures; --strict makes that
a failure too. A skip that is not NOT BUILT, a missing seed, or a suite with
zero executed tests is always a FAIL.

`django_server()` is the reusable part (environment, migrate, seed, free port,
teardown) so a later browser layer can start the same server.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

E2E = Path(__file__).resolve().parent
BACKEND = E2E.parent
RUNS = E2E / ".runs"
SUITES_DIR = E2E / "suites"

#: Suites in run order. The first one needs a database of its own.
OWN_DATABASE = ("phase_0_3",)
SHARED_DATABASE = ("identity", "addendum", "phase_b", "suggestions", "exports")
ALL_SUITES = OWN_DATABASE + SHARED_DATABASE


# --- environment ------------------------------------------------------------


def build_env(run_dir: Path, name: str) -> dict[str, str]:
    """The one environment for the server, manage.py and Robot of one database."""
    base = run_dir / name
    base.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    # Anything the developer exported that could change behaviour is dropped
    # first, so only the values below (and defaults) are in force.
    for key in list(env):
        if key.startswith(("DJANGO_", "LLM_", "MONGO", "VECTOR_", "MATCHING_", "MATCH_", "OTP_",
                           "EXPOSE_", "DEMO_", "SERVE_DEMO", "CACHE_", "SUGGESTIONS_", "SHORTLIST_",
                           "OPPORTUNIT", "JWT_", "STORAGE_", "TRUSTED_PROXY", "DEV_KEY", "DEFAULT_SIMILARITY",
                           "EMAIL_", "ALLOWED_STUDENT", "CORS_", "CSRF_", "PRN_REGEX", "PLATFORM_JWKS")):
            del env[key]
    env.update(
        DATABASE_URL=f"sqlite:///{base / 'db.sqlite3'}",
        MEDIA_ROOT=str(base / "media"),
        CACHE_BACKEND="file",
        CACHE_LOCATION=str(base / "cache"),  # absolute: BASE_DIR / absolute is the absolute path
        DEV_KEY_DIR=str(base / "keys"),
        # offline and deterministic
        LLM_ENABLED="false",
        VECTOR_STORE_BACKEND="local",
        MONGO_URI="",  # empty, and present: load_dotenv will not override it
        MATCHING_BACKEND="tfidf",
        DEFAULT_SIMILARITY_THRESHOLD="",
        # OTPs come back in responses: DEBUG on, and the flag explicit
        DJANGO_DEBUG="true",
        EXPOSE_OTP_IN_RESPONSE="true",
        DEMO_MODE="true",
        DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1",
        TRUSTED_PROXY_COUNT="0",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        # the run must never throttle itself
        OTP_THROTTLE_RATE="100000/hour",
        ANON_THROTTLE_RATE="100000/hour",
        MATCHING_THROTTLE_RATE="100000/hour",
        EXPORT_THROTTLE_RATE="100000/hour",
        OTP_REQUESTS_PER_WINDOW="100000",
        PYTHONUNBUFFERED="1",
        E2E_PYTHON=sys.executable,
    )
    for sub in ("media", "cache", "keys"):
        (base / sub).mkdir(exist_ok=True)
    return env


def manage(env: dict, *args: str, label: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    if label:
        print(f"  setup: {label}", flush=True)
    done = subprocess.run(
        [sys.executable, "manage.py", *args], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    if check and done.returncode != 0:
        raise SystemExit(f"manage.py {' '.join(args)} failed:\n{done.stdout[-800:]}\n{done.stderr[-1500:]}")
    return done


def ensure_fixtures(env: dict) -> None:
    """The sample resumes are gitignored; a clean clone generates them."""
    resumes = BACKEND / "fixtures" / "resumes"
    if not (resumes / "aarav_mehta_backend.pdf").exists():
        manage(env, "make_sample_resumes", label="generating the sample resumes (missing)")
    if not (BACKEND / "fixtures" / "transcripts" / "transcript_clean.pdf").exists():
        manage(env, "make_sample_transcripts", label="generating the sample transcripts (missing)")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class Server:
    name: str
    env: dict
    base_url: str
    db_path: Path
    media_root: Path
    process: subprocess.Popen
    log_path: Path


@contextlib.contextmanager
def django_server(run_dir: Path, name: str, seed: bool = True):
    """Prepare a fresh database, start Django on a free port, always stop it.

    Reusable: a browser layer can use this and add its own dev server.
    """
    env = build_env(run_dir, name)
    ensure_fixtures(env)
    manage(env, "migrate", "--noinput", label=f"[{name}] migrate a fresh database")
    if seed:
        manage(env, "seed_demo", label=f"[{name}] seed_demo (plain: admins, companies, roster)")
    port = free_port()
    log_path = run_dir / name / "server.log"
    log = log_path.open("w")
    process = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 90
        while True:
            if process.poll() is not None:
                raise SystemExit(f"server exited early; see {log_path}\n{log_path.read_text()[-1500:]}")
            try:
                with urllib.request.urlopen(base_url + "/api/health", timeout=3) as resp:
                    if resp.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            if time.time() > deadline:
                raise SystemExit(f"server did not become healthy; see {log_path}")
            time.sleep(0.3)
        print(f"  [{name}] server up at {base_url}", flush=True)
        yield Server(name, env, base_url, run_dir / name / "db.sqlite3", run_dir / name / "media", process, log_path)
    finally:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
        log.close()
        print(f"  [{name}] server stopped", flush=True)


# --- Robot ------------------------------------------------------------------


@dataclass
class SuiteResult:
    name: str
    passed: int = 0
    failed: int = 0
    skipped_not_built: int = 0
    skipped_other: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def total_run(self) -> int:
        return self.passed + self.failed

    @property
    def not_built(self) -> bool:
        return self.skipped_not_built > 0 and self.passed == 0 and self.failed == 0 and self.skipped_other == 0

    @property
    def failing(self) -> bool:
        if self.not_built:
            return False
        return self.failed > 0 or self.skipped_other > 0 or self.skipped_not_built > 0 or self.passed == 0


def run_robot(server: Server, suites: list[str], run_dir: Path) -> list[SuiteResult]:
    out_dir = run_dir / f"robot-{server.name}"
    cmd = [
        sys.executable, "-m", "robot", "--outputdir", str(out_dir), "--nostatusrc", "--consolecolors", "off",
        "--variable", f"BASE_URL:{server.base_url}",
        "--variable", f"DB_PATH:{server.db_path}",
        "--variable", f"MEDIA_ROOT:{server.media_root}",
        "--variable", f"PYTHON:{sys.executable}",
        "--variable", f"BACKEND_DIR:{BACKEND}",
        *[str(SUITES_DIR / f"{s}.robot") for s in suites],
    ]
    # Robot runs in the server's environment, so its manage.py setup calls and
    # its audit-table reads see exactly the database and media folder the server uses.
    subprocess.run(cmd, cwd=BACKEND, env=server.env)
    return parse_results(out_dir / "output.xml", suites)


def parse_results(output_xml: Path, suites: list[str]) -> list[SuiteResult]:
    from robot.api import ExecutionResult

    results = {s: SuiteResult(s) for s in suites}
    if not output_xml.exists():
        for r in results.values():
            r.notes.append("Robot produced no output.xml")
        return list(results.values())
    root = ExecutionResult(str(output_xml)).suite
    for test in root.all_tests:
        stem = Path(test.parent.source).stem if test.parent and test.parent.source else test.parent.name
        res = results.get(stem)
        if res is None:
            continue
        if test.status == "PASS":
            res.passed += 1
            if test.message:
                res.notes.append(test.message)
        elif test.status == "SKIP":
            if "NOT BUILT" in (test.message or "") or "not-built" in {str(t).lower() for t in test.tags}:
                res.skipped_not_built += 1
            else:
                res.skipped_other += 1
                res.notes.append(f"skipped: {test.name}: {test.message}")
        else:
            res.failed += 1
            res.notes.append(f"FAIL {test.name}: {(test.message or '')[:400]}")
    for r in results.values():
        if r.passed + r.failed + r.skipped_not_built + r.skipped_other == 0:
            r.notes.append("zero tests executed")
    return list(results.values())


# --- main -------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="Run the API-journey suites (Robot Framework) against a live server.")
    p.add_argument("--suite", help=f"comma list of: {', '.join(ALL_SUITES)} (default: all)")
    p.add_argument("--keep", action="store_true", help="keep the run folder after a pass")
    p.add_argument("--strict", action="store_true", help="the final gate: NOT BUILT counts as a failure")
    args = p.parse_args()

    selected = list(ALL_SUITES) if not args.suite else [s.strip() for s in args.suite.split(",") if s.strip()]
    unknown = [s for s in selected if s not in ALL_SUITES]
    if unknown or not selected:
        p.error(f"unknown suite(s) {unknown}; choose from {', '.join(ALL_SUITES)}")
    selected = [s for s in ALL_SUITES if s in selected]  # canonical order

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS / stamp
    run_dir.mkdir(parents=True)
    print(f"run folder: {run_dir}", flush=True)

    results: list[SuiteResult] = []
    try:
        for group, name in ((OWN_DATABASE, "own"), (SHARED_DATABASE, "shared")):
            wanted = [s for s in selected if s in group]
            if not wanted:
                continue
            with django_server(run_dir, "phase_0_3_db" if name == "own" else "shared_db") as server:
                results += run_robot(server, wanted, run_dir)
    except KeyboardInterrupt:
        print("interrupted", flush=True)
        print(f"run folder kept: {run_dir}")
        return 130
    except BaseException:
        print(f"run folder kept: {run_dir}", flush=True)
        raise

    print("\n=== Summary ===")
    failed = False
    for r in sorted(results, key=lambda x: ALL_SUITES.index(x.name)):
        if r.not_built:
            line = f"NOT BUILT   {r.name}  (probe answered 404; {r.skipped_not_built} test(s) skipped)"
            if args.strict:
                line += "  -> FAIL under --strict"
                failed = True
        else:
            verdict = "FAIL" if r.failing else "PASS"
            line = f"{verdict:<11} {r.name}  {r.passed}/{r.total_run + r.skipped_other + r.skipped_not_built} passed"
            if r.skipped_other or r.skipped_not_built:
                line += f"  ({r.skipped_other + r.skipped_not_built} skipped)"
            failed = failed or r.failing
        print(line)
        for note in r.notes:
            print(f"      {note}")
    print("Result:", "FAILED" if failed else "OK")

    if failed or args.keep:
        print(f"run folder kept: {run_dir}  (Robot log: robot-*/log.html)")
    else:
        shutil.rmtree(run_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            RUNS.rmdir()  # only if empty
        print("run folder removed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
