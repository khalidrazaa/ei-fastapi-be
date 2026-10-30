# ExplainIt FastAPI backend

Backend for article publishing, editorial research/generation, YouTube trend intelligence and contact leads. The sibling admin and public Next.js apps consume this API; [AGENT.md](AGENT.md) describes the architecture and contribution rules.

## Local development

1. Install Python 3.12+ and uv, then run `uv sync --locked` from this directory.
2. Configure backend `.env` using the required fields in [app/core/config.py](app/core/config.py), point it at development databases, and apply the appropriate [migrations](Instruction.md#migrations).
3. Start FastAPI in the first PowerShell terminal:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

4. Open a second terminal in this directory and start the worker:

   ```powershell
   .\.venv\Scripts\python.exe -m app.services.content_worker
   ```

Keep both open. Restart the worker after worker code or `.env` changes. The [workflow guide](docs/content-workflow.md) covers shared Research Sources settings, providers, seed import and manual publication; [devcontainer setup](.devcontainer/README.md) covers Codespaces/Linux.

### Open all development terminals automatically

Open [blogging system.code-workspace](blogging%20system.code-workspace) in VS Code.
Its startup tasks open four dedicated terminals and start FastAPI on port 8000,
the content worker, admin UI on port 3001, and public UI on port 3000. Python uses
the backend's existing `.venv`; both frontends use their existing `npm run dev`
scripts. The public UI waits for FastAPI startup before fetching its article
snapshot. Configure development databases and install dependencies before enabling
these tasks. Opening only a repository folder does not load the workspace tasks.

Trust the workspace and allow automatic tasks when VS Code prompts. If automatic
tasks were previously disallowed, run **Tasks: Manage Automatic Tasks** from the
Command Palette and choose **Allow Automatic Tasks**, then reopen the workspace.
To launch them manually, use **Terminal > Run Task > Start all services**. Each
service reuses its own terminal and allows one running task instance.

## Docker startup

With `.env` configured and migrations applied:

```sh
docker compose up -d --build
docker compose ps
```

The repository Compose file starts the API and content worker. For the existing VPS stack, add the worker to its production Compose file and enable Docker at boot; follow [deployment steps](docs/content-workflow.md#vps-deployment-with-docker-compose). Image-only builds/runs and CI do not automatically deploy that worker.

## Public API and app keys

The application prefix is `/v1`. These endpoints require `host_site` and the `X-Public-App-Key` header; public articles must be published for that host.

| Method | Path |
| --- | --- |
| GET | `/v1/public/articles?host_site=explainit.tech&page=1&size=100` |
| GET | `/v1/public/articles/{slug}?host_site=explainit.tech` |
| GET, POST | `/v1/public/articles/{slug}/comments?host_site=explainit.tech` |
| POST | `/v1/public/contact?host_site=explainit.tech` |

Create/activate the host in backend settings, then manage keys through `GET /v1/admin/settings/public-api-keys`, `POST /v1/admin/settings/public-api-keys/generate`, and `POST /v1/admin/settings/public-api-keys/{api_key_id}/revoke`. Example generate payload:

```json
{"host":"explainit.tech","name":"EI frontend","deactivate_old_keys":true}
```

Store the one-time returned `api_key` as the public frontend's server-only `PUBLIC_APP_KEY`. Database keys are hashed; backend `PUBLIC_APP_KEYS` is a legacy fallback.

## Markdown diagram uploads

The admin editor saves a reviewed Markdown article and its SVG/PNG diagrams in one multipart request. Images stay in a persistent directory on the existing VPS and receive permanent browser-public URLs; no S3 service is used. Apply Alembic `c04_article_images` or SQL `012_article_images.sql`, set `MEDIA_PUBLIC_BASE_URL` including `/v1`, and mount the media directory before using uploads. See [article image upload](docs/article-image-upload.md) for API fields, SVG compatibility, Compose/proxy setup, retries, retention and backups. Rebuild the public frontend after publication to refresh its static article pages.

## Article pagination

Use `page` (starting at 1) and `size` (1–100, default 20) on `/v1/admin/articles` and `/v1/public/articles`. Responses contain `items`, `total`, `page`, `size`, `total_pages`, `has_next` and `has_previous`. Filters apply before counting and pagination; results use newest creation time first, with descending article ID to break ties. Empty matches return zero total pages; out-of-range pages return an empty `items` array.

Admin lists also accept `status`, `category` and literal substring `search` across title, slug and category. Their `categories` array (`name`, `count`) and `category_total` describe the full status-filtered list, independently of search, selected category and page. Blank categories appear as `Uncategorized`. Admin rows load in pages, while the public app fetches every page at build time to generate its static article snapshot and all published article pages, including libraries larger than 500 articles.

`GET /v1/admin/articles/categories` returns distinct nonempty category names from drafts and published articles across all hosts, sorted alphabetically with surrounding spaces removed. The authenticated editor uses this lightweight list for its category dropdown and also accepts custom category text; no article bodies are fetched for these options.

For existing clients, calls without pagination or admin category/search parameters keep returning an array using the legacy `limit` parameter (default 100, maximum 500). Updated frontends explicitly send `page` and `size`; deploy the backend before those frontends. No database migration is required.

## Contact leads

Contact accepts `name`, `email`, `message` and optional international `phone`, subject and source attribution. Example:

```json
{"name":"Your name","email":"you@example.com","phone":"+1 (202) 555-0198","message":"Your message"}
```

Each valid enquiry is saved before an inline email attempt. HTTP 200 confirms persistence even if email fails; there is no email worker or automatic retry. Validation, limits, responses, Brevo settings, admin access and rollout history are in [lead management](docs/lead-management.md).

## Migrations and checks

Use the installation's existing migration method; Alembic and SQL history are separate. [Instruction.md](Instruction.md) includes generation, review, targeted application and image commands. Run backend tests with `uv run python -m unittest discover -s tests`; opt-in PostgreSQL tests require disposable local `_test` databases.

## YouTube scan controls

Admin Settings > YouTube Scans provides three slider switches: **Disable popular YouTube scan**, **Disable all niche scans**, and **Disable all YouTube video scans**. Switch on to disable scanning and save the settings to apply changes to manual and scheduled scans. Disabling all YouTube videos overrides the individual preferences without clearing them; stored videos remain available.

Settings use the protected `GET`/`PUT /v1/admin/yt-scan/popular/settings` endpoints alongside the existing regions and fetch limit. Disabled manual scans return HTTP 409; scheduled scans skip their work. Running scans recheck settings before the next YouTube request stage; already sent requests can finish.

Apply Alembic revision `c03_youtube_scan_controls` or SQL history file `011_youtube_scan_controls.sql` using the installation's existing migration method before deploying this change. Scanning defaults to enabled, with all disable sliders off, to preserve existing behavior. Do not apply both migration histories for the same schema change.

If the database reports `popular_scan_settings.youtube_scan_enabled does not exist`, it is missing this migration. Back up the database, confirm the migration connection targets the same database as the API, and use the command for the existing migration history from the backend directory:

```sh
# Alembic installations
uv run alembic upgrade c03_youtube_scan_controls
```

```sh
# SQL history installations
uv run python -m migrations.migration_script --file 011_youtube_scan_controls.sql
```

Reload the settings page after migrating. API and Compose startup do not apply migrations. Missing scan-control columns return HTTP 503 with migration instructions, and scanning stays blocked until the schema is ready.
