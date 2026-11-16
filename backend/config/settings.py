"""
Django settings for the Placement Cell Portal.

Environment-driven so the same code runs on SQLite (default local dev) and
PostgreSQL (docker-compose / deployment) with no code change -- see .env.example
at the repo root for every variable this file reads.
"""

from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

# .env lives at the repo root so backend and docker-compose share one file.
load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

# Long enough to satisfy HS256 key-length guidance; still replace it in any
# real deployment (DJANGO_SECRET_KEY).
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me-before-deploying-anywhere"
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,backend")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    # Local
    "core",
    "accounts",
    "roster",
    "profiles",
    "matching",
    "opportunities",
    "notifications",
    "certifications",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
# DATABASE_URL unset -> SQLite, so a clean clone runs with zero setup.
# docker-compose sets postgres://... and nothing else changes.

DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}

# --- Auth -------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / static ----------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- File storage -----------------------------------------------------------
# Local filesystem in dev; flipping STORAGE_BACKEND=s3 swaps in an
# S3-compatible bucket with no code change (see core/storage.py).

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()

if STORAGE_BACKEND == "s3":
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or None
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True  # resumes are private: signed URLs only
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# Max upload size for resumes / certification proofs, in bytes.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))

# --- Email (OTP delivery) ---------------------------------------------------
# Console backend by default: OTPs land in the server log, so signup can be
# exercised with no SMTP credentials.

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "placements@college.edu")

# --- Placement portal settings ---------------------------------------------

PLACEMENT = {
    # Only these email domains may be used for student signup.
    "ALLOWED_STUDENT_EMAIL_DOMAINS": env_list(
        "ALLOWED_STUDENT_EMAIL_DOMAINS", "college.edu"
    ),
    "OTP_LENGTH": int(os.getenv("OTP_LENGTH", 6)),
    "OTP_TTL_MINUTES": int(os.getenv("OTP_TTL_MINUTES", 10)),
    "OTP_MAX_ATTEMPTS": int(os.getenv("OTP_MAX_ATTEMPTS", 5)),
    # Rate limiting on OTP requests (Phase 1 abuse protection).
    "OTP_REQUESTS_PER_WINDOW": int(os.getenv("OTP_REQUESTS_PER_WINDOW", 3)),
    "OTP_RATE_WINDOW_MINUTES": int(os.getenv("OTP_RATE_WINDOW_MINUTES", 15)),
    # Echo the OTP in the API response. DEBUG-only convenience so the
    # frontend prototype can be driven without reading the server console.
    "EXPOSE_OTP_IN_RESPONSE": env_bool("EXPOSE_OTP_IN_RESPONSE", DEBUG),
}


def demo_mode_from(debug: bool, requested: bool) -> bool:
    """
    One-click demo sign-in is allowed only on a DEBUG server.

    The public link runs with DEBUG off, and a stray `DEMO_MODE=true` in its
    environment must not hand out sessions without a password, so the request
    is ignored there rather than trusted.
    """
    return bool(debug and requested)


# Persona buttons on the login page and POST /api/auth/demo/login. Defaults
# to DEBUG, and is forced off whenever DEBUG is off (WEEKEND_DEMO_PLAN D-W3).
DEMO_MODE = demo_mode_from(DEBUG, env_bool("DEMO_MODE", DEBUG))

# --- Matching engine (Phase 2) ---------------------------------------------

MATCHING = {
    # "auto" -> spaCy when the model is installed, else TF-IDF.
    "BACKEND": os.getenv("MATCHING_BACKEND", "auto").strip().lower(),
    "SPACY_MODEL": os.getenv("SPACY_MODEL", "en_core_web_md"),
    # Unset -> each backend's own suggested threshold, because spaCy vector
    # cosine and TF-IDF cosine do not share a scale. Set it to pin one value.
    "DEFAULT_SIMILARITY_THRESHOLD": (
        float(os.environ["DEFAULT_SIMILARITY_THRESHOLD"])
        if os.getenv("DEFAULT_SIMILARITY_THRESHOLD")
        else None
    ),
}

