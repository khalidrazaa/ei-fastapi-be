# Repository instructions

This workspace is the ExplainIt publishing and YouTube trend-intelligence system. Keep the sibling layout used by `blogging system.code-workspace`:

| Repository | Responsibility |
| --- | --- |
| `ei-fastapi-be` | FastAPI, persistence, integrations, scanning, content jobs |
| `ei-admin-ui-nextjs` | Next.js admin: topics, drafts, articles, leads, niches, settings |
| `ei-ui-nextjs` | Next.js public articles, comments, contact form |

Additional applications may be added; do not assume a `future-apps` directory exists.

## Architecture and contracts

Follow `API -> Service -> Query -> Database`: routes handle HTTP/auth, services own business logic, query modules own persistence, models define tables, and schemas validate inputs/outputs. Keep new logic out of routes and reuse existing contracts before adding endpoints or response wrappers.

| Location | Purpose |
| --- | --- |
| `app/main.py`, `app/api/router.py` | Startup and route registration; actual API prefix is `/v1` |
| `app/core/` | Settings, JWT/admin authentication, public app-key checks |
| `app/db/models/`, `app/db/query/`, `app/schemas/` | SQLAlchemy models, database access, Pydantic validation |
| `app/services/content_*.py` | Inventory workflow, providers, worker, policy, seed import |
| `app/clients/`, `app/services/scanner/`, `app/services/analyzer/` | YouTube API, niche/popular scans, trend scores and ideas |
| `app/scheduler/` | APScheduler scan/discovery jobs registered at API startup |
| `alembic/`, `migrations/` | Separate Alembic and SQL-history migration mechanisms |
| Frontend `src/app/`, `src/components/`, `src/lib/`, `src/types/` | Routes, reusable UI, API/services/utilities, types |

Use `/v1/admin/...`, `/v1/public/articles`, and `/v1/public/contact`; `/v1/api` is not registered by this app. Read route registration before changing paths. Preserve existing admin cookie/Bearer authentication and Origin checks on protected routes. Public requests require `host_site` and `X-Public-App-Key`; public article queries return only published content for that host.

## Functional boundaries

- Niches contain keywords; scanning fetches videos, then analysis scores virality/growth/engagement, discovers trends and creates ideas. PostgreSQL is the main relational store; MongoDB remains an integration. Inspect the existing store before adding persistence.
- Inventory flow: brief -> manual research -> manual generation -> automatic QA -> manual Save to Drafts -> manual publish in the article editor. QA is advisory; there is no separate approval gate. OpenAI/Gemini selection is pinned per job; automatic QA inherits generation's provider. Inventory research does not require YouTube. Shared sources/instructions are managed through protected `/v1/admin/content-research-settings` and stored in `content_research_settings`; enqueue research with a settings snapshot, keep per-brief URLs optional, and preserve historical snapshots. Defaults select relevant sources rather than requiring every preferred domain.
- Accept all schema-valid provider claims, including empty or nonmatching citation lists. Do not reject research on per-claim URL membership. Preserve claims and the provider-returned source catalog separately; research readiness and advisory QA still apply.
- Preserve immutable workspace versions, current-brief checks, idempotency, article fingerprints, job leases/fencing and cancellation. Workspace operations must not overwrite published articles. Keep private briefs/research/QA out of public article bodies; topic IDs are never reused. Archive topics with history instead of deleting them.
- Contact submissions are committed as leads before an inline email attempt. Email failure does not undo a saved enquiry. There is no email worker, outbox or automatic email retry. Preserve validation, database-backed submission limits, admin access and private/no-store responses. Details: [lead management](docs/lead-management.md).

## Development

Use Python 3.12+ and Node 24 (matching the devcontainer and frontend images). From the backend, `uv sync --locked` installs dependencies. Configure all required fields declared in `app/core/config.py` in backend `.env`, including existing integration settings; selecting one AI provider does not remove other required settings. Never commit or print credentials.

Run from each application's own directory, using a development database:

| Process | Command |
| --- | --- |
| FastAPI | `uv run uvicorn app.main:app --reload` |
| Content worker, separate terminal | `uv run python -m app.services.content_worker` |
| Public frontend | `npm ci`, then `npm run dev -- --port 3000` |
| Admin frontend | `npm ci`, then `npm run dev -- --port 3001` |

API startup does not start the content worker. Keep both backend terminals open; restart the worker after its code or environment changes. APScheduler already starts per API process: consider duplicate scan scheduling when changing Gunicorn process counts. Do not run a development worker against production queues.

Admin requests use `NEXT_PUBLIC_API_BASE_URL` (including `/v1`) with credentials; configure matching backend CORS origins. The public app keeps `API_URL` and `PUBLIC_APP_KEY` server-side. Set browser-visible variables before building, verify Docker build arguments match source usage, and provide loading/error states. Keep shared frontend logic reusable. See each frontend README and the [devcontainer guide](.devcontainer/README.md).

## Database changes and validation

1. Register relational models in `app/db/models/__init__.py`, imported by `app/db/base.py`.
2. Use a reviewed migration. Alembic uses `ALEMBIC_DATABASE_URL`; the SQL generator inspects the configured database and writes additive SQL. The SQL runner checks `DB_NAME`; its bare invocation applies every untracked history file, while `--file` selects one reviewed file.
3. Back up before deployment, inspect generated SQL, and use the installation's migration history. Alembic and `schema_migrations` are independent; do not apply equivalent schema changes twice or run migrations at API startup. Commands: [Instruction.md](Instruction.md).
4. Run checks appropriate to the change:

   | App | Checks from its directory |
   | --- | --- |
   | Backend | `uv run python -m unittest discover -s tests` |
   | Admin | `npm test`, `npx tsc --noEmit`; `npm run build` for build-related changes |
   | Public | `node --test tests/*.test.mjs`, `npx tsc --noEmit`; `npm run build` for build-related changes |

Use mocked/isolated tests for routine work. Optional `CONTENT_TEST_DATABASE_URL` and `LEAD_TEST_DATABASE_URL` suites require disposable local databases ending in `_test`; never target production. Check current package scripts before documenting lint commands.

## Deployment and working rules

- `compose.yaml` builds and starts `api` plus `content-worker`; `compose.worker.yaml` supports the standalone worker. The Dockerfile alone starts Gunicorn. Keep the content worker separately supervised rather than spawning it inside API processes.
- The existing VPS stack uses `fastapi-app`; add a worker with the same backend image, environment and networks. No worker port or Nginx route is needed. Configure restart policy and Docker startup at boot. CI builds/pushes images; it does not deploy services or apply migrations. Steps: [content workflow](docs/content-workflow.md).
- Trace changes through UI -> API -> service -> query/client -> storage; check payloads, response shapes, settings and side effects. Fix the underlying cause.
- Read related code before editing, explain intended changes, prefer small existing-pattern fixes, and preserve unrelated work. Do not duplicate logic, break contracts or add unused code. Never hand-edit `.next`, `node_modules`, virtual environments or generated build outputs. Update affected documentation when behavior changes.
