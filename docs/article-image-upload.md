# Markdown articles with diagram images

The admin editor has one file selector for Markdown and SVG/PNG diagrams. It reads
and previews the selected files locally, lets the author review metadata and image
matching, then saves the article and images in one request. No preliminary draft
save or separate image-upload step is required. Files stay on the existing VPS.

## API contract

`POST /v1/admin/articles/import` creates a draft. `PUT
/v1/admin/articles/{article_id}/import` updates an existing article. Both use the
existing admin cookie/Bearer authentication and cookie Origin checks, and accept
multipart form fields:

| Field | Value |
| --- | --- |
| `article` | JSON string validated as `ArticleDraftCreate` or `ArticleUpdate`; its reviewed `content` is authoritative |
| `manifest` | JSON object mapping a Markdown image destination to one uploaded filename; defaults to `{}` |
| `request_id` | UUID generated once for a save attempt and retained for retries |
| `images` | Repeated file part, zero or more SVG/PNG images with unique filenames |

For example, `{"images/flow.svg":"flow.svg"}` maps
`![How requests flow](images/flow.svg)` to `flow.svg`. Exact paths and unique
basenames, including their extension, match without a manifest. When neither
matches, local SVG/PNG references can use the same diagram name in the other
format: `images/flow.png` can match `flow.svg`, and vice versa. Matching prefers
the same path without its extension, then a unique basename without its extension;
extension recognition is case-insensitive. Ambiguous alternatives require an
explicit mapping. Explicit mappings take priority and can replace existing
HTTP(S) or same-origin image URLs. Every uploaded image must be referenced by the
article, and every local image reference must be matched. Relative paths are
logical references; generated UUID filenames determine storage paths.

The service parses real Markdown image tokens, including reference-style images.
It leaves code blocks, inline code, ordinary links and unrelated source unchanged.
Reference images being replaced become inline images while retaining their alt
markup and title. Existing external images remain unchanged unless mapped.
Successful responses use the existing `ArticleResponse`, with permanent media
URLs already inserted into `content`. Updates retain the existing
`expected_updated_at` concurrency check. Ordinary article updates also reject
unresolved local diagram references when publishing.

Validation failures return 400 (or 422 for invalid form JSON/schema), missing
articles return 404, and request-ID reuse with different content returns 409.
Storage failures return 503. The client should retain the selected files and
reviewed editor contents after errors. A retry with the same ID and identical
article, manifest and file bytes returns the saved response without creating a
second article or second image set. A newly edited save needs a new request ID.

## Image validation and delivery

Defaults are 10 images, 5 MiB per image, 50 MiB combined article/manifest/images, 2 MiB Markdown,
and 24 million pixels per image. Backend limits are configurable through
`MEDIA_MAX_IMAGES`, `MEDIA_MAX_IMAGE_BYTES`, `MEDIA_MAX_BATCH_BYTES` and
`MEDIA_MAX_PIXELS`; keep frontend limits aligned if changing them.

PNG validation checks the signature, chunk CRCs, dimensions, encoding and bounded
scanline decompression, including Adam7. Animated PNG is unsupported. SVG is
parsed without network access, external entities or DTD loading, validated against
an explicit native SVG element/attribute/style policy, then serialized. Safe text,
gradients, markers, clipping paths and internal `#id` references are preserved.
Scripts, event handlers, external resources, CSS imports/escapes/comments,
unsupported XML and HTML `foreignObject` labels are rejected with an explanation.
In draw.io, use **Convert Labels to SVG** for supported formatted labels, or
export PNG. Unsupported content is never silently stripped from diagram labels.

`GET /v1/media/articles/{article_id}/{uuid.svg-or-png}` returns the stored image
with its verified MIME type, `nosniff`, restrictive sandbox CSP, cross-origin image
permission and a one-year immutable cache policy. These browser-public,
unguessable URLs work without admin cookies or the public article API key. This
includes images associated with drafts: draft media is not a private document
store. Article APIs continue to enforce normal draft/publication access rules.
Render uploaded SVG using an image element; never inject its markup or embed it as
an active document.

## VPS setup and rollout

1. Back up PostgreSQL and review the migration. Apply **one** history using the
   installation's existing method:

   ```sh
   uv run alembic upgrade c04_article_images
   ```

   ```sh
   uv run python -m migrations.migration_script --file 012_article_images.sql
   ```

   Do not run both. API startup does not apply migrations.

