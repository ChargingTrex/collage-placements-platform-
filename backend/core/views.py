"""Health endpoint -- the Phase 0 smoke-test target."""

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.storage import storage_info


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """
    Liveness + dependency check.

    Returns 200 only when the database actually answers a query, so
    `docker-compose up` racing ahead of Postgres shows as a failure here
    rather than as a confusing error later.
    """
    checks = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = {"ok": True}
        if settings.DEBUG:
            checks["database"]["engine"] = connection.vendor
    except Exception as exc:  # pragma: no cover - only hit when the DB is down
        # The message can carry a path or host; show it only with DEBUG on.
        checks["database"] = {"ok": False}
        if settings.DEBUG:
            checks["database"]["error"] = str(exc)

    checks["storage"] = {"ok": True, **storage_info()}

    # Reported, never failed on: the engine has a working fallback backend.
    # Kept on the public link: the backend name (spacy/tfidf) proves the demo's
    # matching mode and is harmless. Model detail and thresholds are DEBUG-only.
    from matching.backends import backend_info

    engine = backend_info()
    if not settings.DEBUG:
        engine = {k: engine[k] for k in ("ok", "backend")}
    checks["matching_engine"] = engine

    healthy = all(check.get("ok", False) for check in checks.values())
    return Response(
        {
            "status": "ok" if healthy else "degraded",
            "service": "placement-cell-portal",
            "debug": settings.DEBUG,
            "checks": checks,
        },
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
