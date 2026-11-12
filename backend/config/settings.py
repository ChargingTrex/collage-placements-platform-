"""
Django settings for the Placement Cell Portal.

Environment-driven so the same code runs on SQLite (default local dev) and
PostgreSQL (docker-compose / deployment) with no code change -- see .env.example
at the repo root for every variable this file reads.
"""

from datetime import timedelta
from pathlib import Path

import dj_database_url
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
SKILL_GRAPH = {
    "ALIAS_SUGGESTION_THRESHOLD": float(os.getenv("SKILL_ALIAS_SUGGESTION_THRESHOLD", 0.85)),
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
# the best sample. The embedding constants are PROVISIONAL, typical
# nomic-embed-text cosines (unrelated ~0.4, a close match ~0.85), until the
# live run (plan §5.4) measures the samples. Retune all of them when the
# model changes.
MATCH_SCORE = {
    "WEIGHTS": {"semantic": 0.45, "skills": 0.35, "experience": 0.10, "education": 0.10},
    "CALIBRATION": {
        "embedding": {"FLOOR": 0.40, "CEILING": 0.85},
        "spacy": {"FLOOR": 0.80, "CEILING": 0.97},
        "tfidf": {"FLOOR": 0.00, "CEILING": 0.25},
    },
    # With no embedder, /api/matching/search scores visible profiles one by
    # one on the similarity backend; this caps how many.
    "FALLBACK_MAX_PROFILES": int(os.getenv("MATCH_FALLBACK_MAX_PROFILES", 500)),
}

# Role categories learnt from recruiters' JDs (matching/categories.py).
# MERGE_THRESHOLD is a raw embedding cosine between a JD and a same-titled
# category's centroid: below it the JD starts a variant for an admin to
# review. PROVISIONAL for nomic-embed-text, like MATCH_SCORE's embedding
# constants. A profile gets at most MAX_PER_PROFILE categories, each with
# a fit (CENTROID_WEIGHT x calibrated centroid cosine + the rest x weighted
# skill overlap) of at least MIN_FIT.
CATEGORY = {
    "MERGE_THRESHOLD": float(os.getenv("CATEGORY_MERGE_THRESHOLD", 0.75)),
    "MIN_FIT": float(os.getenv("CATEGORY_MIN_FIT", 0.4)),
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
