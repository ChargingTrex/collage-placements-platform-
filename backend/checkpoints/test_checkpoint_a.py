"""
Checkpoint A — the identity and auth retrofit gate.

One test (sometimes two) per checkbox in `IMPLEMENTATION_PLAN.md` §5. Written
before the work that ticks them, which is the only discipline that makes a
checkpoint mean anything: a test written afterwards asserts what the code does,
where this one has to assert what the checkbox claims.

Most of these fail today. That is the correct starting state, and the list of
failures is the real definition of Phase A.

Two of them reproduce bugs already measured on 2026-09-30 and recorded in
`TODO.md` — the fail-open query parameter and the per-recruiter shortlist. They
are the proof a fix landed, so they must fail now and pass later, never the
other way round.

Written against the plan documents alone. Nothing here was shaped by reading
stream A-1's implementation, because a gate written from the implementation is
weaker evidence and QA has to be able to say so.

Run alone:

    cd backend && ../.venv/bin/python -m pytest checkpoints/ -q

Conventions this file follows, because a failing gate has to be actionable:

- A feature that does not exist yet is a `pytest.fail` naming what is missing,
  never an ImportError at collection time. A collection error takes the whole
  file down and tells the owning agent nothing.
- Where the plan fixes a name, the test asserts that name. Where it does not —
  the key a batch lookup reports missing PRNs under, for instance — the test
  asserts the observable behaviour and accepts any reasonable naming.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import sqlite3
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse

from checkpoints.conftest import (
    ABSENT_PRN,
    body_without_results,
    claims_in,
    client_for,
    token_for,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


# --- helpers ---------------------------------------------------------------


def missing(what: str, *, needed_for: str) -> None:
    """Fail with the thing that is absent, not with a traceback."""
    pytest.fail(f"NOT BUILT YET: {what}\n  needed for: {needed_for}")


def target(module: str, name: str, *, needed_for: str):
    """Import something Phase A is supposed to add, or fail saying it is not there."""
    import importlib

    try:
        loaded = importlib.import_module(module)
    except ImportError:
        missing(f"module {module}", needed_for=needed_for)
    if not hasattr(loaded, name):
        missing(f"{module}.{name}", needed_for=needed_for)
    return getattr(loaded, name)


def detail_url(list_url: str, identifier) -> str:
    return f"{list_url}/{identifier}"


def fetch_detail(client, list_url: str, profile):
    """
    One profile's detail record, however the API currently addresses it.

    G2 moves PRN out of path parameters and puts a UUID there, so a gate that
    hardcodes either one breaks on the commit that lands the change. This tries
    both and reports what it tried when neither works.
    """
    attempts = []
    for identifier in (
        profile.student.prn,
        profile.pk,
        profile.student.pk,
        profile.user.pk,
    ):
        response = client.get(detail_url(list_url, identifier))
        attempts.append(f"{identifier} -> {response.status_code}")
        if response.status_code == 200:
            return response, identifier
    return None, attempts


# ---------------------------------------------------------------------------
# 1. Migrations apply cleanly from empty AND from a populated Phase 3 database
# ---------------------------------------------------------------------------

#: The migration graph as Phase 3 shipped it. Frozen deliberately: this is a
#: historical state, so a change here means the test is being bent to fit.
PHASE_3_LEAVES = (
    ("accounts", "0002_onetimecode"),
    ("roster", "0001_initial"),
    ("profiles", "0001_initial"),
    ("core", "0001_initial"),
)

#: A populated Phase 3 database, inserted as raw SQL against the Phase 3
#: schema. The ORM cannot do it -- the models in memory are the Phase A ones.
PHASE_3_ROWS = """
INSERT INTO accounts_user
  (id,password,last_login,is_superuser,email,role,prn,full_name,
   is_active,is_staff,email_verified_at,date_joined)
VALUES
  (1,'!',NULL,0,'anaya.krishnan@college.edu','student','220200921',
   'Anaya Krishnan',1,0,'2026-09-01 00:00:00','2026-09-01 00:00:00'),
  (2,'!',NULL,0,'careers@acmetech.example','company',NULL,
   'Acme Tech',1,0,NULL,'2026-09-01 00:00:00');

INSERT INTO roster_student
  (id,created_at,updated_at,prn,email,full_name,department,batch,cgpa,
   phone,is_placement_eligible)
VALUES
  (1,'2026-09-01 00:00:00','2026-09-01 00:00:00','220200921',
   'anaya.krishnan@college.edu','Anaya Krishnan','B.Tech Computer Science',
   2026,8.72,'',1);

INSERT INTO profiles_studentprofile
  (id,created_at,updated_at,headline,summary,phone,github_url,linkedin_url,
   website_url,experience_years,education_level,resume,resume_filename,
   resume_text,resume_uploaded_at,parsed_experience_years,
   parsed_education_levels,parsed_values_confirmed,visibility,is_verified,
   verified_at,student_id,user_id,verified_by_id)
VALUES
  (1,'2026-09-01 00:00:00','2026-09-01 00:00:00','Backend developer','','',
   '','','',3.0,'UG',NULL,'','',NULL,NULL,'[]',0,'shortlisted',0,NULL,1,1,NULL);

INSERT INTO profiles_companyshortlist
  (id,created_at,updated_at,note,company_id,profile_id)
VALUES
  (1,'2026-09-01 00:00:00','2026-09-01 00:00:00','',2,1);