2. Set the public API base in the backend environment, including `/v1`:

   ```dotenv
   MEDIA_PUBLIC_BASE_URL=https://YOUR-API-HOST/v1
   MEDIA_HOST_PATH=/srv/explainit/media
   ```

   `compose.yaml` bind-mounts `MEDIA_HOST_PATH` into the API at
   `/var/lib/explainit/media` and sets `MEDIA_ROOT` accordingly. Its local default
   is `./var/media`. Give the API process permission to write the host directory.
   For the existing production `fastapi-app` Compose service, add the same bind
   mount and `MEDIA_ROOT` environment setting to that service. Keep the media
   directory outside release checkouts and disposable container layers.

3. Route `/v1/media/` to the API using the existing reverse proxy. Do not expose
   the entire storage root: `.staging` is private. Proxy responses preserve media
   MIME and security headers. Set the proxy request-body limit above the maximum
   image batch plus article/form overhead, for example `client_max_body_size 55m;`
   for the defaults. The proxy bound is needed in addition to per-file validation
   because multipart files are spooled before the route runs. Configure temporary
   disk space and request timeouts for that limit.

4. Deploy/restart the backend after migrating and configuring the mount, then
   deploy the updated admin and reader frontends. Import a Markdown file with SVG
   and PNG, save, reopen, and inspect the public media URLs from another browser.
   Recreate the API container and confirm the files persist.

5. Publish the article and rebuild/deploy the public frontend. The reader uses a
   build-time article snapshot, so publishing or editing an article does not
   immediately refresh its deployed page.

No S3 credentials, object storage service, media worker, or frontend filesystem
writes are needed.

## Persistence, recovery and backups

Files are validated in `MEDIA_ROOT/.staging/{random-id}`. The service opens a DB
transaction, claims the unique import request ID, saves article/image records,
moves UUID-named files into `MEDIA_ROOT/articles/{article_id}`, flushes files and
directory metadata, then commits. A failure rolls back DB changes and compensates
files when a fresh transaction confirms that the request did not commit. A lost
connection during commit may leave files deliberately retained until retry or
reconciliation. PostgreSQL and the filesystem do not form a single atomic store.

Inspect interrupted-import leftovers with:

```sh
docker compose exec api python -m app.services.article_media_reconcile
```

The default is a dry run. Review its output, then add `--apply` to remove only
unrecorded final files and staging directories older than 24 hours. The tool also
reports recorded files missing from disk. It never removes a recorded image,
including retained images for deleted articles. Do not run the API with a different
database or filesystem root while reconciling.

Replacing an image creates a new immutable URL. Removing a Markdown reference or
deleting an article retains its image rows and files because existing deployed
static pages and browser caches may still use them. `article_images.article_id`
becomes null on article deletion; `original_article_id` preserves its URL. There
is no automatic deletion policy for recorded media. Retire recorded assets only
after confirming that retained deployments and backups no longer need them.

Back up PostgreSQL (including `article_images` and `article_imports`) and the full
persistent media directory together. Restore them together and preserve the public
media origin/path. A database backup alone cannot restore diagrams. A schema
downgrade deliberately leaves filesystem files untouched.

## Missing migration troubleshooting

If article imports or media requests return HTTP 503 with
`012_article_images.sql or c04_article_images`, the API database is missing an
article-upload table or required column. The upload is rolled back and temporary
files are cleaned up; no automatic schema changes are attempted. Other database
failures are not relabeled as migration problems.

Back up the database, confirm the migration connection targets the same database
as the running API, and apply the reviewed migration using the installation's
existing history: `uv run alembic upgrade c04_article_images` for Alembic, or
`uv run python -m migrations.migration_script --file 012_article_images.sql` for
SQL-history installations. Use one method only, then retry the same save. If the
migration is already recorded but tables/columns are absent, investigate the
database target or schema drift before rerunning creation statements. Restarting
the API alone does not apply a migration.

If `DATABASE_URL` uses an SSH tunnel, its `localhost` address can still reach the
live VPS database. Check the actual database name and migration history before
changing schema. A separately configured `ALEMBIC_DATABASE_URL` can point at a
different database; running its default upgrade will not repair the API target.

## Validation

`uv run python -m unittest discover -s tests -p 'test_article_media*.py'` exercises
SVG/PNG policy, Markdown matching, public image headers, real isolated persistence,
all-or-nothing failure, retry receipts, uncertain commit recovery, concurrent-save
checks, retained images after deletion, missing migrations and reconciliation selection. The full
backend suite remains `uv run python -m unittest discover -s tests`.
