#!/usr/bin/env bash
# Serve the backend for the public demo link: gunicorn, DEBUG off, behind a tunnel.
#
# Lives in scripts/ at the repo root (not backend/) because it is operator
# tooling that spans the venv, the root .env and the tunnel, not Django code.
#
#   scripts/serve_demo.sh --tunnel-host my-name.ngrok-free.app \
#                         --netlify-domain my-demo.netlify.app
#
# Flags (each also an env var): --tunnel-host / TUNNEL_HOST, --netlify-domain /
# NETLIFY_DOMAIN, --port / PORT (8000), --timeout / GUNICORN_TIMEOUT (240 s: one
# live Gemma call is ~90 s and there may be a retry), PYTHON (the venv python).
# DEMO_ALLOW_INSECURE_KEY=1 (dev SECRET_KEY) and SERVE_DEMO_LOCAL_TEST=1 (returns sign-in
# codes, for the local e2e run) are local-only: both refused when a tunnel/Netlify host is set.
# TRUSTED_PROXY_COUNT sets how many X-Forwarded-For hops to trust (default 1 per tunnel/Netlify).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"
PORT="${PORT:-8000}"
TIMEOUT="${GUNICORN_TIMEOUT:-240}"
TUNNEL_HOST="${TUNNEL_HOST:-}"
NETLIFY_DOMAIN="${NETLIFY_DOMAIN:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --tunnel-host) TUNNEL_HOST="$2"; shift 2 ;;
    --netlify-domain) NETLIFY_DOMAIN="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Accept pasted URLs: strip scheme and any path.
strip() { local h="${1#http://}"; h="${h#https://}"; echo "${h%%/*}"; }
TUNNEL_HOST="$(strip "$TUNNEL_HOST")"
NETLIFY_DOMAIN="$(strip "$NETLIFY_DOMAIN")"

hosts="localhost,127.0.0.1"
origins=""
add() {
  [ -n "$1" ] || return 0
  hosts="$hosts,$1"
  origins="${origins:+$origins,}https://$1"
}
add "$TUNNEL_HOST"
add "$NETLIFY_DOMAIN"
[ -n "$TUNNEL_HOST" ] || echo "warning: no --tunnel-host / TUNNEL_HOST; only localhost will be accepted" >&2

public=0
{ [ -n "$TUNNEL_HOST" ] || [ -n "$NETLIFY_DOMAIN" ]; } && public=1

# Local-only switches. Both are refused as soon as a tunnel or Netlify host is set.
if [ "$public" = 1 ]; then
  if [ "${DEMO_ALLOW_INSECURE_KEY:-}" = "1" ]; then
    echo "refusing to start: DEMO_ALLOW_INSECURE_KEY=1 with a tunnel/Netlify host. Set a real DJANGO_SECRET_KEY." >&2
    exit 1
  fi
  if [ "${SERVE_DEMO_LOCAL_TEST:-}" = "1" ]; then
    echo "refusing to start: SERVE_DEMO_LOCAL_TEST=1 returns sign-in codes in responses; never with a tunnel/Netlify host." >&2
    exit 1
  fi
fi

# Exported, so a .env at the repo root (load_dotenv never overrides exports)
# cannot turn any of these back on.
export DJANGO_DEBUG=false
export DJANGO_ADMIN_ENABLED=false
export DEMO_MODE=false
if [ "${SERVE_DEMO_LOCAL_TEST:-}" = "1" ]; then
  echo "NOTE: SERVE_DEMO_LOCAL_TEST=1: sign-in codes are returned in responses (local e2e run only)." >&2
  export EXPOSE_OTP_IN_RESPONSE=true
else
  export SERVE_DEMO_LOCAL_TEST=0
  export EXPOSE_OTP_IN_RESPONSE=false
fi
export DJANGO_ALLOWED_HOSTS="$hosts"
export CSRF_TRUSTED_ORIGINS="$origins"
export CORS_ALLOWED_ORIGINS="${origins:-http://localhost:5173}"
export DJANGO_BEHIND_PROXY=true
# X-Forwarded-For hops our proxies add: ngrok, plus Netlify when it fronts the API.
if [ -z "${TRUSTED_PROXY_COUNT:-}" ]; then
  TRUSTED_PROXY_COUNT=0
  [ -n "$TUNNEL_HOST" ] && TRUSTED_PROXY_COUNT=1
  [ -n "$TUNNEL_HOST" ] && [ -n "$NETLIFY_DOMAIN" ] && TRUSTED_PROXY_COUNT=2
fi
export TRUSTED_PROXY_COUNT

cd "$ROOT/backend"

# Refuse the dev-default SECRET_KEY: tokens signed with a published key can be forged.
if [ "${DEMO_ALLOW_INSECURE_KEY:-}" != "1" ]; then
  if ! "$PYTHON" -c '
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.conf import settings
sys.exit(1 if settings.SECRET_KEY.startswith("dev-only-insecure") or len(settings.SECRET_KEY) < 32 else 0)
'; then
    echo "refusing to start: DJANGO_SECRET_KEY is unset or the dev default." >&2
    echo "Export a long random one: python -c 'import secrets;print(secrets.token_urlsafe(50))'" >&2
    echo "(or DEMO_ALLOW_INSECURE_KEY=1 for a local-only check)." >&2
    exit 1
  fi
fi

echo "serve_demo: port $PORT, timeout ${TIMEOUT}s, allowed hosts: $hosts"
exec "$PYTHON" -m gunicorn config.wsgi:application \
  --bind "127.0.0.1:$PORT" --workers 2 --threads 4 \
  --timeout "$TIMEOUT" --graceful-timeout 30 --access-logfile -
