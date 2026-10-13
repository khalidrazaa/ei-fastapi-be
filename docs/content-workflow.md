# Inventory article workflow

The admin workflow is Topics → brief → Begin research → Generate article → automated QA → Save to Drafts → existing manual publishing. OpenAI is used for research/writing. Gemini and YouTube are not prerequisites. The retired transcript UI and its API endpoints have been removed. Drafts uses the inventory workspace. Historical database fields are retained.

## Deployment

1. Back up the database. Apply the additive `c01_content_workflow` Alembic migration through your existing deployment process (`alembic upgrade head`). For installations using the SQL migration runner, the equivalent SQL is in `docs/content-workflow-schema.sql`; register/apply it using that installation's migration history. Do not apply both methods to the same database. No migration runs at API startup.
2. Retain `OPEN_AI_KEY` (or `OPENAI_API_KEY`) on the backend only. Both names are accepted; within the same settings source, `OPENAI_API_KEY` takes precedence if both are set. Restart the API and content worker after changing environment settings. Set `CONTENT_RESEARCH_MODEL` and `CONTENT_WRITING_MODEL` to supported Responses API models available to the account; unset values reuse existing `OPENAI_DRAFT_MODEL`. Verify web-search support for the research model. Current SDK dependency includes Responses and structured parsing; integration uses `web_search` and Pydantic structured outputs.
3. Optional settings: `CONTENT_WORKFLOW_ENABLED=true`, `CONTENT_HOST=explainit.tech`, `CONTENT_MAX_SEARCH_CALLS=6`, `CONTENT_MAX_OUTPUT_TOKENS=10000`. Limits bound calls/output, not a guaranteed currency budget. Usage is recorded per run; failed requests can still incur provider charges.
4. Start API as usual. Start a separately supervised process from the backend directory: `python -m app.services.content_worker`. Do not put it inside every API worker. Database leases allow recovery after crashes; one active job per topic is enforced by an index. A process supervisor should restart failed workers.
5. Preview bundled seed import with `python -m app.services.content_seed`; run with `--apply` to import topics and the existing EXPLAINIT-001 draft. Existing IDs/work are preserved. This command does not publish or call OpenAI. Check the imported draft's dated claims before publishing.
6. Build/deploy admin and public apps. No new frontend dependencies are required. Safe flow rendering supports simple Mermaid TD/TB/LR nodes and edges, without directives or executable HTML. Unsupported diagrams display an explicit notice and their source for correction.

## Persistence and operations

PostgreSQL is the operational inventory. CSV imports add missing topics and never delete/update existing editorial work; edit existing topics in the UI. IDs are held in a permanent registry and are not reused after deletion. Topic deletion is allowed only without runs, versions, or articles; archive instead when history exists.

Research jobs retain the provider's research narrative, cited source URLs, checked timestamps, a structured claim ledger, gaps, and token usage. Evidence is provider-retrieved and must still receive human scrutiny; automated QA is not independent factual certification. The server does not fetch arbitrary URLs itself. Source suggestions go to the hosted search tool; pages are explicitly untrusted input. No API keys or provider error bodies are exposed in job failures.

Generation creates immutable workspace versions and automatically queues QA for that exact version. It does not create articles. Save to Drafts creates/updates one linked article transactionally, forces draft status, and checks the editor fingerprint. Duplicate saves of the same version are no-ops. Published articles cannot be overwritten by workspace generation. Manual publish/unpublish in the existing editor controls public visibility as before; inventory publication state and URL are derived from the linked article, so they stay consistent.

Cancelled running jobs stop at their completion boundary and discard their result; the provider may already be processing/billing. An expired ten-minute lease can be retried up to three times with a new fencing token; stale workers cannot commit. Jobs time out before their lease. UI stage buttons provide explicit retries. Production accounts/billing and live generated article quality must be validated in a controlled pilot.

Private briefs/research/QA stay out of article body. Import strips YAML, duplicate H1, and editorial handoff. The public API continues to serve only published articles for the requested host.

## Verification

Run backend unit tests with `python -m unittest discover -s tests`. New content tests use isolated SQLite and provider fixtures; SQLite does not validate PostgreSQL locking. Run the optional `CONTENT_TEST_DATABASE_URL` suite only against a disposable local database ending in `_test` to verify migration and locking. Never point it at production.

Run `npm test` and `npx tsc --noEmit` in admin; run `node --test tests/*.test.mjs` and `npx tsc --noEmit` in public. Before rollout, exercise two controlled live topics and review source support, specificity, diagram correctness, editing time, and cost.

Disable `CONTENT_WORKFLOW_ENABLED` if needed. Keep new tables/data; do not downgrade a migration with editorial work without a reviewed backup/restore plan. Existing articles/public reading do not depend on the new workflow being enabled.

## Admin page layout and metadata

Topics uses the shared sidebar layout: add/import/edit/archive/delete topics on the left; the selected topic's brief, research, generation and run history on the right. Drafts lists topics with generated versions or saved draft articles and shows the article, metadata, version history and QA. Published topics are excluded from the draft list.

OpenAI generates article text and editorial metadata together in one structured response, including SEO title, category/subcategory, keywords, language, schema type and Open Graph text. Older saved versions remain readable with default values for the new metadata fields. Publication state, host, canonical URL, dates and reading time are application-managed. Images are supplied in the article editor rather than invented by the language model. No Gemini metadata call or new database migration is required.

## Provider selection

Choose OpenAI or Gemini in the topic or draft workspace before starting a stage. Jobs pin the selection; automatic QA inherits the generation provider. Existing jobs default to OpenAI. There is no automatic provider fallback and no migration is needed.

Gemini uses GOOGLE_AI_STUDIO_API_KEY and CONTENT_GEMINI_MODEL (default gemini-2.5-flash). Research uses Google Search grounding, followed by a separate evidence-ledger extraction. Generation returns article and metadata together; QA uses the same editorial checks. Gemini search query counts are provider-controlled; CONTENT_MAX_SEARCH_CALLS is an OpenAI-only limit. Usage and Gemini search queries are retained. Live account access, quotas and generated quality require a pilot.

References: https://ai.google.dev/gemini-api/docs/google-search and https://ai.google.dev/gemini-api/docs/structured-output

## VPS deployment with Docker Compose

`compose.worker.yaml` runs the worker independently of the existing API/frontend stack. Run these commands from the backend repository on the VPS, with its production `.env` present:

```sh
docker compose -p explainit-content -f compose.worker.yaml config --quiet
docker compose -p explainit-content -f compose.worker.yaml up -d --build
docker compose -p explainit-content -f compose.worker.yaml logs --tail=100 -f content-worker
```

The worker uses the backend Dockerfile and the same database/API-key settings as FastAPI. It publishes no ports and runs no migrations. Repeat `up -d --build` when deploying changed worker code. Apply required migrations through the usual deployment process first.

The `unless-stopped` policy restarts a failed container and brings it back after Docker restarts unless it was explicitly stopped. Ensure the Docker daemon starts on VPS boot. `docker compose down` removes the service; run `up -d` to create it again. This policy supervises process exits, not model errors, exhausted quota, or database outages caught by the worker. Check logs and queue status.

This standalone setup assumes the configured database is reachable externally (as with the current Supabase configuration). If production uses a database container addressed by a Compose service name, put this worker service in the existing Compose project/network and adjust build/env-file paths instead. The actual VPS Compose file is not in this checkout, so it has not been changed.

Interrupted in-flight jobs may wait for their existing ten-minute lease before retrying. Avoid leaving the development worker connected to the production database once the VPS worker is active.

Docker reference: https://docs.docker.com/reference/compose-file/services/#restart