# --- Resume intelligence: a Llama the college runs itself --------------------
# Ollama's OpenAI-compatible API, locally in development and on a private
# server in production. Never a third-party API: resumes do not leave the
# college (RESUME_INTELLIGENCE_PLAN.md §2). Off by default, so a clean clone
# and CI run on regex alone.

LLM = {
    "ENABLED": env_bool("LLM_ENABLED", False),
    "BASE_URL": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
    "MODEL": os.getenv("LLM_MODEL", "llama3.1:8b"),
    "EMBED_MODEL": os.getenv("EMBED_MODEL", "nomic-embed-text"),
    "TIMEOUT_SECONDS": float(os.getenv("LLM_TIMEOUT_SECONDS", 60)),
    # Sent as `reasoning_effort` only when set. "none" turns a thinking
    # model's reasoning off (gemma4: about half the time per resume on CPU).
    "REASONING_EFFORT": os.getenv("LLM_REASONING_EFFORT", "").strip(),
}

# Profile vectors: MongoDB `$vectorSearch` when MONGO_URI is set and up,
# otherwise a local table with numpy cosine. MongoDB holds an id, the
# vector and filter metadata -- never resume text or contact details.
VECTOR_STORE = {
    "BACKEND": os.getenv("VECTOR_STORE_BACKEND", "auto").strip().lower(),
    "MONGO_URI": os.getenv("MONGO_URI", ""),
    "DB": os.getenv("MONGO_DB", "placement"),
    "COLLECTION": os.getenv("MONGO_VECTOR_COLLECTION", "profile_vectors"),
    "INDEX": os.getenv("MONGO_VECTOR_INDEX", "profile_vector_index"),
}

# The skill graph (matching/skills.py). An unknown skill name at least this
# close, by embedding cosine, to a canonical skill becomes a *pending* alias
# suggestion for an admin. Never merged automatically. The scale is the
# embedding model's, so retune it when EMBED_MODEL changes.
#
# Measured on nomic-embed-text (2026-11-16, SMOKE_TESTS.md V5): 24 real
# aliases a resume might write ("Postgres DB", "Tensorflow 2") and 44 names
# that are not aliases ("SQL Server", "Angular momentum", "Embedded C"),
# each against its nearest canonical skill:
#
#     threshold   right suggestions (of 24)   wrong suggestions
#     0.70        17                          6
#     0.74        16                          3
#     0.78        14                          1   <- chosen
#     0.80        11                          1
#     0.85         5                          1   (the old provisional value)
#
# The one wrong suggestion left is "SQL Server" -> SQL (0.866); short names
# with a version or suffix ("ReactJS 18" 0.566, "Golang 1.21" 0.549) stay
# below any usable threshold. A suggestion is only pending, for an admin.
SKILL_GRAPH = {
    "ALIAS_SUGGESTION_THRESHOLD": float(os.getenv("SKILL_ALIAS_SUGGESTION_THRESHOLD", 0.78)),
}

# `POST /api/profiles/me/resume/analyze` runs inside the request, so the
# whole run (model reply, a retry, the embedding) shares one budget, kept
# below the server's request timeout. Past it the reading falls back to
# regex and says it can be retried; `manage.py analyze_resumes` backfills.
RESUME_ANALYSIS = {
    "TIME_BUDGET_SECONDS": float(os.getenv("RESUME_ANALYSIS_TIME_BUDGET_SECONDS", 25)),
}

