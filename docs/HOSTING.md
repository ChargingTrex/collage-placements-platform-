# Hosting the demo on a public link

The shape: **Netlify** serves the built React app and forwards `/api/*` to an
**ngrok** tunnel, which reaches **gunicorn** on your Mac. The link works only
while the Mac is awake and the two processes below are running.

```
phone/browser -> https://YOUR-SITE.netlify.app
                   /api/*  -> https://YOUR-NAME.ngrok-free.app/api/*  -> your Mac, 127.0.0.1:8000 (gunicorn)
```

You need a Netlify account and an ngrok account (both free). Nothing in this
repo can create them for you.

## One-time setup

1. **Install ngrok and sign in.**
   ```
   brew install ngrok
   ngrok config add-authtoken <token from dashboard.ngrok.com/get-started/your-authtoken>
   ```
2. **Claim the free static domain.** In the ngrok dashboard open *Domains* (or
   *Universal Gateway -> Domains*), click *Create Domain*, and keep the name it
   gives you, like `quiet-otter-1234.ngrok-free.app`. This is `TUNNEL_HOST`
   below. It does not change between runs.
3. **Install the Netlify CLI and sign in.**
   ```
   npm install -g netlify-cli
   netlify login
   ```
4. **Create the Netlify site** (once), from `frontend/`:
   ```
   cd frontend && netlify init --manual     # or: netlify sites:create --name your-demo-name
   ```
   Note the site domain, like `your-demo-name.netlify.app`. This is `NETLIFY_DOMAIN`.
5. **Put the tunnel host into the redirects.** In `frontend/public/_redirects`
   replace `TUNNEL_HOST` with your ngrok domain (no `https://`):
   ```
   sed -i '' 's/TUNNEL_HOST/quiet-otter-1234.ngrok-free.app/' frontend/public/_redirects
   ```
   Check it: `cat frontend/public/_redirects`. Do not commit your real domain if
   the repo is public.
6. **Make a secret key** and keep it in your shell (or the root `.env`):
   ```
   export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets;print(secrets.token_urlsafe(50))')"
   ```
   `serve_demo` refuses to start on the development default key.

## Every demo session

1. **Prepare the database** (reset to the synthetic seed and pre-analyse; see
   WEEKEND_DEMO_PLAN.md R3). Start Ollama/MongoDB if the demo uses them.
2. **Start the backend** from the repo root:
   ```
   scripts/serve_demo.sh --tunnel-host quiet-otter-1234.ngrok-free.app \
                         --netlify-domain your-demo-name.netlify.app
   ```
   It runs gunicorn with `DJANGO_DEBUG=false` on `127.0.0.1:8000`, with a 240 s
   timeout (one live Gemma call is about 90 s, and there may be a retry). Change
   it with `--timeout 300` or `GUNICORN_TIMEOUT`; the port with `--port` or `PORT`.
   Both hosts go into `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
3. **Start the tunnel** in a second terminal:
   ```
   ngrok http --url=quiet-otter-1234.ngrok-free.app 8000
   ```
   Check: `curl https://quiet-otter-1234.ngrok-free.app/api/health` returns JSON
   with `"debug":false`.
4. **Deploy the frontend** (only when the frontend or the redirects changed):
   ```
   cd frontend && npm run build && netlify deploy --prod --dir=dist
   ```
   `netlify.toml` records the same build command (`npm run build`) and publish
   folder (`dist`) if you deploy from the Netlify UI or a connected repo.
5. Open `https://your-demo-name.netlify.app`, then run the smoke test (below).
6. **When the demo ends, stop ngrok** (Ctrl-C) and gunicorn.

## Caveats

- **ngrok warning page.** On the free plan ngrok can answer browser-looking
  requests with an HTML "visit site" page unless the request carries the header
  `ngrok-skip-browser-warning` (any value). If sign-in or any page shows a JSON
  parse error or HTML in the response, that is why. The fix that needs no code
  change is the commented fallback in `netlify.toml`: delete the `/api/*` line
  from `frontend/public/_redirects`, uncomment the `[[redirects]]` block there
  (it adds the header on the proxied request), rebuild and redeploy. This is
  untested until the first real deploy.
- **Netlify's proxy gives up after about 30 s.** Any request that takes longer
  comes back as a 502/504 through the link, even though gunicorn would finish
  it. The live resume upload plus Gemma analysis takes about 90 s, so **do that
  step on `localhost` (the Vite dev server or `serve_demo` directly), never on
  the public link**; on the link, use students whose resumes were analysed in
  advance.
- **Sign-in codes are not in responses** with DEBUG off. Public-link students
  get their code in the server's console output (the console email backend), so
  watch the `serve_demo` terminal, or sign in with a pre-created account.
  `checkpoints/e2e_phase_0_3.py` needs the code in the response, so against the
  public link it will report the signup checks as failed; run it locally with
  `SERVE_DEMO_LOCAL_TEST=1` (see below).