"""


def run_migrate(database: Path, *args: str):
    """`manage.py migrate` against one throwaway database file."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database}"}
    return subprocess.run(
        [str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable),
         "manage.py", "migrate", "--no-input", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestMigrations:
    """
    Checkbox 1.

    The second half is the one that bites. A primary key change rewrites every
    foreign key, and `AlterField` to a UUID does not convert the integers
    already sitting in the column -- it reports OK and leaves the database
    unreadable. A gate that only migrates an empty database never sees it.
    """

    def test_migrations_apply_cleanly_to_an_empty_database(self, tmp_path):
        database = tmp_path / "empty.sqlite3"

        result = run_migrate(database)

        assert result.returncode == 0, (
            f"migrate failed from empty:\n{result.stdout}\n{result.stderr}"
        )
        assert database.exists()

    def test_the_uuid_migration_refuses_loudly_on_a_populated_phase_3_database(
        self, tmp_path
    ):
        """
        Re-scoped by DECISIONS D11 (confirmed 2026-10-20).

        The checkbox originally said "applies cleanly". Django's integer->UUID
        AlterField reports OK and leaves integers in a UUID column, so the
        only safe options are a full backfill or a refusal. The data is
        synthetic, so the product owner chose refusal. This test pins it:
        migrate fails, the message names the reset path, and nothing in the
        database was touched. If a backfill is ever written, restore the
        "applies cleanly" assertions instead.
        """
        database = tmp_path / "phase3.sqlite3"

        for app, leaf in PHASE_3_LEAVES:
            step = run_migrate(database, app, leaf)
            assert step.returncode == 0, (
                f"could not build the Phase 3 state ({app} {leaf}):\n{step.stderr}"
            )

        connection = sqlite3.connect(database)
        connection.executescript(PHASE_3_ROWS)
        connection.commit()
        connection.close()

        result = run_migrate(database)
        output = result.stdout + result.stderr

        # Loud: a non-zero exit, a reason, and the way out.
        assert result.returncode != 0, (
            "migrate reported success on a populated Phase 3 database; the UUID "
            f"change would have corrupted it:\n{output}"
        )
        assert "Refusing to migrate" in output, f"no refusal message:\n{output}"
        assert "manage.py migrate" in output and "seed_demo" in output, (
            f"the refusal does not name the reset path:\n{output}"
        )

        connection = sqlite3.connect(database)
        try:
            users = connection.execute(
                "SELECT id, email, prn FROM accounts_user ORDER BY email"
            ).fetchall()
            students = connection.execute(
                "SELECT id, prn FROM roster_student"
            ).fetchall()
            linked = connection.execute(
                "SELECT p.id FROM profiles_studentprofile p "
                "JOIN accounts_user u ON u.id = p.user_id "
                "JOIN roster_student s ON s.id = p.student_id"
            ).fetchall()
            shortlists = connection.execute(
                "SELECT COUNT(*) FROM profiles_companyshortlist"
            ).fetchone()[0]
        finally:
            connection.close()

        # Untouched: every row is still there and still joins.
        assert len(users) == 2, f"users lost in the refused migration: {users}"
        assert [row[1] for row in students] == ["220200921"]
        assert len(linked) == 1, "the profile no longer joins to its user and roster row"
        assert shortlists == 1

        # And nothing was half-converted: the ids are still the original integers.
        assert sorted(row[0] for row in users) == [1, 2], f"user ids changed: {users}"


# ---------------------------------------------------------------------------
# 2-4. The claim contract
# ---------------------------------------------------------------------------

#: `docs/agents/A1-identity.md`, quoting the shared spec §5.4. Exact, not
#: approximate: every key present in every mode, optional values null.
CLAIM_CONTRACT = frozenset(
    {
        "sub", "iss", "aud", "iat", "exp", "email", "student_id", "prn",
        "display_name", "roles", "department", "programme", "year", "mfa",
    }
)

#: Standard JWT/simplejwt machinery, allowed alongside the contract.
CLAIM_MACHINERY = frozenset({"jti", "token_type", "nbf", "iss_at", "user_id"})


@pytest.mark.django_db
class TestClaimContract:
    """Checkboxes 2, 3 and 4."""

    def test_a_token_carrying_the_full_claim_set_validates_and_authorises(
        self, profiles
    ):
        """
        Checkbox 2.

        Two halves, and both have to hold at once: the token the portal mints
        carries the whole §5.4 claim set, *and* it gets its holder through the
        door. Either alone passes today -- the current token authorises fine
        and carries three claims.
        """
        student = profiles[0].user
        token = token_for(student)
        claims = claims_in(token)

        absent = sorted(CLAIM_CONTRACT - set(claims))
        assert not absent, f"claims missing from the token: {absent}"

        client = client_for(student)
        assert client.get(reverse("auth-me")).status_code == 200

    def test_every_claim_is_present_for_every_role_with_optional_values_null(
        self, profiles, placement_admin, recruiter
    ):
        """
        Checkbox 3.

        A consumer reading `claims["prn"]` must not KeyError on a staff token.
        That is why the rule is "null, never omitted" rather than "present when
        it applies" -- the second shape makes every reader defensive.
        """
        by_role = {
            "student": claims_in(token_for(profiles[0].user)),
            "admin": claims_in(token_for(placement_admin)),
            "company": claims_in(token_for(recruiter)),
        }

        for role, claims in by_role.items():
            absent = sorted(CLAIM_CONTRACT - set(claims))
            assert not absent, f"{role} token is missing claims: {absent}"

        key_sets = {role: frozenset(claims) for role, claims in by_role.items()}
        assert len(set(key_sets.values())) == 1, (
            "token key sets differ by role, so a claim is being omitted rather "
            f"than nulled: { {role: sorted(keys) for role, keys in key_sets.items()} }"
        )

        # The optional ones, on a role that cannot have them.
        admin = by_role["admin"]
        assert admin["prn"] is None
        assert admin["student_id"] is None

    def test_roles_is_an_array_and_no_token_carries_a_single_role_string(
        self, profiles, placement_admin, recruiter
    ):
        """
        Checkbox 4.

        `roles` plural and a list, every time. A single `role` string is the
        shape that makes `company_recruiter:<uuid>` scoping impossible to
        express, so it is not merely untidy.
        """
        for who, user in (
            ("student", profiles[0].user),
            ("admin", placement_admin),
            ("company", recruiter),
        ):
            claims = claims_in(token_for(user))
            assert "roles" in claims, f"{who} token has no `roles` claim"
            assert isinstance(claims["roles"], list), (
                f"{who} token: roles is {type(claims['roles']).__name__}, not a list"
            )
            assert "role" not in claims, (
                f"{who} token still carries a singular `role` claim: {claims.get('role')!r}"
            )

    def test_a_token_whose_roles_name_the_placement_admin_reaches_admin_endpoints(
        self, placement_admin, as_admin
    ):
        """
        Checkbox 4, behavioural half.

        Role names are `lower_snake_case` per the spec's §4.3, which makes the
        placement admin `placement_admin` rather than the current `admin`.
        """
        claims = claims_in(token_for(placement_admin))
        roles = claims.get("roles")
        assert isinstance(roles, list), "no `roles` array to check"
        assert "placement_admin" in roles, f"admin roles are {roles!r}"
        assert as_admin.get(reverse("admin-profile-list")).status_code == 200

    def test_the_me_payload_exposes_roles_as_an_array(self, profiles):
        """
        Checkbox 4, the other reader.

        The frontend routes on this payload. If it still says `role`, A5's
        `roles[]` migration has nothing to read.
        """
        payload = client_for(profiles[0].user).get(reverse("auth-me")).json()

        assert "roles" in payload, f"`me` payload keys: {sorted(payload)}"
        assert isinstance(payload["roles"], list)
        assert "role" not in payload, "`me` still exposes a singular role string"

    def test_no_backend_module_writes_a_singular_role_claim_onto_a_token(self):
        """
        Checkbox 4, source level.

        `tokens_for` sets `refresh["role"]` today. Every reader of that claim
        changes, so the claim itself has to go -- a behavioural test on one
        endpoint would not catch a second minting path.
        """
        offenders = []
        pattern = re.compile(r"""\[\s*["']role["']\s*\]\s*=""")
        for path in sorted(BACKEND_DIR.rglob("*.py")):
            parts = set(path.parts)
            if "migrations" in parts or "tests" in parts or "checkpoints" in parts:
                continue
            if ".venv" in parts:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(BACKEND_DIR)}:{number}: {line.strip()}")

        assert not offenders, "a singular `role` claim is still being written:\n" + "\n".join(
            offenders
        )


