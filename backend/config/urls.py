from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/roster/", include("roster.urls")),
    path("api/profiles/", include("profiles.urls")),
    path("api/matching/", include("matching.urls")),
]

# MEDIA_ROOT is deliberately NOT served, not even in DEBUG. Resumes and
# transcripts live under paths keyed on PRN, so a /media/ route would let anyone
# fetch them by guessing. They are served only by the audited API views in
# profiles/views.py (DECISIONS D25).
