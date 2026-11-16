"""
One-click demo sign-in, for a laptop demo only (WEEKEND_DEMO_PLAN D-W3, P5).

    GET  /api/auth/demo/personas   the persona buttons the login page shows
    POST /api/auth/demo/login      {"persona": "<key>"} -> the normal login payload

Both answer 404 unless the server runs with DEBUG *and* DEMO_MODE, checked on
every request, so the public link (DEBUG off) behaves as if the routes did not
exist. A persona names one account `seed_demo` creates, looked up by its fixed
seeded identifier and role; nothing in the request can point it at any other
account. The tokens are the ones a password login issues -- no extra claim
marks a demo session, because the shared identity contract allows none.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.http import Http404
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role, User
from core import demo_accounts


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    description: str
    role: str
    #: Email for admins and recruiters, PRN for the student: what they would
    #: type at the login screen.
    identifier: str

    def account(self) -> User | None:
        """The seeded account, if it exists and may sign in; else None."""
        lookup = {"prn": self.identifier} if self.role == Role.STUDENT else {
            "email": self.identifier
        }
        user = User.objects.filter(role=self.role, **lookup).first()
        return user if user is not None and user.may_log_in else None


PERSONAS: tuple[Persona, ...] = (
    Persona(
        key="student",
        label="Student",
        description="A final-year student with a complete, verified profile.",
        role=Role.STUDENT,
        identifier=demo_accounts.DEMO_STUDENT_PRN,
    ),
    Persona(
        key="officer",
        label="Placement officer",
        description="The pilot placement-cell login: roster, profiles, all users.",
        role=Role.ADMIN,
        identifier=demo_accounts.PILOT_OFFICER_EMAIL,
    ),
    Persona(
        key="acme",
        label="Acme Tech recruiter",
        description="Recruiter who has shortlisted a student.",
        role=Role.COMPANY,
        identifier=demo_accounts.COMPANIES[0][2],
    ),
    Persona(
        key="nimbus",
        label="Nimbus Analytics recruiter",
        description="Recruiter at a second company, with its own shortlist.",
        role=Role.COMPANY,
        identifier=demo_accounts.COMPANIES[1][2],
    ),
)
PERSONAS_BY_KEY = {persona.key: persona for persona in PERSONAS}


def demo_mode_enabled() -> bool:
    # Both, at request time. DEMO_MODE is already forced off when DEBUG is off
    # at startup; checking DEBUG again means no later override can open it.
    return bool(settings.DEBUG and getattr(settings, "DEMO_MODE", False))


def _require_demo_mode() -> None:
    if not demo_mode_enabled():
        raise Http404()


class DemoLoginSerializer(serializers.Serializer):
    persona = serializers.CharField(max_length=32)


class DemoPersonasView(APIView):
    """The personas whose seeded account exists and may sign in right now."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        _require_demo_mode()
        available = [persona for persona in PERSONAS if persona.account() is not None]
        return Response(
            {
                "personas": [
                    {
                        "key": persona.key,
                        "label": persona.label,
                        "description": persona.description,
                        "role": persona.role,
                        "identifier": persona.identifier,
                    }
                    for persona in available
                ]
            }
        )


class DemoLoginView(APIView):
    """Sign in as a seeded persona without a password."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from accounts.views import signed_in

        _require_demo_mode()
        serializer = DemoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        persona = PERSONAS_BY_KEY.get(serializer.validated_data["persona"].strip().lower())
        user = persona.account() if persona else None
        if user is None:
            # Unknown persona, or its seeded account is missing or barred:
            # the same answer either way.
            raise Http404("No such demo persona.")
        return Response(signed_in(user))