# ---------------------------------------------------------------------------
# 5-7. Token lifetime, refresh replay, signing keys
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTokenLifetime:
    """Checkbox 5."""

    def test_an_access_token_expires_fifteen_minutes_after_it_is_issued(self, profiles):
        """
        Asserted on the token, not on the setting: a 15-minute setting that
        some other code path overrides is still a 60-minute token.
        """
        claims = claims_in(token_for(profiles[0].user))

        assert "iat" in claims and "exp" in claims, (
            f"token carries no iat/exp pair: {sorted(claims)}"
        )
        lifetime = timedelta(seconds=claims["exp"] - claims["iat"])
        assert lifetime == timedelta(minutes=15), (
            f"access token lifetime is {lifetime}, not 15 minutes"
        )

    def test_an_access_token_one_second_past_its_lifetime_is_refused(self, profiles):
        """
        The expiry has to be enforced, not merely declared. No freezegun in
        this environment, so the clock moves by minting the token in the past.
        """
        from django.conf import settings
        from django.utils import timezone
        from rest_framework_simplejwt.tokens import AccessToken

        lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        expired = AccessToken.for_user(profiles[0].user)
        expired.set_exp(
            from_time=timezone.now() - lifetime - timedelta(seconds=1),
            lifetime=lifetime,
        )

        from rest_framework.test import APIClient

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")

        assert client.get(reverse("auth-me")).status_code == 401


@pytest.mark.django_db
class TestRefreshReplay:
    """Checkbox 6."""

    def test_replaying_a_consumed_refresh_token_revokes_the_whole_family(
        self, profiles
    ):
        """
        Rotation without revocation is theatre: if a stolen refresh token still
        works after the legitimate holder has rotated it, rotation has bought
        nothing. Replaying a consumed token is evidence of theft, so both the
        replayed token and the one that replaced it must die.
        """
        from accounts.serializers import tokens_for
        from rest_framework.test import APIClient

        client = APIClient()
        original = tokens_for(profiles[0].user)["refresh"]
        url = reverse("auth-refresh")

        first = client.post(url, {"refresh": original}, format="json")
        assert first.status_code == 200, f"legitimate rotation failed: {first.content}"
        rotated = first.json().get("refresh")
        assert rotated, "rotation returned no new refresh token"

        replayed = client.post(url, {"refresh": original}, format="json")
        assert replayed.status_code == 401, (
            f"a consumed refresh token still works (HTTP {replayed.status_code})"
        )

        after = client.post(url, {"refresh": rotated}, format="json")
        assert after.status_code == 401, (
            "the replay did not revoke the family: the rotated token still works "
            f"(HTTP {after.status_code})"
        )


@pytest.mark.django_db
class TestSigningKeys:
    """Checkbox 7."""

    #: Where a JWKS could reasonably live. The plan does not fix the path, so
    #: the gate accepts any of these and reports all of them when none answers.
    JWKS_PATHS = (
        "/api/auth/jwks",
        "/api/auth/.well-known/jwks.json",
        "/.well-known/jwks.json",
        "/api/.well-known/jwks.json",
        "/api/auth/keys",
    )

    def test_the_portal_publishes_a_jwks_the_access_token_can_be_verified_against(
        self, profiles
    ):
        """
        D5's whole point: the portal issues its own tokens now and accepts the
        platform's later, and the switch is a key-source change. That only
        works if verification goes through a published key set rather than a
        shared secret.
        """
        import jwt
        from rest_framework.test import APIClient

        client = APIClient()
        found = None
        tried = []
        for path in self.JWKS_PATHS:
            response = client.get(path)
            tried.append(f"{path} -> {response.status_code}")
            if response.status_code == 200:
                found = response
                break

        if found is None:
            missing(
                "a JWKS endpoint (tried " + ", ".join(tried) + ")",
                needed_for="checkbox 7 — a token signed by a second key pair validates",
            )

        keys = found.json().get("keys")
        assert isinstance(keys, list) and keys, f"JWKS has no keys: {found.json()}"
        for key in keys:
            assert key.get("kty") == "RSA", f"non-RSA key published: {key}"
            assert key.get("kid"), f"published key has no kid: {key}"

        header = jwt.get_unverified_header(token_for(profiles[0].user))
        assert header.get("alg") == "RS256", f"tokens are signed with {header.get('alg')}"
        assert header.get("kid") in {key["kid"] for key in keys}, (
            f"the token's kid {header.get('kid')!r} is not in the published set"
        )

    def test_a_token_signed_by_a_second_published_key_pair_is_accepted(self, profiles):
        """
        Rotation is the reason JWKS exists. During a rotation two key pairs are
        live at once and tokens signed by either must authenticate, which means
        verification resolves the key by `kid` rather than holding one key.

        The seam is `settings.IDENTITY["KEYS"]` ({kid: {private, public}}) plus
        `ACTIVE_KID`, which picks the key new tokens are signed with.
        """
        import jwt
        from django.conf import settings
        from django.test import override_settings
        from rest_framework.test import APIClient

        from accounts.identity import _generate_keypair, reset_keyring

        old_private, old_public = _generate_keypair()
        new_private, new_public = _generate_keypair()
        keys = {
            "rotate-old": {"private": old_private, "public": old_public},
            "rotate-new": {"private": new_private, "public": new_public},
        }
        user = profiles[0].user

        def identity(active):
            return {**settings.IDENTITY, "KEYS": keys, "ACTIVE_KID": active}

        try:
            # Mint one token under each active key. The keyring is cached, so
            # it must be reset each time the settings change.
            tokens = {}
            for kid in keys:
                with override_settings(IDENTITY=identity(kid)):
                    reset_keyring()
                    tokens[kid] = token_for(user)

            # Mid-rotation: the new key signs, the old one is still published.
            with override_settings(IDENTITY=identity("rotate-new")):
                reset_keyring()
                published = {key["kid"] for key in APIClient().get("/api/auth/jwks").json()["keys"]}
                assert published == set(keys), f"JWKS publishes {published}"

                for kid, token in tokens.items():
                    assert jwt.get_unverified_header(token)["kid"] == kid
                    client = APIClient()
                    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                    response = client.get(reverse("my-profile"))
                    assert response.status_code == 200, (
                        f"a token signed by {kid} was refused mid-rotation "
                        f"(HTTP {response.status_code})"
                    )
        finally:
            # Back to the default dev key for every later test.
            reset_keyring()