# The 0-100 match against a job description (`engine.match_score`). Each
# similarity source has its own scale, so each raw score is mapped onto 0-1
# by its own FLOOR (-> 0) and CEILING (-> 1) before it is weighted.
#
# spaCy and TF-IDF were measured on the five samples in matching/samples.py
# against SAMPLE_JOB_DESCRIPTION (2026-10-19), relevant ones marked *:
#
#     sample                spacy    tfidf
#     backend_engineer *    0.964    0.237
#     data_engineer *       0.926    0.102
#     frontend_intern       0.847    0.018
#     mechanical_designer   0.836    0.048
#     marketing_executive   0.801    0.014
#
# spaCy's averaged word vectors put even unrelated English near 0.8, so its
# floor sits at the least relevant sample; TF-IDF shares almost no terms
# with an unrelated resume, so its floor is 0. Each ceiling sits just above
# the best sample. Retune all of them when the model changes.
#
# nomic-embed-text was measured the same way (2026-11-16, SMOKE_TESTS.md V5),
# on all ten samples, and on the stored profile documents (form + resume
# text, what search actually scores) of the five Phase 2 students:
#
#     sample                  raw text   profile document
#     backend_engineer *      0.836      0.876
#     data_engineer *         0.733      0.714
#     frontend_intern         0.630      0.628
#     mechanical_designer     0.565      0.606
#     biotech_masters         0.551
#     electronics_dated       0.544
#     civil_fresher           0.537
#     designer_short_dates    0.531
#     operations_multi_job    0.530
#     marketing_executive     0.509      0.623 (form says Python, Java)
#
# nomic puts unrelated English near 0.5, so the floor is the least relevant
# sample (0.50); the ceiling sits just above the best profile (0.88).
#
# The live run (plan §5.4, main 2ed4fe1) measured the same raw-text column.
MATCH_SCORE = {
    # "certifications" is a slot for Phase C (certifications held). It stays 0
    # until that phase exists: the engine scores only the parts it computes,
    # so a zero weight changes nothing (DECISIONS D28).
    "WEIGHTS": {
        "semantic": 0.45, "skills": 0.35, "experience": 0.10, "education": 0.10,
        "certifications": 0.0,
    },
    "CALIBRATION": {
        "embedding": {
            "FLOOR": float(os.getenv("MATCH_EMBEDDING_FLOOR", 0.50)),
            "CEILING": float(os.getenv("MATCH_EMBEDDING_CEILING", 0.88)),
        },
        "spacy": {"FLOOR": 0.80, "CEILING": 0.97},
        "tfidf": {"FLOOR": 0.00, "CEILING": 0.25},
    },
    # With no embedder, /api/matching/search scores visible profiles one by
    # one on the similarity backend; this caps how many.
    "FALLBACK_MAX_PROFILES": int(os.getenv("MATCH_FALLBACK_MAX_PROFILES", 500)),
    # Inside a live JD search, the chat model's reading of a JD it has not
    # read before gets only this long (the embedding goes first, on the full
    # analysis budget). A CPU model takes a minute, so a miss falls back to
    # the text reading at once and the search still ranks on vectors. Read
    # demo JDs ahead with `manage.py read_jd`: a cached reading costs nothing.
    "JD_READING_BUDGET_SECONDS": float(os.getenv("JD_READING_BUDGET_SECONDS", 3)),
}

# --- Cache ------------------------------------------------------------------
# What the cache holds: JD readings (a day), the "this JD fed a category"
# markers, and the API throttle counters.
#   locmem (default)  per process: lost on restart, not shared by workers
#   file              FileBasedCache at CACHE_LOCATION: survives restarts and
#                     is shared by every gunicorn worker on the machine, so a
#                     JD pre-read with `manage.py read_jd` is a hit for all
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "locmem").strip().lower()
if CACHE_BACKEND == "locmem":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
elif CACHE_BACKEND == "file":
    # A relative CACHE_LOCATION is under backend/, not the working directory:
    # `read_jd` and gunicorn started in different folders must share one cache.
    CACHE_LOCATION = BASE_DIR / Path(os.getenv("CACHE_LOCATION", ".cache")).expanduser()
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": str(CACHE_LOCATION),
            "OPTIONS": {"MAX_ENTRIES": 10_000},
        }
    }
else:
    raise ImproperlyConfigured(f"Unknown CACHE_BACKEND '{CACHE_BACKEND}'. Use locmem or file.")

# How long a JD's model reading stays cached (default a day). A JD read the
# evening before a demo needs more: `read_jd --ttl` sets it per reading.
JD_CACHE_SECONDS = int(os.getenv("JD_CACHE_SECONDS", 60 * 60 * 24))

