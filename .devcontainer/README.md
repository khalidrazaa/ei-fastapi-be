# Codespaces

Create a Codespace from this backend repository. It uses Python 3.12 and Node 24. [setup.sh](setup.sh) clones missing sibling frontends, runs `uv sync --locked` and `npm ci`, and preserves existing folders without pulling/resetting. GitHub may request sibling repository read access.

Open [blogging system.code-workspace](../blogging%20system.code-workspace). Configure development databases, API keys, frontend API URLs, and allowed origins; setup provisions no databases and copies no secrets. Browser requests need the backend's forwarded Codespaces URL.

Start each command in a separate terminal from the backend directory:

```sh
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```sh
uv run python -m app.services.content_worker
```

```sh
cd ../ei-ui-nextjs
npm run dev -- --hostname 0.0.0.0 --port 3000
```

```sh
cd ../ei-admin-ui-nextjs
npm run dev -- --hostname 0.0.0.0 --port 3001
```

Apps start manually; ports 8000/3000/3001 are labeled in the **Ports** panel. See [worker restart notes](../docs/content-workflow.md#local-development) and [migrations](../Instruction.md#migrations). For Playwright scraping, install Chromium once with `uv run playwright install --with-deps chromium`.