# ---------------------------------------------------------------------------
# 8-9. PRN and email never carry a join
# ---------------------------------------------------------------------------


def url_patterns():
    """Every route in the project, flattened, with its full pattern string."""
    from django.urls import get_resolver
    from django.urls.resolvers import URLPattern, URLResolver

    def walk(resolver, prefix=""):
        for entry in resolver.url_patterns:
            pattern = prefix + str(entry.pattern)
            if isinstance(entry, URLPattern):
                yield pattern, entry
            elif isinstance(entry, URLResolver):
                yield from walk(entry, pattern)

    return list(walk(get_resolver()))


class TestNoHumanKeyCarriesAJoin:
    """Checkboxes 8 and 9."""

    def test_no_api_path_parameter_contains_a_prn(self):
        """
        Checkbox 8.

        PRN stays the human key and every list endpoint filters on it (§3.5) --
        what it stops being is an address. A PRN in a path makes the URL change
        whenever the registrar's format does, and it puts a student's document
        identifier in every server log and browser history.
        """
        offenders = [
            pattern
            for pattern, _ in url_patterns()
            if "prn" in pattern.lower() and pattern.startswith("api/")
        ]

        assert not offenders, "PRN still appears in path parameters:\n" + "\n".join(
            offenders
        )

    def test_no_foreign_key_references_prn_or_email(self):
        """
        Checkbox 9. The binding rule: UUID is the only key.

        `FlaggedSignup.prn` is not a violation -- it deliberately stores PRNs
        matching no student, which is the entire point of the review queue.
        A *foreign key* targeting the column is what cannot exist.
        """
        from django.apps import apps

        offenders = []
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not getattr(field, "is_relation", False):
                    continue
                if not getattr(field, "related_model", None):
                    continue
                target_field = getattr(field, "target_field", None)
                if target_field is None:
                    continue
                if target_field.name in {"prn", "email"}:
                    offenders.append(
                        f"{model._meta.label}.{field.name} -> "
                        f"{field.related_model._meta.label}.{target_field.name}"
                    )

        assert not offenders, "foreign keys on a human key:\n" + "\n".join(offenders)

    #: Model -> the route that puts its primary key in a URL. DRF's router
    #: addresses a record by `pk`, so "UUID in every path parameter" is a
    #: statement about these models' primary keys.
    RECORDS_ADDRESSED_BY_PATH = {
        "accounts.User": "the `sub` claim and auth/me",
        "roster.Student": "roster/students/<pk>",
        "roster.FlaggedSignup": "roster/flagged/<pk>",
        "profiles.StudentProfile": "profiles/admin/<pk>, profiles/students/<pk>",
        "profiles.ExperienceEntry": "profiles/me/experience/<pk>",
        "profiles.ProjectEntry": "profiles/me/projects/<pk>",
        "profiles.ProfileSkill": "profiles/me/skills/<pk>",
    }

    def test_every_record_addressed_by_a_path_parameter_has_a_uuid_primary_key(self):
        """
        G2's other half, and the reason checkbox 8 is not simply "delete the
        PRN route": what replaces it has to be the UUID, not an integer
        sequence. `/profiles/me/experience/41` is enumerable and leaks how many
        rows the portal holds, and an integer key is the one thing the binding
        rule names -- UUID is the only key.

        Beyond the 21 checkboxes; recorded here because G2 is A-1's and nothing
        else in this file would catch it.
        """
        from django.apps import apps
        from django.db import models as django_models

        offenders = []
        for label, route in self.RECORDS_ADDRESSED_BY_PATH.items():
            try:
                model = apps.get_model(label)
            except LookupError:
                continue
            primary = model._meta.pk
            if not isinstance(primary, django_models.UUIDField):
                offenders.append(
                    f"{label}.{primary.name} is {type(primary).__name__} ({route})"
                )

        assert not offenders, (
            "records are still addressed by an integer sequence:\n"
            + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# 10. PRN regex from shared configuration
# ---------------------------------------------------------------------------


class TestPrnRegex:
    """Checkbox 10."""

    #: Candidate homes for the shared PRN rule. A3's stream moves it out of
    #: `roster/models.py`; the plan does not say to which module.
    LOCATIONS = (
        ("core.identity", "PRN_REGEX"),
        ("core.config", "PRN_REGEX"),
        ("core.shared", "PRN_REGEX"),
        ("config.identity", "PRN_REGEX"),
    )

    def _shared_regex(self):
        import importlib

        from django.conf import settings

        for dotted in ("IDENTITY", "SHARED", "PLACEMENT"):
            block = getattr(settings, dotted, None)
            if isinstance(block, dict) and block.get("PRN_REGEX"):
                return block["PRN_REGEX"], f"settings.{dotted}['PRN_REGEX']"

        for module, name in self.LOCATIONS:
            try:
                loaded = importlib.import_module(module)
            except ImportError:
                continue
            if hasattr(loaded, name):
                return getattr(loaded, name), f"{module}.{name}"
        return None, None

    def test_the_prn_pattern_is_read_from_shared_configuration(self):
        """
        G8. Hardcoded in `roster/models.py` today, which means the registrar's
        format lives in one app's model file while signup, filters and the
        document check all need the same rule.
        """
        regex, where = self._shared_regex()
        if regex is None:
            missing(
                "a shared PRN pattern (looked in settings.IDENTITY/SHARED/PLACEMENT "
                "and " + ", ".join(f"{m}.{n}" for m, n in self.LOCATIONS) + ")",
                needed_for="checkbox 10 — PRN regex read from shared config",
            )

        assert re.fullmatch(r"\^?\[0-9\]\{9\}\$?", str(regex).replace(" ", "")), (
            f"{where} is {regex!r}, not the nine-digit rule D4 settled on"
        )

    @pytest.mark.parametrize(
        "candidate,accepted",
        [
            ("220200921", True),
            ("PRN2022CS001", False),
            ("22020092", False),
            ("2202009211", False),
            ("22020092X", False),
        ],
    )
    def test_the_validator_accepts_nine_digits_and_nothing_else(
        self, candidate, accepted
    ):
        """
        D4: the transcript is an issued document and prints nine digits. The
        spec's illustrative `21CS1042` loses to it, and so does the invented
        `PRN2022CS001` the fixtures still use.
        """
        from django.core.exceptions import ValidationError

        from roster.models import PRN_VALIDATOR

        if accepted:
            PRN_VALIDATOR(candidate)
            return
        with pytest.raises(ValidationError):
            PRN_VALIDATOR(candidate)


# ---------------------------------------------------------------------------
# 11. Unknown department codes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUnknownDepartmentCode:
    """Checkbox 11."""

    def test_an_unknown_department_code_surfaces_as_unknown_and_logs(
        self, as_admin, caplog
    ):
        """
        G10. The binding rule is that an unrecognised code is never silently
        mapped to something plausible -- a roster row that quietly becomes
        "B.Tech Computer Science" because it looked close is how a placement
        report comes out wrong with no trace of why.

        Either shape counts as surfacing: the row is rejected naming the
        department, or it is accepted and the response reports the code as
        unknown. Silence does not.
        """
        import logging

        from django.core.files.uploadedfile import SimpleUploadedFile

        bogus = "Department of Wizardry"
        csv = (
            "prn,email,full_name,department,batch,cgpa\n"
            f"230200924,luna.pillai@college.edu,Luna Pillai,{bogus},2027,8.10\n"
        ).encode()

        with caplog.at_level(logging.WARNING):
            response = as_admin.post(
                reverse("roster-upload"),
                {"file": SimpleUploadedFile("roster.csv", csv, content_type="text/csv")},
                format="multipart",
            )

        assert response.status_code in (200, 207, 400), response.content
        surfaced = bogus in json.dumps(response.json(), default=str)
        logged = any(bogus in record.getMessage() for record in caplog.records)

        from roster.models import Student

        stored = Student.objects.filter(prn="230200924").first()
        remapped = (
            stored is not None
            and stored.department == bogus
            and not surfaced
            and not logged
        )

        assert surfaced, (
            "the upload accepted an unknown department code without naming it "
            f"in the response: {response.json()}"
        )
        assert logged, (
            "nothing was logged about the unknown code; "
            f"records: {[r.getMessage() for r in caplog.records]}"
        )
        assert not remapped


# ---------------------------------------------------------------------------
# 12. Revocation on status change
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStatusRevocation:
    """Checkbox 12."""

    @pytest.mark.parametrize("status", ["suspended", "withdrawn"])
    def test_suspending_or_withdrawing_a_student_kills_every_live_session(
        self, profiles, status
    ):
        """
        G14. "Revoked" has to mean now, not when the access token happens to
        expire. A suspended student with a 15-minute token is a suspended
        student who is still logged in, and the spec does not allow that.

        Two sessions on purpose: revoking the one that asked is not revocation.
        """
        from rest_framework.test import APIClient

        user = profiles[0].user
        sessions = []
        for _ in range(2):
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_for(user)}")
            assert client.get(reverse("auth-me")).status_code == 200
            sessions.append(client)

        setter = getattr(user, "set_status", None)
        if setter is None:
            if not hasattr(user, "status"):
                missing(
                    "User.status and a status-change path",
                    needed_for="checkbox 12 — status change revokes all sessions",
                )
            user.status = status
            user.save(update_fields=["status"])
        else:
            setter(status)

        codes = [session.get(reverse("auth-me")).status_code for session in sessions]
        assert codes == [401, 401], (
            f"after status -> {status}, live sessions answered {codes}"
        )

    def test_the_status_lifecycle_has_its_six_registrar_values(self):
        """
        G9, and not a rename of `is_placement_eligible`: that is a placement
        cell decision about participation, this is a registrar fact about
        enrolment. Both survive and neither implies the other.

        The shared spec's six are not quoted in any document in this repo, so
        this asserts the count and the three the plan names by behaviour.
        """
        status = None
        for module, name in (
            ("accounts.models", "Status"),
            ("accounts.models", "UserStatus"),
            ("core.identity", "Status"),
        ):
            try:
                import importlib

                loaded = importlib.import_module(module)
            except ImportError:
                continue
            if hasattr(loaded, name):
                status = getattr(loaded, name)
                break

        if status is None:
            missing(
                "a status lifecycle enum (accounts.models.Status)",
                needed_for="checkbox 12 / G9 — the six-value lifecycle",
            )

        values = {str(choice) for choice in status.values}
        assert len(values) == 6, f"status has {len(values)} values, not six: {sorted(values)}"
        for required in ("graduated", "withdrawn", "suspended"):
            assert required in values, f"{required!r} is not a status: {sorted(values)}"

        from accounts.models import User

        assert any(field.name == "is_placement_eligible" for field in User._meta.get_fields()) or any(
            field.name == "is_placement_eligible"
            for field in __import__("roster.models", fromlist=["Student"]).Student._meta.get_fields()
        ), "is_placement_eligible was collapsed into status; the plan says both survive"