# Phase B / Addendum 2. SUGGESTIONS.MIN_SCORE is on the calibrated 0-100
# match score, so one figure means the same on spaCy, TF-IDF and embeddings
# (a raw similarity cut would not). OPPORTUNITIES.DEADLINE_NOTICE_DAYS is how
# far ahead `notify_deadlines` warns eligible students who have not applied.
SUGGESTIONS = {
    "MIN_SCORE": int(os.getenv("SUGGESTIONS_MIN_SCORE", 50)),
    "MAX_RESULTS": int(os.getenv("SUGGESTIONS_MAX_RESULTS", 20)),
}
OPPORTUNITIES = {
    "DEADLINE_NOTICE_DAYS": int(os.getenv("OPPORTUNITY_DEADLINE_NOTICE_DAYS", 3)),
    # Cap on rows in one contact export: a shortlist is small, and the zip is
    # returned inline as base64.
    "EXPORT_MAX_ROWS": int(os.getenv("SHORTLIST_EXPORT_MAX_ROWS", 500)),
}

# Role categories learnt from recruiters' JDs (matching/categories.py).
# MERGE_THRESHOLD is a raw embedding cosine between a JD and a same-titled
# category's centroid: below it the JD starts a variant for an admin to
# review. A profile gets at most MAX_PER_PROFILE categories, each with a
# fit (CENTROID_WEIGHT x calibrated centroid cosine + the rest x weighted
# skill overlap) of at least MIN_FIT.
#
# Both measured on nomic-embed-text (2026-11-16, SMOKE_TESTS.md V5) with 18
# synthetic JDs over 9 roles, including same-titled JDs for different work
# ("Software Engineer": backend, Android, firmware; "Analyst": data, finance).
#
# MERGE_THRESHOLD only judges JDs that share a title or role name:
#
#     pair                                     cosine
#     same role, JD vs JD                      0.701 - 0.891
#     same title, different work, JD vs JD     0.665 - 0.728
#     JD vs its own role's centroid (others)   >= 0.788
#     JD vs any other role's centroid          <= 0.771
#
# Single JDs overlap, so no value is clean. 0.75 splits every different-work
# pair (margin 0.022) and splits 7 of 20 same-role pairs (different stacks:
# Java vs Python backends) into variants an admin merges. A wrong split costs
# an admin one merge; a wrong merge mixes two roles silently.
#
# MIN_FIT, five profiles against the categories those JDs make:
#
#     right roles (backend->Backend, data->Data Analyst, ...)   0.72 - 0.95
#     doubtful: backend->Data Analyst 0.51, data->Financial Analyst 0.49
#     wrong: marketing->Data Analyst 0.38, frontend->Backend (2) 0.31
#
# 0.45 drops every wrong one with room; 0.40 dropped the 0.38 by only 0.02.
# It keeps data->Financial Analyst (0.49), a weak but not absurd suggestion.
CATEGORY = {
    "MERGE_THRESHOLD": float(os.getenv("CATEGORY_MERGE_THRESHOLD", 0.75)),
    "MIN_FIT": float(os.getenv("CATEGORY_MIN_FIT", 0.45)),
    "MAX_PER_PROFILE": int(os.getenv("CATEGORY_MAX_PER_PROFILE", 3)),
    "CENTROID_WEIGHT": float(os.getenv("CATEGORY_CENTROID_WEIGHT", 0.5)),
}

# --- DRF / JWT --------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        # First: a query parameter this endpoint does not understand is a 400,
        # never a silently ignored filter that returns the whole table.
        "core.filters.RejectUnknownQueryParams",
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_RATES": {
        "otp": os.getenv("OTP_THROTTLE_RATE", "10/hour"),
        "anon": os.getenv("ANON_THROTTLE_RATE", "60/hour"),
        # Per user, on every endpoint that may call the LLM or score a pool.
        "matching": os.getenv("MATCHING_THROTTLE_RATE", "30/hour"),
        # Per user, on the shortlist exports (CV zip, contact zip).
        "export": os.getenv("EXPORT_THROTTLE_RATE", "20/hour"),
    },
}

# --- Identity: signing keys and the claim contract --------------------------
# The seam the portal switches on. Standalone mode signs with its own keys and
# publishes a JWKS; platform mode points JWKS_URL at the platform and nothing
# downstream of claim-reading changes.

