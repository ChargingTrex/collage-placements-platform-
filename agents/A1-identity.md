# A1 — Identity

Read [`CONTEXT.md`](../CONTEXT.md) first.

You own the seam every other agent depends on: who a user is, what they may do,
and how the portal will one day accept a platform token.

## You own

`accounts/` · `roster/` · `core/` · shared config · the `IdentityProvider`
adapter · the frontend auth surface (`src/auth/`, `src/api/client.ts`)

You also own three shared surfaces (`accounts/permissions.py`,
`core/storage.py`, `config/settings.py`) and **migration ordering for the whole
repo**. No other agent writes a migration without raising it to you.

## Phase A — your streams

Stream **A-1** (UUID keys, status lifecycle, reconciliation filters) is being
done by the main agent, not you. Pick up from there.

| Stream | Gaps | Work |
| --- | --- | --- |
| **A-2** | G3–G7 | The §5.4 claim contract · `roles` as an array · 15-minute access tokens · refresh-reuse family revocation · RS256 with a published JWKS |
| **A-3** | G8, G10 | PRN regex to shared config as `^[0-9]{9}$` · the eight schools and ~45 programmes as a code list · unknown codes surfacing as unknown and logging |

## The claim contract — exact, not approximate

```json
{
  "sub": "<user_uuid>", "iss": "...", "aud": ["portal"],
  "iat": 0, "exp": 0, "email": "...", "student_id": "<uuid>|null",
  "prn": "220200921|null", "display_name": "...",
  "roles": ["student"], "department": "...|null",
  "programme": "...|null", "year": 0, "mfa": false
}
```

Every key present in every mode. **Optional values are `null`, never omitted** —
a consumer reading `claims["prn"]` must not KeyError on a staff token.

`full_name` is deliberately absent; `display_name` covers rendering.

A recruiter carries `company_recruiter:<company_uuid>` in `roles` — the spec's
`<role>:<scope_uuid>` pattern (§4.3). No new claim is needed for company scope.

## Watch for

- The current `role` is a single string in `accounts/serializers.py:tokens_for`.
  Every reader of it changes.
- `resolve_user` already strips whitespace and matches case-insensitively on
  both email and PRN. Verified. Do not "fix" it.
- `USERNAME_FIELD = "email"` is **not** a violation. The spec permits email for
  "SSO subject matching at first login"; it forbids email as a *key*.
