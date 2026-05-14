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

## Migrations

```bash
python -m migrations.generate_sql_from_models
python -m migration.migration_script
```

Or run Alembic as per your current workflow.