IDENTITY = {
    # The one PRN rule (nine digits). roster.models.PRN_VALIDATOR reads it at
    # call time; override with the PRN_REGEX env var if the registrar changes it.
    "PRN_REGEX": os.getenv("PRN_REGEX", r"^[0-9]{9}$"),
    "ISSUER": os.getenv("JWT_ISSUER", "https://placements.saiuniversity.edu.in"),
    "AUDIENCE": env_list("JWT_AUDIENCE", "placements"),
    # {kid: {"private": pem, "public": pem}}. Empty in development, where a
    # pair is generated into DEV_KEY_DIR on first use.
    "KEYS": {},
    "ACTIVE_KID": os.getenv("JWT_ACTIVE_KID", ""),
    "DEV_KEY_DIR": Path(os.getenv("DEV_KEY_DIR", BASE_DIR / ".keys")),
    # Platform mode, not yet used: verify against the platform's JWKS instead
    # of the portal's own keyring.
    "JWKS_URL": os.getenv("PLATFORM_JWKS_URL", ""),
}

SIMPLE_JWT = {
    # 15 minutes, per the shared spec §5.3. Short enough that a leaked token
    # expires before it is useful.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", 15))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", 7))),
    "ROTATE_REFRESH_TOKENS": True,
    # Reuse of a consumed refresh token revokes the family. Without this,
    # rotation is theatre: a stolen refresh token keeps working alongside the
    # legitimate one and nothing notices.
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "RS256",
    "ISSUER": os.getenv("JWT_ISSUER", "https://placements.saiuniversity.edu.in"),
    "AUDIENCE": env_list("JWT_AUDIENCE", "placements"),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --- CORS -------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

# --- Preliminary verification (admin-only flags) -----------------------------
# Resume vs form vs roster. Flags never block anything; an admin decides.
# Two CGPAs (roster, transcript, resume) further apart than this are flagged.
VERIFICATION = {
    "CGPA_TOLERANCE": float(os.getenv("VERIFICATION_CGPA_TOLERANCE", 0.1)),
}

# === HOSTING: public demo link (Netlify -> tunnel -> gunicorn) =================
# Everything the hosted demo needs, in one place. scripts/serve_demo.sh sets the
# env vars; with none of them set, local development is unchanged.
#
#   CSRF_TRUSTED_ORIGINS  comma list of full origins, e.g. https://x.ngrok-free.app
#   DJANGO_ADMIN_ENABLED  serve /django-admin/. Follows DEBUG, so it is off on
#                         the public link: the admin is a login form on the
#                         open internet, and nothing in the demo needs it.
#   DJANGO_BEHIND_PROXY   trust X-Forwarded-Proto from the tunnel so Django
#                         sees requests as https (CSRF origin checks)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
ADMIN_ENABLED = env_bool("DJANGO_ADMIN_ENABLED", DEBUG)
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
#   TRUSTED_PROXY_COUNT   how many reverse proxies append to X-Forwarded-For in
#                         front of gunicorn (ngrok = 1, Netlify + ngrok = 2).
#                         0 (default) ignores the header, so a client cannot
#                         pick its own IP and dodge the throttles. DRF reads it
#                         as NUM_PROXIES, accounts.views._client_ip likewise.
#   SERVE_DEMO_LOCAL_TEST the ONLY way to expose sign-in codes with DEBUG off
#                         (the local e2e run). scripts/serve_demo.sh exports it
#                         as 0 for any real run; it refuses it with a tunnel.
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", 0))
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": TRUSTED_PROXY_COUNT}
if not DEBUG:
    # Defence in depth: a .env or stray variable cannot turn sign-in codes back
    # on for a DEBUG-off server (serve_demo also exports it false). Only the
    # explicit local-test flag, which serve_demo refuses behind a tunnel, can.
    if not env_bool("SERVE_DEMO_LOCAL_TEST", False):
        PLACEMENT["EXPOSE_OTP_IN_RESPONSE"] = False
    # JSON only: the browsable API is an HTML page that needs static files
    # (which gunicorn does not serve) and invites poking.
    REST_FRAMEWORK = {
        **REST_FRAMEWORK,
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    }
# === end HOSTING ================================================================
