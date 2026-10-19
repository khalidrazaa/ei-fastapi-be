# Contact lead management

Use the backend origin plus `/v1`, without a trailing slash, for the public
server's `API_URL` and admin's `NEXT_PUBLIC_API_BASE_URL`. Rebuild the admin after
changing its API URL; that setting is baked into the build.

## Submission and privacy

`POST /v1/public/contact?host_site=explainit.tech` requires `X-Public-App-Key`,
`name`, `email` and `message`; `phone` is optional. Contact is restricted to
`explainit.tech`. Success remains:

```json
{"status": true, "message": "Your message has been submitted."}
```

Required strings are trimmed: name 1–80 characters, valid email up to 254, and
message 1–5,000. Phone may be omitted, null or blank. A supplied phone string
allows at most 40 raw characters: ASCII digits, spaces, parentheses, hyphens and
a leading `+` country code, with at most 15 international digits. Letters,
extensions, control characters, invalid types/prefixes and malformed numbers
are rejected. `phonenumbers` validates country numbering rules (including fixed
and mobile numbers) and stores canonical E.164, handling trunk prefixes while
preserving significant zeros (for example UK `+44 020…` becomes `+4420…`, Italian
`+39 02…` retains `+3902…`). Numbering validity does not establish reachability.

Optional metadata: `subject`, `landing_page`, `referrer`, `utm_source`,
`utm_medium`, `utm_campaign`, `utm_term`, `utm_content` and an empty `website`
honeypot. Subject/UTM fields allow 200 characters; URLs allow 2,048. Source URLs
must be HTTP(S), without credentials; query strings/fragments are stripped.
Attribution is untrusted descriptive data. Existing callers need not supply it.

The public site retains the first landing URL, referrer and UTMs in session
storage, falling back to memory. A direct `/contact` visit becomes the landing
page if no earlier source exists. Public responses never expose internal notes,
lead status or notification errors; no raw IP address is retained.

PostgreSQL enforces one accepted enquiry per email and 20 total per 60 seconds
across API processes. Later submissions create separate leads. Invalid data or
nonempty honeypots return 422; limits return 429 with `Retry-After`; persistence
failures return a generic 503. Success means the lead committed, even if its
subsequent email attempt fails. Missing/invalid public app authentication returns
401/403; an authenticated host other than `explainit.tech` returns 403.

## Admin

The `/leads` dashboard provides search, status/source filters, pagination,
enquiry/source details, status changes and internal notes.

| Endpoint | Inputs/result |
| --- | --- |
| `GET /v1/admin/leads` | `page` (1+), `size` (1–100), optional `search`, `status`, exact UTM `source`; existing pagination envelope |
| `GET /v1/admin/leads/{id}` | Full details |
| `PATCH /v1/admin/leads/{id}` | `status` and/or `internal_notes` (10,000 characters; `""` clears); contact details cannot change |

Statuses: `new`, `contacted`, `qualified`, `proposal`, `won`, `lost`, `spam`.
All endpoints require an active admin authenticated by the OTP JWT cookie or
Bearer token. JWT signing uses backend `SECRET_KEY`, `ALGORITHM` and
`ACCESS_TOKEN_EXPIRE_MINUTES`; use a strong secret and reauthenticate sessions
created with the former hardcoded key. `/v1/admin/create` also requires an active
admin; a trusted operator must provision the first account through the existing
database process.

OTP login sets an HttpOnly `access_token` cookie; JavaScript never reads/stores
the token. Its lifetime matches `ACCESS_TOKEN_EXPIRE_MINUTES`. Cookies are Secure
except on HTTP `localhost`, `127.0.0.1` or `::1`; use the same local hostname for
admin and backend. Keep production HTTPS and set `CORS_ORIGINS` to the exact
admin origin: cookie mutations require an allowed Origin. Authenticated 401s
trigger backend logout before `/login`; invalid OTPs stay on the form, and
failed logout shows recovery guidance to avoid stale-cookie loops.

Successful lead responses use `Cache-Control: no-store`; the UI renders text.
Restrict admin/database/backup access and apply your lead retention policy.
Redact `/admin/leads` query strings from access logs because searches may contain
emails. Notification failure logs include only lead ID/error classification,
without enquiry content, contact details, credentials or provider responses.

## Email delivery

`API → Service → Query → Database` commits the lead before awaiting one Brevo
attempt through [email.py](../app/utils/email.py), with the transaction closed
and a ten-second deadline. Start the API normally:

```bash
uvicorn app.main:app --reload
```

Configure `BREVO_API_KEY`, HTTPS `BREVO_URL`, verified `EMAIL_USERNAME` and
`CONTACT_EMAIL_TO` (default `core@explainit.tech`). The visitor is Reply-To;
content is plain text. There is no email worker, outbox, delivery tracking or
automatic retry. Provider acceptance does not confirm inbox delivery. Missing
configuration, provider failure or an API exit after commit can leave a saved
lead without email; monitor failure logs and use Leads as the submission record.

## Release and verification

1. Back up PostgreSQL; review `alembic heads`, `alembic current` and cleanup SQL:
   `alembic upgrade 7d2a4c9e81b0:b6f3e94d2a10 --sql`. Revision
   `b6f3e94d2a10` removes the obsolete outbox/notification records, preserving leads.
2. Stop any old notification worker before releasing the simplified API. Direct
   email works with the deployed lead schema; outbox cleanup is optional for
   that behavior. During approved schema cleanup, run `alembic upgrade head`
   after reviewing all pending revisions. Startup applies no migrations; no
   email worker is required.
3. Check a submission appears in Leads, mailbox delivery, persisted status/notes
   edits and rejected unauthorized access. Reauthenticate after signing-key changes.
4. Prefer application rollback with enquiry data retained. Downgrading past
   `7d2a4c9e81b0` **deletes leads and their data**; recreating the outbox cannot
   recover deleted notification records.

Backend: `python -m unittest discover -s tests -v` and targeted Ruff. PostgreSQL
tests opt in via `LEAD_TEST_DATABASE_URL`, never `DATABASE_URL`; use only a
disposable local `*_test` database (for example,
`postgresql+asyncpg://...@127.0.0.1:5432/ei_leads_test`). They create/remove random
schemas and check migration round trips, atomic rollback and concurrent limits.
Email transport is mocked; no real email is needed.

Both frontends: `npx tsc --noEmit --incremental false`, `npx eslint src`,
`npm run build`; additionally public `npm run test:contact` and admin `npm test`
for mocked session recovery. Their current `npm run lint` uses unsupported
`next lint` on Next 16; use direct ESLint.

### Recorded operational history

- On 2026-10-09, with user approval, `009_update_tables.sql` was applied to
  Supabase using the SQL runner's `--file` option. Two tables, six indexes and
  constraints were verified; equivalent Alembic revision `7d2a4c9e81b0` was then
  recorded without replaying DDL. The runner commits each file/history atomically,
  accepts the synchronous migration URL and uses Windows-compatible messages.
  No worker or email was started. At the last recorded rollout, cleanup revision
  `b6f3e94d2a10` had not been applied; current database state is not verified here.
- Historical simplification/auth checks finished with 73 backend tests passing
  and seven opt-in PostgreSQL tests skipped. SQLite migration round trips,
  offline cleanup SQL, mocked contact/session checks, frontend types, targeted
  Ruff and the admin build passed. Direct ESLint had two existing admin warnings;
  earlier frontend builds were not repeated for the backend-only simplification.
  Those changes sent no real email and performed no database change/deployment.
