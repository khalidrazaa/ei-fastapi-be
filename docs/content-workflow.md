# Inventory article workflow

Create a topic, save its brief, run research, then generate an article. Generation automatically queues QA. Review the evidence and article, save it to Drafts, then publish manually in the article editor. Choose OpenAI or Gemini in the workspace; QA is advisory and does not enforce publication approval.

Admins can also write directly from **Drafts -> New Draft**. Saving creates a draft through authenticated `POST /v1/admin/articles` with a title, unique slug, and content (which may be empty), plus optional article metadata. New articles always begin as drafts; publishing remains a separate save in the editor. Manual drafts do not require a topic or AI generation.

## Setup

1. Fill the required backend settings from [app/core/config.py](../app/core/config.py), including database settings and a provider key: `OPENAI_API_KEY` (or `OPEN_AI_KEY`) for OpenAI, or `GOOGLE_AI_STUDIO_API_KEY` for Gemini. Keep `CONTENT_WORKFLOW_ENABLED=true`.
2. Back up the database and run `alembic upgrade head`, including `c02_research_settings`. For SQL installations, apply the [inventory schema](content-workflow-schema.sql) if missing, then `python -m migrations.migration_script --file 010_content_research_settings.sql`. Use one migration method; migrations never run at app startup.
3. Optional: preview bundled topics with `python -m app.services.content_seed`; add `--apply` to import them. This preserves existing work and does not publish articles.
4. Open **Settings -> Research Sources** in admin to edit the reusable source groups and research instructions. Your ExplainIT defaults apply automatically to new research runs for both providers. Per-topic **Additional source URLs** are optional. Each run keeps its own settings snapshot; changing shared settings does not change previous research.

## Local development

Use a development database. Start the API and worker manually in separate terminals for each development session, from the backend directory:

1. Start FastAPI in the first PowerShell terminal:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

2. Start the worker in a second terminal in the same directory:

   ```powershell
   .\.venv\Scripts\python.exe -m app.services.content_worker
   ```

3. Keep both terminals open; both processes use the backend `.env`. Restart the worker after worker code or `.env` changes. Press **Ctrl+C** to stop each process.

Both providers retain all schema-valid research claims, including claims with empty source lists or URLs absent from the search results. Claims are not discarded for citation mismatches; the returned source catalog remains separate. Research readiness and advisory QA still apply.

Gemini logs the stage, finish/block reasons and token counts without raw response text. Empty, truncated or schema-invalid structured output gets one retry using the original inputs; research retries reuse the search results. Each Gemini call has a 120-second deadline.

## VPS deployment with Docker Compose

1. Add `content-worker` to your existing production `docker-compose.yml`. Reuse the `fastapi-app` image, `./env/fastapi-app-ei.env`, and its networks. Set `command: ["python", "-m", "app.services.content_worker"]` and `restart: unless-stopped`. The worker needs no exposed port or Nginx entry.
2. Add `content-worker` to `fastapi-app.depends_on` so starting only the API also starts the worker. Remove any previous standalone worker deployment before switching.
3. Enable Docker at server boot once: `sudo systemctl enable --now docker`.
4. After applying migrations, run these from your production Compose directory:

   ```sh
   docker compose config --quiet
   docker compose up -d --pull always
   docker compose ps
   docker compose logs --tail=100 content-worker
   ```

The same command updates all apps and starts the worker on future deployments. Existing worker containers restart with Docker unless explicitly stopped; after `down`, run `up` again. For a standalone backend deployment from this repository, [compose.yaml](../compose.yaml) starts the API and worker using `.env` with `docker compose up -d --build`.