- `/django-admin/` is switched off (404) on the public link. To use the admin,
  run the ordinary dev server (`manage.py runserver`, DEBUG on) locally.
- The Mac must stay awake (`caffeinate -dis` in a spare terminal).

## Smoke test and security check

Locally, against `serve_demo`, on a throwaway database:

```
cd backend && export LLM_ENABLED=false
python manage.py migrate && python manage.py seed_demo
SERVE_DEMO_LOCAL_TEST=1 DEMO_ALLOW_INSECURE_KEY=1 OTP_THROTTLE_RATE=1000/hour \
  ../scripts/serve_demo.sh --port 8765 &
python checkpoints/e2e_phase_0_3.py --base-url http://127.0.0.1:8765
```

`SERVE_DEMO_LOCAL_TEST=1` is the only way to get sign-in codes back in responses
with DEBUG off, and `DEMO_ALLOW_INSECURE_KEY=1` allows the dev secret key. Both
are local-only: `serve_demo` refuses either one when `--tunnel-host` or
`--netlify-domain` is set. Do not set `EXPOSE_OTP_IN_RESPONSE` yourself; with
DEBUG off settings ignore it unless `SERVE_DEMO_LOCAL_TEST=1`.

On the public link, check by hand (replace the host):

```
curl -s -o /dev/null -w '%{http_code}\n' https://HOST/django-admin/        # 404
curl -s -o /dev/null -w '%{http_code}\n' https://HOST/media/x.pdf          # 404
curl -s -o /dev/null -w '%{http_code}\n' https://HOST/api/auth/demo/personas  # 404
curl -s https://HOST/api/health                                            # "debug":false
```

## What `serve_demo` forces, and why a `.env` cannot undo it

`serve_demo` exports these before starting gunicorn:

| Variable | Value | Effect |
| --- | --- | --- |
| `DJANGO_DEBUG` | `false` | no debug pages, no browsable API |
| `DJANGO_ADMIN_ENABLED` | `false` | `/django-admin/` is a 404 |
| `DEMO_MODE` | `false` | no one-click demo sign-in routes |
| `EXPOSE_OTP_IN_RESPONSE` | `false` | no sign-in codes in any response |
| `SERVE_DEMO_LOCAL_TEST` | `0` | the local-test escape hatch is closed |

The repo-root `.env` is read with `load_dotenv`, which never overrides a
variable already exported in the environment, so a `.env` saying
`EXPOSE_OTP_IN_RESPONSE=true` or `DJANGO_ADMIN_ENABLED=true` cannot win.
`settings.py` adds a second guard: with DEBUG off, sign-in-code exposure is
forced off unless `SERVE_DEMO_LOCAL_TEST=1`, and `DEMO_MODE` is ignored.

## `/api/health` with DEBUG off

Anonymous callers get only `status`, `service`, `debug` and, per check, `ok`
plus `storage.backend` and `matching_engine.backend`. The storage path, the
database engine or error text and the model details appear only with DEBUG on.

## Trusted proxies and the throttles

The OTP and anonymous throttles key on the client IP. `X-Forwarded-For` is
client-controlled on its left, so only the entries our own proxies append are
trusted: `TRUSTED_PROXY_COUNT` (also DRF's `NUM_PROXIES`) says how many. `serve_demo`
sets it to **1** with a tunnel host and **2** with a tunnel host plus a Netlify
domain (Netlify and ngrok each append one hop); override with
`TRUSTED_PROXY_COUNT=n`. With 0 the header is ignored.

**First real deploy check** (the Netlify behaviour is assumed, not yet seen):
1. Send a request through the Netlify URL with a forged header, e.g.
   `curl -s -H 'X-Forwarded-For: 6.6.6.6' https://YOUR-SITE.netlify.app/api/health`.
2. Look at gunicorn's output or the ngrok inspector (http://127.0.0.1:4040) and
   confirm the request's `X-Forwarded-For` ends with your real public IP then
   Netlify's, in that order, with `6.6.6.6` at the far left.
3. Confirm the throttle sees you: call `/api/auth/otp/request` more than
   `OTP_THROTTLE_RATE` times from one machine and get a 429, then repeat with a
   different forged `X-Forwarded-For` and still get the 429.
4. If Netlify does not append (only ngrok's hop is present), restart with
   `TRUSTED_PROXY_COUNT=1`. If every visitor is throttled together, the count is
   too low (all share one hop); if forging avoids the 429, it is too high.

## Before the demo

- Clear the cache: `rm -rf backend/.cache` (if that folder exists; the file
  cache also keeps throttle counters, so old 429s would survive a restart).
- Re-run `read_jd` for the demo job descriptions so they are read fresh. Note:
  I found no `read_jd` management command or file-cache setting on this branch,
  so use whatever the demo checklist (E/G stream) names for it.
