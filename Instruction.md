# Backend maintenance

Run from the backend directory. See [README](README.md) for setup/startup, [Codespaces](.devcontainer/README.md), and [worker deployment](docs/content-workflow.md#vps-deployment-with-docker-compose).

## Migrations

Register new models in `app/db/models/__init__.py`. Back up the database and review generated changes before applying them. Use the installation's existing migration method.

Alembic uses `ALEMBIC_DATABASE_URL`:

The existing migration environment uses a synchronous engine. Use
`postgresql+psycopg2://` for its URL, targeting the same database as the API's
`DATABASE_URL`. Keep normal URL percent-encoding in `.env`; `alembic/env.py`
handles the extra escaping required by Alembic's configuration parser.

```sh
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
```

SQL workflow:

```sh
uv run python -m migrations.generate_sql_from_models
uv run python -m migrations.migration_script --file REVIEWED_FILE.sql
```

The generator inspects the database and writes new tables/columns to `migrations/history_sql_mig`; it is not a complete schema diff. Replace `REVIEWED_FILE.sql` with the reviewed filename. The runner uses `ALEMBIC_DATABASE_URL` or `DATABASE_URL`, checks `DB_NAME`, and commits each file with its `schema_migrations` entry. Without `--file`, it applies all untracked files. SQL and Alembic histories are separate; do not apply equivalent changes twice.

## Local Docker image

```sh
docker build -t explainit-fastapi:local .
docker run --rm --env-file .env -e PORT=10000 -p 8000:10000 explainit-fastapi:local
```

Open <http://localhost:8000>. `PORT` sets Gunicorn's container port; `-p` maps the host port. This starts only the API. For a shell:

```sh
docker run -it --rm --env-file .env explainit-fastapi:local /bin/bash
```