# ---------------------------------------------------------------------------
# 13. MFA for admin roles
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminMfa:
    """Checkbox 13."""

    # Deferred until after the demo by the product owner. strict=True: the day
    # admin MFA is built this test starts passing, and the xfail turns into a
    # failure that says "remove me". Do not delete the test.
    @pytest.mark.xfail(
        strict=True,
        reason="Deferred post-demo: email OTP second factor for admins -- DECISIONS D23",
    )
    def test_an_admin_token_without_mfa_is_refused_on_admin_endpoints(self, as_admin):
        """
        G13. MFA is mandatory for admin roles, which means the `mfa` claim is
        load-bearing rather than informational: a token that says `false` must
        not reach an admin endpoint, however it was obtained.
        """
        response = as_admin.get(reverse("admin-profile-list"))

        assert response.status_code == 403, (
            "an admin token issued without MFA reached the admin profile list "
            f"(HTTP {response.status_code})"
        )

    def test_the_mfa_claim_is_present_and_false_before_a_second_factor(
        self, placement_admin
    ):
        claims = claims_in(token_for(placement_admin))

        assert "mfa" in claims, f"no mfa claim: {sorted(claims)}"
        assert claims["mfa"] is False


# ---------------------------------------------------------------------------
# 14. Identity access logging
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIdentityAccessLogging:
    """Checkbox 14."""

    def test_an_admin_reading_a_students_record_appears_in_the_audit_log(
        self, as_admin, placement_admin, profiles
    ):
        """
        G15. The binding rule: identity access beyond a user's own record is
        logged. Today only verification is -- so an admin can read every
        student's record and leave no trace, which is exactly the access a
        placement cell needs to be able to answer for.
        """
        from core.models import AuditLog

        profile = profiles[0]
        before = AuditLog.objects.count()

        response, how = fetch_detail(as_admin, reverse("admin-profile-list"), profile)
        assert response is not None, f"could not address the profile detail: {how}"

        written = AuditLog.objects.filter(actor=placement_admin).order_by("-created_at")
        assert written.count() > 0 and AuditLog.objects.count() > before, (
            "an admin read a student's identity record and nothing was logged"
        )

        trail = json.dumps(
            [{"action": row.action, "target": row.target, "detail": row.detail}
             for row in written],
            default=str,
        )
        assert profile.student.prn in trail, (
            f"the audit entry does not name the student it was about: {trail}"
        )

    def test_a_student_reading_their_own_profile_is_not_logged_as_identity_access(
        self, profiles
    ):
        """
        The rule is "beyond own record" for a reason. Logging a student's own
        reads buries the entries that matter in noise.
        """
        from core.models import AuditLog

        before = AuditLog.objects.count()

        client_for(profiles[0].user).get(reverse("my-profile"))

        assert AuditLog.objects.count() == before


