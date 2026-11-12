"""
Token signing keys, the claim contract, and multi-key verification.

Three things live here, and they are together because they are the seam that
lets this portal switch from issuing its own tokens to accepting the
platform's without any code downstream changing.

**Keys.** RS256, not a shared secret. The portal publishes a JWKS so anything
holding a token can verify it without being given a key, which is what makes
key rotation possible at all -- during a rotation two pairs are live and
tokens signed by either must authenticate.

**Claims.** `build_claims` produces the shared spec's §5.4 set, exactly. Every
key present in every mode; optional values are `null`, never omitted. That rule
is load-bearing: a consumer reading `claims["prn"]` must not KeyError on a
staff token, and the alternative shape makes every reader defensive.

**Verification.** `MultiKeyTokenBackend` resolves the signing key by the
token's `kid` header rather than holding one key. Platform mode is then a
configuration change -- point `IDENTITY["JWKS_URL"]` at the platform and the
same code path verifies its tokens.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import TokenBackendError

logger = logging.getLogger(__name__)


# --- keys -------------------------------------------------------------------


def _generate_keypair() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private, public


@lru_cache(maxsize=1)
def keyring() -> dict:
    """
    The live signing keys: `{"active": kid, "keys": {kid: {private, public}}}`.

    Configured keys win. With none configured a development pair is generated
    and written to `IDENTITY["DEV_KEY_DIR"]`, because regenerating on every
    reload would invalidate every token a developer is holding. Those files are
    gitignored and must never be used anywhere real -- a key in the repo is not
    a key.
    """
    configured = settings.IDENTITY.get("KEYS") or {}
    if configured:
        active = settings.IDENTITY.get("ACTIVE_KID") or next(iter(configured))
        if active not in configured:
            raise RuntimeError(
                f"IDENTITY['ACTIVE_KID'] is {active!r}, which is not among the "
                f"configured keys: {sorted(configured)}"
            )
        return {"active": active, "keys": dict(configured)}

    key_dir = Path(settings.IDENTITY["DEV_KEY_DIR"])
    key_dir.mkdir(parents=True, exist_ok=True)
    private_path, public_path = key_dir / "dev-signing.pem", key_dir / "dev-signing.pub"

    if private_path.exists() and public_path.exists():
        private, public = private_path.read_text(), public_path.read_text()
    else:
        private, public = _generate_keypair()
        private_path.write_text(private)
        private_path.chmod(0o600)
        public_path.write_text(public)
        logger.warning(
            "No signing keys configured; generated a development pair in %s. "
            "Set IDENTITY['KEYS'] before deploying anywhere.",
            key_dir,
        )

    kid = "dev-1"
    return {"active": kid, "keys": {kid: {"private": private, "public": public}}}


def active_kid() -> str:
    return keyring()["active"]


def private_key(kid: str | None = None) -> str:
    ring = keyring()
    return ring["keys"][kid or ring["active"]]["private"]


def public_key(kid: str) -> str | None:
    entry = keyring()["keys"].get(kid)
    return entry["public"] if entry else None


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwks() -> dict:
    """Every public key, as a JWKS. Both halves of a rotation appear here."""
    from cryptography.hazmat.primitives import serialization

    keys = []
    for kid, pair in keyring()["keys"].items():
        numbers = serialization.load_pem_public_key(
            pair["public"].encode()
        ).public_numbers()
        keys.append(
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": kid,
                "n": _b64(numbers.n),
                "e": _b64(numbers.e),
            }
        )
    return {"keys": keys}


# --- the claim contract -----------------------------------------------------

#: The shared spec's §5.4 set. Every key appears on every token.
CLAIM_CONTRACT = (
    "sub",
    "iss",
    "aud",
    "iat",
    "exp",
    "email",
    "student_id",
    "prn",
    "display_name",
    "roles",
    "department",
    "programme",
    "year",
    "mfa",
)

#: Institution-wide role names, `lower_snake_case` per §4.3. A role scoped to
#: one object carries a `:<uuid>` suffix, as in `company_recruiter:<uuid>`.
ROLE_STUDENT = "student"
ROLE_PLACEMENT_ADMIN = "placement_admin"
ROLE_COMPANY_RECRUITER = "company_recruiter"


def roles_for(user) -> list[str]:
    """
    The `roles` array. Plural and a list, always.

    A single role string is the shape that makes `company_recruiter:<uuid>`
    impossible to express, so this is not merely tidier.
    """
    from accounts.models import Role

    if user.role == Role.ADMIN:
        roles = [ROLE_PLACEMENT_ADMIN]
        if user.is_superuser:
            roles.append("it_admin")
        return roles

    if user.role == Role.COMPANY:
        # Scope is carried in the role, so no new claim is needed. The spec's
        # §4.4 still applies: this authorises nothing on its own, and the
        # portal checks the recruiter's company owns the resource.
        company_id = getattr(user, "company_id", None)
        return [f"{ROLE_COMPANY_RECRUITER}:{company_id}" if company_id else ROLE_COMPANY_RECRUITER]

    return [ROLE_STUDENT]


def _student_record(user):
    """The roster row behind a student account, or None for staff."""
    from roster.models import Student

    if not user.prn:
        return None
    return Student.objects.filter(prn=user.prn).first()


def build_claims(user, *, mfa: bool = False) -> dict:
    """
    The §5.4 claim set for one user.

    Carries name, PRN, department, programme and year precisely so that
    rendering a page does not require a call back for basic identity. A
    directory lookup happens only when something beyond these is needed.
    """
    student = _student_record(user)

    return {
        "sub": str(user.id),
        "iss": settings.IDENTITY["ISSUER"],
        "aud": list(settings.IDENTITY["AUDIENCE"]),
        "email": user.email,
        "student_id": str(student.id) if student else None,
        "prn": user.prn or None,
        # full_name is deliberately absent: display_name covers rendering, and
        # the official name is fetched only where it is legally needed.
        "display_name": user.display_name,
        "roles": roles_for(user),
        "department": getattr(student, "department", None) or None,
        "programme": getattr(student, "programme", None) or None,
        "year": getattr(student, "year_of_study", None),
        # Whether THIS session was MFA-verified, so a sensitive operation can
        # require it independently of role.
        "mfa": bool(mfa),
    }


# --- verification -----------------------------------------------------------


class MultiKeyTokenBackend(TokenBackend):
    """
    Resolve the verifying key by the token's `kid`.

    SimpleJWT holds a single verifying key, which cannot survive a rotation:
    the moment a second pair starts signing, tokens from the first stop
    validating. Resolving per token is what makes the published JWKS mean
    anything.
    """

    def encode(self, payload):
        """
        Sign with the active key, naming it in the `kid` header.

        Reimplemented rather than delegated because the parent offers no way to
        set a header, and without a `kid` a verifier holding several published
        keys has to try each one.
        """
        import jwt as pyjwt

        jwt_payload = payload.copy()
        if self.audience is not None:
            jwt_payload["aud"] = self.audience
        if self.issuer is not None:
            jwt_payload["iss"] = self.issuer

        return pyjwt.encode(
            jwt_payload,
            private_key(),
            algorithm=self.algorithm,
            headers={"kid": active_kid()},
            json_encoder=self.json_encoder,
        )

    def decode(self, token, verify=True):
        if not verify:
            return super().decode(token, verify=False)

        import jwt as pyjwt

        try:
            kid = pyjwt.get_unverified_header(token).get("kid")
        except pyjwt.PyJWTError as exc:
            raise TokenBackendError(f"Token header is unreadable: {exc}") from exc

        key = public_key(kid) if kid else None
        if key is None:
            raise TokenBackendError(
                f"No published key matches kid {kid!r}. Published: "
                f"{sorted(keyring()['keys'])}"
            )
        self.verifying_key = key
        return super().decode(token, verify=True)


def reset_keyring() -> None:
    """Drop the cached keyring. For tests that install their own keys."""
    keyring.cache_clear()
