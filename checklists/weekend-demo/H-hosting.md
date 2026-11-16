# H: hosting

Owner: H builder. QA: QA-1.

- [ ] H1: gunicorn in the requirements, plus a `serve_demo` script. The script starts the backend with:
  - `DEBUG=false`
  - a gunicorn timeout that covers G4's worst case (not the plan's 120 s, if G4 measures more)
  - the tunnel host in `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
  - the Netlify domain allowed

  **Pass when:** the script starts locally, and `/api/health` answers through gunicorn with DEBUG off.
- [ ] H2: `frontend/public/_redirects` (and `netlify.toml` if needed) forwards `/api/*` to the tunnel address with status 200, and sends `/*` to `/index.html` with status 200. The tunnel address is a placeholder until U2. **Pass when:** `npm run build` copies it into `dist/`.
- [ ] H3: Netlify deploy. **owner: user (needs U1)**. The build command and publish folder are documented.
- [ ] H4: Public-link smoke test: `checkpoints/e2e_phase_0_3.py` against the Netlify URL, plus a phone pass. **owner: user (needs U1, U2)**. **Local stand-in:** the same suite against `serve_demo` on localhost, with the agent-verifiable result recorded.
- [ ] H5: Security pass with DEBUG off. **Pass when:** checked locally against `serve_demo`, and re-checked on the public link once it exists:
  - no debug page
  - `/media/` returns 404
  - `/django-admin/` is disabled or has a strong password
  - demo sign-in returns 404
  - no sign-in code appears in any response
