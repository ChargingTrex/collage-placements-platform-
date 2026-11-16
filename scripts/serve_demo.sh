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
# Set DEMO_ALLOW_INSECURE_KEY=1 to run with the dev SECRET_KEY (local checks only).
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

export DJANGO_DEBUG=false
export DJANGO_ALLOWED_HOSTS="$hosts"
export CSRF_TRUSTED_ORIGINS="$origins"
export CORS_ALLOWED_ORIGINS="${origins:-http://localhost:5173}"
export DJANGO_BEHIND_PROXY=true

case "${EXPOSE_OTP_IN_RESPONSE:-0}" in
  0|false|False|no|"") ;;
  *) echo "WARNING: EXPOSE_OTP_IN_RESPONSE is on: sign-in codes are returned in responses. Never on the public link." >&2 ;;
esac

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
