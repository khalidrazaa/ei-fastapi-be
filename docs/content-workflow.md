# Inventory article workflow

Create a topic, save its brief, run research, then generate an article. Generation automatically queues QA. Review the evidence and article, save it to Drafts, then publish manually in the article editor. Choose OpenAI or Gemini in the workspace; QA is advisory and does not enforce publication approval.

Admins can also write directly from **Drafts -> New Draft**. Saving creates a draft through authenticated `POST /v1/admin/articles` with a title, unique slug, and content (which may be empty), plus optional article metadata. New articles always begin as drafts; publishing remains a separate save in the editor. Manual drafts do not require a topic or AI generation.

## Editorial policy and SVG generation

The provider-neutral rules live in `app/editorial/article-workflow.md`. Research jobs
snapshot the policy text, version, and SHA-256 alongside the research settings;
generation, fixes, and automatic QA inherit that snapshot. Later policy edits do
not rewrite existing runs. A legacy run without a policy uses the current bundled
policy when next processed. Start fresh research to adopt new rules deliberately.

New articles use 400–800 main-body words, excluding H1, image markup and final
Sources. Main headings, tables and captions count. Sources are assembled from the
research catalog with checked dates; body URLs and invented citations are flagged
by QA. Vendor rate comparisons, advertised discounts, and price break-even claims
are outside scope; billing units against workload and operating effort remain in scope.

For a requested diagram, writing supplies one `diagram.svg` placeholder. A separate
provider call creates a bounded sequence, stages, or comparison plan. The worker
renders native SVG, sanitizes it, and runs Chromium paint and text-bounds checks
with network and page scripts disabled. Rendering failures fail the stage with a
retryable operator message rather than silently omitting the asset. The plan,
SVG, and visual-check results stay in the generation run outside DraftPayload.
Automated QA compares the plan and labels with the prose; semantic correctness
and real site/mobile appearance still require human review. There is no PNG artifact.

Workspace responses include only diagrams referenced by that topic's versions.
The admin preview displays sanitized SVG through an image blob, never inline HTML.
Edited versions can retain a previously generated asset. Save to Drafts stores the
SVG through the existing article media tables and rewrites the Markdown to its
immutable media URL. Published articles retain the existing overwrite protections.
This change adds no database tables or migration, but the existing article-media
schema must already be installed. Historical Mermaid versions remain viewable;
regenerate them to obtain the new SVG workflow.

For local workers install the browser once with
`python -m playwright install chromium --only-shell` (Linux installations may also
need `--with-deps`). The Dockerfile already installs Chromium and dependencies.
Configure `MEDIA_ROOT` and `MEDIA_PUBLIC_BASE_URL` as for manual media uploads;
persist and share MEDIA_ROOT wherever media is served. Draft saving writes the
files; diagram generation itself stores artifacts in the database, so workers do
not need a shared local artifact directory. Restart the API and worker, and rebuild
the admin after deploying these code changes. No paid provider or production job
is run by the isolated test suite.

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