# ---------------------------------------------------------------------------
# 15-16. The existing suites and the E2E
# ---------------------------------------------------------------------------


class TestExistingSuitesSurvive:
    """
    Checkboxes 15 and 16.

    A census, not a run: these count the tests that must still exist so the
    retrofit cannot go green by deleting coverage. Whether they *pass* is the
    suite's own output, recorded in `SMOKE_TESTS.md`.
    """

    BACKEND_TESTS = 249
    FRONTEND_TESTS = 43

    def test_the_backend_suite_still_holds_at_least_249_tests(self):
        result = subprocess.run(
            [str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable),
             "-m", "pytest", "--collect-only", "-q"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, f"collection failed:\n{result.stdout[-2000:]}"

        # `addopts` already carries -q, so the second one collapses the output
        # to one line per file. Sum those rather than looking for a total.
        per_file = re.findall(r"^\S+\.py:\s*(\d+)$", result.stdout, re.MULTILINE)
        assert per_file, f"could not read a test count from:\n{result.stdout[-2000:]}"

        collected = sum(int(count) for count in per_file)
        assert collected >= self.BACKEND_TESTS, (
            f"{collected} backend tests collected, down from {self.BACKEND_TESTS}"
        )

    def test_the_frontend_suite_still_holds_at_least_43_tests(self):
        sources = sorted((REPO_ROOT / "frontend" / "src").rglob("*.test.*"))
        assert sources, "no frontend test files found"

        pattern = re.compile(r"^\s*(it|test)\s*\(", re.MULTILINE)
        counted = sum(
            len(pattern.findall(path.read_text(encoding="utf-8"))) for path in sources
        )

        assert counted >= self.FRONTEND_TESTS, (
            f"{counted} frontend tests in source, down from {self.FRONTEND_TESTS}"
        )

    def test_the_phase_0_to_3_e2e_run_is_committed_and_can_be_re_run(self):
        """
        Checkbox 16 asks for the 30/30 E2E to be re-run, which needs the script
        that produced it. It was never committed -- `3919196` added only
        `SMOKE_TESTS.md`, `PROGRESS.md` and one regression test, so the 196-request
        run exists as captured output and nothing else.

        Until a harness is in the repo, this checkbox cannot be ticked by
        anybody: there is nothing to re-run, and "we ran it before" is not
        evidence the retrofit broke nothing.
        """
        candidates = [
            REPO_ROOT / "backend" / "checkpoints" / "e2e_phase_0_3.py",
            REPO_ROOT / "backend" / "scripts" / "e2e_phase_0_3.py",
            REPO_ROOT / "scripts" / "e2e.py",
            REPO_ROOT / "backend" / "e2e.py",
        ]
        # Only these exact paths count. An earlier version also accepted any
        # file named "*e2e*", and a resume upload whose random hex name
        # contained "e2e" satisfied it on one machine and not on another.
        found = [path for path in candidates if path.exists()]

        assert found, (
            "no Phase 0-3 E2E harness is committed, so the 30/30 run cannot be "
            "re-run. Looked for:\n  " + "\n  ".join(str(p) for p in candidates)
        )


# ---------------------------------------------------------------------------
# 17-18. Reconciliation: the fail-open bug
# ---------------------------------------------------------------------------

#: Every list endpoint that addresses students, with the role that may read it.
#: `?prn=` is required on all of them (§3.5), not just the roster.
PRN_LIST_ENDPOINTS = (
    ("roster-student-list", "admin"),
    ("company-profile-list", "recruiter"),
    ("admin-profile-list", "admin"),
)


@pytest.mark.django_db
class TestPrnFilterFailsOpen:
    """
    Checkbox 17 — the bug measured on 2026-09-30.

    django-filter ignores a query parameter it has not declared, so `?prn=`
    returns the whole table. A reconciliation script reading `count > 0` as
    "found" therefore matches the wrong student, for a student who is not
    there. It fails open, it fails silently, and the output looks plausible,
    which is the worst combination available.
    """

    @staticmethod
    def _client(request, who):
        return request.getfixturevalue({"admin": "as_admin", "recruiter": "as_recruiter"}[who])

    @pytest.mark.parametrize("route,who", PRN_LIST_ENDPOINTS)
    def test_a_prn_filter_returns_exactly_the_student_asked_for(
        self, request, profiles, route, who
    ):
        client = self._client(request, who)

        response = client.get(reverse(route), {"prn": "220200921"})

        assert response.status_code == 200, response.content
        rows = response.json()["results"]
        assert len(rows) == 1, (
            f"{route}?prn=220200921 returned {len(rows)} of 3 rows -- the filter "
            "is being ignored, not applied"
        )
        assert "220200921" in json.dumps(rows, default=str)

    @pytest.mark.parametrize("route,who", PRN_LIST_ENDPOINTS)
    def test_a_prn_filter_for_a_student_who_does_not_exist_returns_nothing(
        self, request, profiles, route, who
    ):
        """
        The half that does the damage. Returning three rows for a PRN that is
        on no roster row tells a reconciliation script the student was found.
        """
        client = self._client(request, who)

        response = client.get(reverse(route), {"prn": ABSENT_PRN})

        assert response.status_code == 200, response.content
        rows = response.json()["results"]
        assert rows == [], (
            f"{route}?prn={ABSENT_PRN} returned {len(rows)} rows for a PRN that "
            "exists nowhere"
        )

    @pytest.mark.parametrize("route,who", PRN_LIST_ENDPOINTS)
    def test_a_batch_prn_filter_returns_the_matches_and_names_the_misses(
        self, request, profiles, route, who
    ):
        """
        Reconciling a 400-row spreadsheet one request at a time is unusable, so
        `?prns=` exists -- and a batch that returns 380 of 400 rows must name
        the 20 it could not find. Quietly returning fewer rows than were asked
        for is the same fail-open shape as the bug above.
        """
        client = self._client(request, who)

        response = client.get(
            reverse(route), {"prns": f"220200921,220200922,{ABSENT_PRN}"}
        )

        assert response.status_code == 200, response.content
        rows = response.json()["results"]
        assert len(rows) == 2, (
            f"{route}?prns= returned {len(rows)} rows, expected the 2 that exist"
        )

        reported = body_without_results(response)
        assert ABSENT_PRN in reported, (
            "the batch lookup did not name the PRN it could not find; the "
            f"response said: {reported}"
        )

    def test_a_batch_prn_filter_is_capped(self, as_admin, profiles):
        """§3.5 caps the batch at 200. An uncapped IN clause is a denial of service."""
        response = as_admin.get(
            reverse("roster-student-list"),
            {"prns": ",".join(f"{220200920 + n:09d}" for n in range(201))},
        )

        assert response.status_code == 400, (
            f"a 201-PRN batch was accepted (HTTP {response.status_code})"
        )

    @pytest.mark.parametrize("route,who", PRN_LIST_ENDPOINTS)
    def test_a_query_parameter_nobody_declared_is_rejected_not_ignored(
        self, request, profiles, route, who
    ):
        """
        The general fix behind the specific bug. A typo'd `?pm=220200921` must
        be a 400; ignoring it and returning everything is how the filter bug
        existed at all. §3.5 makes this a global DRF setting, not a per-view fix.
        """
        client = self._client(request, who)

        response = client.get(reverse(route), {"pm": "220200921"})

        assert response.status_code == 400, (
            f"{route}?pm= (a typo) answered HTTP {response.status_code} and "
            f"returned {len(response.json().get('results', []))} rows"
        )


@pytest.mark.django_db
class TestFilterInputNormalisation:
    """
    Checkbox 18.

    `normalise_prn` runs on model save, so stored values are canonical -- but a
    filter value is never saved. A PRN pasted out of a spreadsheet arrives with
    a trailing space or a newline, and an exact `?prn=` match will not tolerate
    what `search` happens to.
    """

    @pytest.mark.parametrize(
        "typed",
        [
            "220200921",
            " 220200921",
            "220200921 ",
            "  220200921  ",
            "220200921\n",
            "\t220200921\t",
        ],
        ids=["exact", "leading", "trailing", "padded", "newline", "tabs"],
    )
    def test_a_prn_filter_value_is_trimmed_before_it_is_matched(
        self, as_admin, profiles, typed
    ):
        response = as_admin.get(reverse("roster-student-list"), {"prn": typed})

        assert response.status_code == 200, response.content
        rows = response.json()["results"]
        assert len(rows) == 1, f"?prn={typed!r} matched {len(rows)} rows, expected 1"

    def test_a_human_key_filter_value_is_upper_cased_before_it_is_matched(
        self, as_admin, placement_admin, profiles
    ):
        """
        PRN is nine digits so case cannot bite there, but `ADM-0001` and
        `CMP-0001` are mixed, and a human typing one into a search box will not
        hold shift. Write input is upper-cased; filter input takes the same path.
        """
        human_key = getattr(placement_admin, "admin_id", None)
        if not human_key:
            missing(
                "User.admin_id",
                needed_for="checkbox 18 — filter input normalised, case included",
            )

        # Moved from the roster list (which has no admin_id): the admin key is
        # filterable where it means something, on who verified a profile.
        profiles[0].mark_verified(placement_admin)

        response = as_admin.get(
            reverse("admin-profile-list"), {"verified_by": str(human_key).lower()}
        )
        assert response.status_code == 200, response.content
        rows = response.json()["results"]
        assert [row["student_id"] for row in rows] == [str(profiles[0].student_id)], (
            f"?verified_by={str(human_key).lower()!r} was not normalised to "
            f"{human_key!r}; got {rows}"
        )


# ---------------------------------------------------------------------------
# 19. A human key for every role
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRoleHumanKeys:
    """
    Checkbox 19.

    D9. The prefix is the point: an identifier in a log line, an export column
    or an audit entry should say what kind of thing it names without a lookup,
    which a bare sequence would not.
    """

    def test_every_admin_is_issued_a_sequential_adm_identifier(self):
        from accounts.models import User

        first = User.objects.create_admin(
            email="first.officer@college.edu", password="AdminPass!234",
            full_name="Priya Kulkarni",
        )
        second = User.objects.create_admin(
            email="second.officer@college.edu", password="AdminPass!234",
            full_name="Rohit Shetty",
        )

        if not hasattr(first, "admin_id"):
            missing("User.admin_id", needed_for="checkbox 19 — every admin has an ADM- id")

        assert first.admin_id == "ADM-0001", f"first admin got {first.admin_id!r}"
        assert second.admin_id == "ADM-0002", f"second admin got {second.admin_id!r}"
        assert first.admin_id != second.admin_id

    def test_every_company_is_issued_a_sequential_cmp_identifier(self):
        Company = target(
            "accounts.models", "Company",
            needed_for="checkbox 19 — every company has a CMP- id",
        )

        first = Company.objects.create(name="Acme Tech", email="careers@acmetech.example")
        second = Company.objects.create(name="Beta Labs", email="careers@betalabs.example")

        assert first.company_id == "CMP-0001", f"first company got {first.company_id!r}"
        assert second.company_id == "CMP-0002"

    def test_a_role_human_key_cannot_be_changed_once_issued(self):
        """
        Immutable, on the same terms as PRN. A human key that can be edited is
        not a key -- every export and audit line that already named it becomes
        a lie, and the same discipline the registrar applies to PRN applies here.
        """
        from accounts.models import User

        admin = User.objects.create_admin(
            email="third.officer@college.edu", password="AdminPass!234",
            full_name="Nikhil Varma",
        )
        if not hasattr(admin, "admin_id"):
            missing("User.admin_id", needed_for="checkbox 19 — immutability")

        issued = admin.admin_id
        admin.admin_id = "ADM-9999"
        try:
            admin.save()
        except Exception:
            admin.refresh_from_db()
            assert admin.admin_id == issued
            return

        admin.refresh_from_db()
        assert admin.admin_id == issued, (
            f"admin_id was changed from {issued!r} to {admin.admin_id!r}"
        )

    def test_a_role_human_key_is_unique(self):
        from django.db import IntegrityError, transaction

        from accounts.models import User

        first = User.objects.create_admin(
            email="fourth.officer@college.edu", password="AdminPass!234",
            full_name="Asha Menon",
        )
        if not hasattr(first, "admin_id"):
            missing("User.admin_id", needed_for="checkbox 19 — uniqueness")

        clash = User(
            email="fifth.officer@college.edu", role="admin", is_active=True,
            full_name="Imran Qadri", admin_id=first.admin_id,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                clash.save()


# ---------------------------------------------------------------------------
# 20-21. The company is an entity, and a recruiter acts for it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCompanyScope:
    """
    Checkboxes 20 and 21 — the second bug measured on 2026-09-30.

    `CompanyShortlist.company` is a foreign key to `User`, so a shortlist
    belongs to a recruiter rather than to a company. Two recruiters at the same
    company hold two separate shortlists -- and because "shortlisted only"
    visibility is computed from that table, a student is visible to one
    recruiter and 404s for their colleague. Invisible until a company has a
    second account, and nothing in the UI predicts it.
    """

    def test_the_shortlist_belongs_to_a_company_not_to_a_recruiter(self):
        """
        The model-level statement of the bug, which is where the fix has to
        land. Repointing this foreign key is what makes checkbox 20 reachable;
        anything else is per-recruiter state wearing a company's name.
        """
        from profiles.models import CompanyShortlist

        related = CompanyShortlist._meta.get_field("company").related_model

        assert related._meta.model_name == "company", (
            f"CompanyShortlist.company points at {related._meta.label}, so a "
            "shortlist still belongs to one login rather than to the organisation"
        )

    def test_two_recruiters_at_one_company_share_one_shortlist(
        self, profiles, recruiter, second_recruiter, as_recruiter, as_second_recruiter
    ):
        """
        The bug, end to end, from the student's side: they set "shortlisted
        only" believing they are visible to the company that shortlisted them.
        Half that company cannot see them.
        """
        Company = target(
            "accounts.models", "Company",
            needed_for="checkbox 20 — two recruiters at one company share one shortlist",
        )

        company = Company.objects.create(name="Acme Tech", email="careers@acmetech.example")
        for user in (recruiter, second_recruiter):
            if not hasattr(user, "company"):
                missing(
                    "User.company (a recruiter belonging to a Company)",
                    needed_for="checkbox 20",
                )
            user.company = company
            user.save(update_fields=["company"])

        profile = profiles[0]
        list_url = reverse("company-profile-list")

        shortlisted = as_recruiter.post(
            detail_url(list_url, profile.student.prn) + "/shortlist", {}, format="json"
        )
        if shortlisted.status_code not in (200, 201):
            response, how = fetch_detail(as_recruiter, list_url, profile)
            assert response is not None, f"recruiter cannot address the profile: {how}"
            shortlisted = as_recruiter.post(
                detail_url(list_url, how) + "/shortlist", {}, format="json"
            )
        assert shortlisted.status_code in (200, 201), shortlisted.content

        from profiles.models import Visibility

        profile.visibility = Visibility.SHORTLISTED
        profile.save(update_fields=["visibility", "updated_at"])

        colleague = as_second_recruiter.get(list_url, {"prn": profile.student.prn})
        assert colleague.status_code == 200, colleague.content
        rows = colleague.json()["results"]
        assert len(rows) == 1, (
            "a student on 'shortlisted only' is invisible to the second recruiter "
            "at the company that shortlisted them -- the shortlist is still "
            "per-login"
        )

    def test_a_recruiters_token_names_the_company_it_acts_for(self, recruiter):
        """
        Checkbox 21. The spec's §4.3 `<role>:<scope_uuid>` pattern, so no new
        claim is needed -- but the scope has to be *there*, and it has to be the
        company's UUID rather than its name or its CMP- key.
        """
        Company = target(
            "accounts.models", "Company",
            needed_for="checkbox 21 — company_recruiter:<company_uuid>",
        )
        company = Company.objects.create(name="Acme Tech", email="careers@acmetech.example")
        if not hasattr(recruiter, "company"):
            missing("User.company", needed_for="checkbox 21")
        recruiter.company = company
        recruiter.save(update_fields=["company"])

        roles = claims_in(token_for(recruiter)).get("roles")
        assert isinstance(roles, list), f"recruiter token has no roles array: {roles!r}"

        scoped = [role for role in roles if role.startswith("company_recruiter:")]
        assert scoped, f"no company_recruiter scope in {roles!r}"
        assert len(scoped) == 1, f"a recruiter acts for one company, got {scoped!r}"

        scope = scoped[0].split(":", 1)[1]
        assert uuid.UUID(scope) == company.id, (
            f"the scope is {scope!r}, not the company's UUID {company.id}"
        )

    def test_a_recruiter_cannot_reach_another_companys_shortlist(
        self, profiles, recruiter, second_recruiter, as_recruiter, as_second_recruiter
    ):
        """
        Checkbox 21's other half: per §4.4 the scope is checked server-side. A
        token carrying `company_recruiter:<uuid>` authorises nothing by itself,
        so a recruiter at company B must not be able to undo company A's
        shortlist -- and the test only means something once two recruiters at
        one company *do* share, or it would pass by accident.
        """
        Company = target(
            "accounts.models", "Company",
            needed_for="checkbox 21 — scope checked server-side",
        )
        acme = Company.objects.create(name="Acme Tech", email="careers@acmetech.example")
        beta = Company.objects.create(name="Beta Labs", email="careers@betalabs.example")
        if not hasattr(recruiter, "company"):
            missing("User.company", needed_for="checkbox 21")
        recruiter.company = acme
        recruiter.save(update_fields=["company"])
        second_recruiter.company = beta
        second_recruiter.save(update_fields=["company"])

        profile = profiles[0]
        shortlist_url = (
            detail_url(reverse("company-profile-list"), profile.student_id) + "/shortlist"
        )

        assert as_recruiter.post(shortlist_url, {}, format="json").status_code in (200, 201)

        from profiles.models import CompanyShortlist

        removed = as_second_recruiter.delete(shortlist_url)
        assert removed.status_code in (204, 403, 404)
        assert CompanyShortlist.objects.filter(company=acme).exists(), (
            "a recruiter at Beta Labs deleted Acme Tech's shortlist entry"
        )
