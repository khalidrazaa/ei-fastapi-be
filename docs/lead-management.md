# Contact lead management

The existing runtime API prefix is `/v1` (despite the older `/v1/api` wording in
`AGENT.md`). Public and admin frontend API base URLs must include `/v1`.
Set the public server's `API_URL` and the admin build's
`NEXT_PUBLIC_API_BASE_URL` to the backend origin plus `/v1`, without a trailing
slash. Admin API configuration is baked into the build, so rebuild after a
change. The admin's older README names `NEXT_PUBLIC_API_URL`; the code uses
`NEXT_PUBLIC_API_BASE_URL`.

## Submission and privacy

`POST /v1/public/contact?host_site=explainit.tech` retains its existing required
`name`, `email`, `message`, optional `phone`, public app key authentication and
success response:

```json
{"status": true, "message": "Your message has been submitted."}
```

Optional fields are `subject`, `landing_page`, `referrer`, `utm_source`,
`utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, and the empty `website`
honeypot. Subject/UTM fields are bounded to 200 characters; URLs to 2,048.
Only HTTP(S) source URLs without credentials are accepted. Query strings and
fragments are removed; source attribution is untrusted descriptive data.

The public site captures the first landing URL, referrer and UTM values in
session storage, with an in-memory fallback when storage is unavailable. A
direct visit to `/contact` is the landing page when no earlier source exists.
Attribution is optional, so existing callers continue to work. Internal notes,
statuses and notification errors are never exposed on the public API.

PostgreSQL enforces one accepted enquiry per email per 60 seconds and 20 total
accepted enquiries per 60 seconds, shared across API processes. Later enquiries
from the same email create distinct leads. Invalid data/nonempty honeypots return
422; limits return 429 with `Retry-After`. Persistence failures return a generic
503. A success response means the lead has committed. The API attempts to send
the notification after committing, before returning this response. Email
failure does not remove the lead or change the success response. No raw IP
address is retained.

## Admin

The admin dashboard's `/leads` page supports search, status/source filters,
pagination, enquiry/source details, status changes and internal notes.

* `GET /v1/admin/leads`: `page` (1+), `size` (1–100), optional `search`, `status`,
  `source` (exact UTM source). Uses the existing pagination envelope.
* `GET /v1/admin/leads/{id}`: full lead details.
* `PATCH /v1/admin/leads/{id}`: `status` and/or `internal_notes` (10,000 characters;
  empty string clears notes). Contact details cannot be edited here.

Statuses: `new`, `contacted`, `qualified`, `proposal`, `won`, `lost`, `spam`.
All lead endpoints verify the existing OTP JWT cookie or a Bearer token and
require a currently active admin account. Cookie mutations require an allowed
Origin. Set `CORS_ORIGINS` to the exact admin frontend origin; keep the existing
secure cookie/HTTPS deployment. JWT signing now uses configured `SECRET_KEY`,
`ALGORITHM` and `ACCESS_TOKEN_EXPIRE_MINUTES`; previous hardcoded-key sessions
must log in again. Use a strong deployment secret.
JWT creation and verification remain on the backend. OTP login sends the token
only through the existing HttpOnly `access_token` cookie; admin JavaScript does
not read or store it. Cookie lifetime matches `ACCESS_TOKEN_EXPIRE_MINUTES`.
Cookies remain Secure except when developing over HTTP on `localhost`,
`127.0.0.1` or `::1`. Use the same hostname for the local admin and backend
instead of mixing `localhost` and `127.0.0.1`.
An authenticated admin API request returning 401 clears the session through the
existing backend logout endpoint before returning to `/login`. Invalid OTP
responses remain on the login form. A failed logout shows recovery guidance
instead of redirecting into a stale-cookie loop.
The existing `/v1/admin/create` endpoint now requires an active admin too; initial
admin provisioning must be performed by a trusted operator using the existing
database provisioning process, rather than public self-registration.

Successful admin lead responses use `Cache-Control: no-store`; UI content is
rendered as text. Limit database/backups and admin access to staff who need these
enquiries. Apply your retention policy to lead records. Redact query strings
for `/admin/leads` from proxy/access logs because searches can contain email
addresses. Email failure logs contain the lead ID and error classification,
without contact details, enquiry text, credentials or provider responses.

## Email delivery

The flow is `API → Service → Query → Database`: commit the lead, then await one
email attempt through the existing `app/utils/email.py` Brevo integration. The
database transaction is closed before the provider call, and the email attempt
is bounded to 10 seconds. Start the API normally:

```bash
uvicorn app.main:app --reload
```

Keep `CONTACT_EMAIL_TO=core@explainit.tech` (default), and configure the existing
`BREVO_API_KEY`, `BREVO_URL` and verified `EMAIL_USERNAME`. The visitor's email
is Reply-To; enquiry content is sent as plain text.

There is no email worker, outbox queue, delivery tracking or automatic retry.
Provider acceptance does not confirm inbox delivery. If configuration is
missing, the provider fails, or the API stops after saving the lead, that enquiry
remains available in Leads but its email may not arrive. Monitor API email
failure logs and use Leads as the record of submitted enquiries.

## Release and verification

1. Back up PostgreSQL. Review `alembic heads`, `alembic current` and the pending
   SQL: `alembic upgrade 7d2a4c9e81b0:b6f3e94d2a10 --sql`. Cleanup revision
   `b6f3e94d2a10` removes the old notification outbox and its delivery events;
   the `leads` table and enquiries are retained.
2. Stop any previously configured notification worker before releasing the
   simplified backend. The simplified API works with the already deployed lead
   schema; dropping the unused outbox is cleanup, not a prerequisite for direct
   email delivery. During an approved schema cleanup, run `alembic upgrade head`.
   API startup does not apply migrations. No email worker needs to be configured.
3. Verify an enquiry appears in Leads, email reaches the configured core mailbox,
   and status/notes edits persist. Verify unauthorized API access is rejected.
   Reauthenticate existing admins after the signing-key change.
4. Prefer reverting application code while retaining enquiry data if rollback
   is needed. Downgrading past `7d2a4c9e81b0` **deletes the leads table and its
   data**. Recreating the old outbox on downgrade cannot restore removed events.

Backend checks: `python -m unittest discover -s tests -v` and Ruff on changed
feature files. PostgreSQL-specific tests never read `DATABASE_URL`; opt in with
`LEAD_TEST_DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:5432/ei_leads_test`.
They require a local database ending in `_test`, create/remove random test
schemas, and verify migration round trips, atomic rollback and concurrent
submission limits. Use only a disposable local cluster. Email transport is
mocked in automated tests; no real enquiry email needs to be sent for testing.

Both frontends: `npx tsc --noEmit --incremental false`, `npx eslint src` and
`npm run build`; public UI additionally `npm run test:contact`, admin UI
`npm test` for mocked session recovery checks. The existing
`npm run lint` scripts call `next lint`, which Next 16 no longer provides; use
direct ESLint until the scripts are updated separately.

Simplification verification: 69 backend tests passed, with seven PostgreSQL
tests skipped because no disposable local test database was configured. The two
SQLite migration round-trip tests and offline PostgreSQL cleanup SQL passed.
All 18 public contact integration tests, both frontend type checks, and targeted
Ruff passed. Direct frontend ESLint passed with two existing admin warnings.
Frontend production builds had passed before this backend-only simplification;
the frontends were unchanged and were not rebuilt for it.

The subsequent localhost authentication fix passed all 13 backend auth tests,
all nine mocked admin session tests, targeted Ruff, admin type checks and the
admin production build. Full backend verification passed 73 tests and skipped
the seven opt-in PostgreSQL tests. No real OTP email was sent during testing.

After explicit user approval on 2026-10-09, `009_update_tables.sql` was applied
to the configured Supabase database using the SQL runner's `--file` option.
The two tables, six indexes and constraints were verified against the models,
then equivalent Alembic revision `7d2a4c9e81b0` was recorded without replaying
DDL. The SQL runner now commits each file and its history atomically, accepts
the synchronous migration URL and uses Windows-compatible status messages.
No notification worker was started and no email was sent during this migration.
The later simplification adds cleanup revision `b6f3e94d2a10` for the outbox;
that migration has not been applied to Supabase. No database changes or
deployment were performed as part of simplifying email delivery.
