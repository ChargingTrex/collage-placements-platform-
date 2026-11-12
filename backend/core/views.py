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
        checks["database"] = {"ok": True, "engine": connection.vendor}
    except Exception as exc:  # pragma: no cover - only hit when the DB is down
        checks["database"] = {"ok": False, "error": str(exc)}

    checks["storage"] = {"ok": True, **storage_info()}

    # Reported, never failed on: the engine has a working fallback backend.
    from matching.backends import backend_info

    checks["matching_engine"] = backend_info()

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
