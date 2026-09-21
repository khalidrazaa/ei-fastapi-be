# Codespaces

Create a Codespace from the backend repository after committing this directory.
Setup uses Python 3.12 from `.python-version` and Node 24 from both frontend
Dockerfiles. It clones missing sibling repositories beside the backend and installs
dependencies using `uv.lock` and each `package-lock.json`. Existing sibling folders
are reused without pulling or resetting them. GitHub may request read access to the
sibling repositories when creating the Codespace.

Open `blogging system.code-workspace` using **File > Open Workspace from File** to
see all three repositories. No changes to the workspace file are needed.

Configure development environment variables or Codespaces secrets for databases,
API keys, and frontend API URLs before starting the apps. Setup does not provision
databases or copy local secrets. For browser API requests, use the backend's
forwarded Codespaces URL and configure allowed frontend origins as needed.

Run these commands in three separate terminals, starting in the backend directory:

```bash
# Backend: port 8000
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# Public UI: port 3000
cd ../ei-ui-nextjs
npm run dev -- --hostname 0.0.0.0 --port 3000
```

```bash
# Admin UI: port 3001 (avoids the public UI's default port)
cd ../ei-admin-ui-nextjs
npm run dev -- --hostname 0.0.0.0 --port 3001
```

All three ports are forwarded and labeled in the **Ports** panel. Apps are started
manually after environment configuration. For backend Playwright scraping features,
run `uv run playwright install --with-deps chromium` from the backend directory.
