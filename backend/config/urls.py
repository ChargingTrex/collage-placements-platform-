from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/roster/", include("roster.urls")),
    path("api/profiles/", include("profiles.urls")),
    path("api/matching/", include("matching.urls")),
    path("api/opportunities/", include("opportunities.urls")),
    path("api/notifications/", include("notifications.urls")),
]

# The admin site is served only when settings.ADMIN_ENABLED (default: DEBUG),
# so the public demo link has no login form for it. Tests that flip the setting
# must reload this module (see core/tests/test_hosting_security.py).
if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("django-admin/", admin.site.urls))

# MEDIA_ROOT is deliberately NOT served, not even in DEBUG. Resumes and
# transcripts live under paths keyed on PRN, so a /media/ route would let anyone
# fetch them by guessing. They are served only by the audited API views in
# profiles/views.py (DECISIONS D25).
