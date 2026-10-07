# explainit.tech-fastapi

FastAPI backend for article publishing and trend intelligence.

## New Public Content API (No Login)

These endpoints are now available under `/v1/api/public/articles` and are protected by per-host app keys:

- `GET /v1/api/public/articles?host_site=<host>&limit=100`
- `GET /v1/api/public/articles/{slug}?host_site=<host>`
- `GET /v1/api/public/articles/{slug}/comments?host_site=<host>&limit=100`
- `POST /v1/api/public/articles/{slug}/comments?host_site=<host>`

Use admin settings APIs to generate/revoke keys (stored hashed in DB):

- `GET /v1/api/admin/settings/public-api-keys`
- `POST /v1/api/admin/settings/public-api-keys/generate`
- `POST /v1/api/admin/settings/public-api-keys/{api_key_id}/revoke`

Generate payload example:

```json
{
  "host": "explainit.tech",
  "name": "EI frontend",
  "deactivate_old_keys": true
}
```

The generate endpoint returns a one-time `api_key` value. Save it in frontend `.env.local` as `PUBLIC_APP_KEY`.

`PUBLIC_APP_KEYS=...` in `.env` is now optional fallback compatibility only.

## Contact email API

`POST /v1/public/contact?host_site=explainit.tech` uses the existing
`X-Public-App-Key` authentication. The actual application prefix is `/v1`.

```json
{"name": "Your name", "email": "you@example.com", "phone": "+1 (202) 555-0198", "message": "Your message"}
```

Fields are trimmed and validated: name 1–80 characters, valid email up to
254 characters, message 1–5000 characters. Only explainit.tech is accepted.
Optional `phone` may be omitted, null, or blank. A supplied number must begin
with `+`, have a nonzero first digit and 7–15 total ASCII digits, and be at
most 40 raw characters. ASCII spaces, parentheses, and hyphens are allowed
and removed before forwarding (for example, `+12025550198`). Letters,
extensions, control characters, multiple plus signs, and non-string values
are rejected. This validates international formatting, not whether a number
is allocated or reachable. Phone appears in the plain-text email only when
provided; submissions without it continue to work.
The recipient is server-configured `CONTACT_EMAIL_TO` (default
`core@explainit.tech`). Email uses the existing `BREVO_URL`, `BREVO_API_KEY`,
and verified `EMAIL_USERNAME` sender. The visitor is Reply-To; content is
plain text. Public keys and provider credentials remain server-side.

HTTP 200 returns `{"status": true, "message": "Your message has been submitted."}`
only after Brevo returns 201 with a message ID. This confirms provider
acceptance, not inbox delivery. Errors: 422 validation, 401/403 authentication
or host mismatch, 429 cooldown, 503 missing/invalid email configuration,
502 provider rejection/network failure, and 504 timeout. Provider details
and credentials are not included in error responses.

Basic abuse protection limits one attempt per email per 60 seconds and
20 attempts per 60 seconds per backend process, including failed sends.
HTTP 429 includes `Retry-After`. State is bounded, held in memory, resets
on restart, and is not shared across workers; production-wide limits
should also be enforced at the public proxy or in a shared store.

## Migrations

```bash
python -m migrations.generate_sql_from_models
python -m migration.migration_script
```

Or run Alembic as per your current workflow.
