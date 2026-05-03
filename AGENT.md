## Project Overview

This repository is a YouTube Trend Intelligence and Blogging System.

### Core Idea
- Fetch trending and niche-based YouTube videos using the YouTube API
- Analyze videos to compute a virality score
- Identify trends that are viral or likely to go viral
- Generate content ideas and articles from trends
- Serve content through multiple frontend applications

---

## System Architecture

This is a multi-application system.

### Current Applications
- `ei-fastapi-be` - Backend API and background processing (FastAPI)
- `ei-ui-nextjs` - Public content UI (Next.js)
- `ei-admin-ui-nextjs` - Admin dashboard UI (Next.js)

### Future Applications
- Additional UI apps may be added over time as the platform grows
- References to "future-apps" describe planned expansion, not a required existing folder in this repo

---

## Core Domain Concepts

### 1. Niche
- A niche contains multiple keywords
- Each niche can be scanned independently
- Scanning fetches relevant YouTube videos

### 2. Trend Detection
- Videos are evaluated based on:
  - views
  - engagement
  - growth velocity
- A virality score is calculated

### 3. Idea Generation
- Trends -> Ideas -> Articles
- Used for blogging and content creation

---

## Backend: `ei-fastapi-be`

### Folder Structure Overview

```text
ei-fastapi-be/
├── alembic/						# Alembic config and versions
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── *_migration_files.py
│
├── migrations/						# SQL/history migrations
│   ├── generate_sql_from_models.py
│   ├── migration_script.py
│   └── history_sql_mig/
│
├── app/
│   ├── main.py						# Entry point
│   │
│   ├── api/
│   │   ├── router.py
│   │   ├── admin/
│   │   ├── auth/
│   │   ├── niche/
│   │   ├── trend_keyword/
│   │   └── youtube/
│   │
│   ├── clients/
│   │   └── youtube_client.py		# External API clients
│   │
│   ├── core/						# Config and security
│   │   ├── config.py
│   │   └── security.py
│   │
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   ├── schema.sql
│   │   ├── mongodb.py
│   │   ├── models/
│   │   └── query/
│   │
│   ├── generated/					# Generated artifacts/helpers
│   │   └── blogs.json
│   │
│   ├── scheduler/					# Background jobs and scheduler startup
│   │   ├── jobs.py
│   │   └── scheduler.py
│   │
│   ├── schemas/					# Pydantic schemas
│   │   ├── admin_user.py
│   │   ├── article.py
│   │   ├── auth.py
│   │   ├── email_otp.py
│   │   ├── keyword.py
│   │   ├── niche.py
│   │   ├── trends.py
│   │   ├── trend_video.py
│   │   └── youtube.py
│   │
│   ├── services/
│   │   ├── admin_service.py
│   │   ├── auth_service.py
│   │   ├── gemini_service.py
│   │   ├── niche_service.py
│   │   ├── trend_scrape.py
│   │   ├── trend_video.py
│   │   ├── analyzer/
│   │   │   ├── trend_analyzer.py
│   │   │   ├── trend_discovery_service.py
│   │   │   └── idea_generator.py
│   │   └── scanner/
│   │       ├── niche_scanner.py
│   │       └── youtube_scan_service.py
│   │
│   └── utils/						# Helper
│       ├── cookies.py
│       └── email.py

```

---

## Backend Architecture Rules

### Layer Responsibilities

| Layer | Responsibility |
|---|---|
| API | Request/response handling only |
| Services | Business logic |
| Query | Database interaction |
| Models | Database schema |
| Schemas | Validation |

### Mandatory Flow

`API -> Service -> Query -> Database`

### Strict Rules

- Never put business logic inside API routes
- Never access the database directly from routes
- Never bypass the service layer without a strong existing pattern
- Always follow the layered architecture used in the codebase

---

## API Rules

- Base path: `/v1/api`
- Follow REST principles
- Reuse existing endpoints when possible
- Do not create duplicate APIs

### Standard Response Format

Use the existing endpoint response patterns in the codebase. Prefer consistency with current routes over inventing a new wrapper format.

---

## YouTube Integration

### Key Components

- `app/clients/youtube_client.py`
  - Handles external YouTube API calls
- `app/services/scanner/youtube_scan_service.py`
  - Orchestrates scanning flow
- `app/services/scanner/niche_scanner.py`
  - Runs scans for specific niches
- `app/services/trend_scrape.py`
  - Fetches trending video data

---

## Analyzer System

Located in: `app/services/analyzer/`

### Responsibilities
- Trend scoring
- Trend detection
- Idea generation

### Key Files
- `trend_analyzer.py`
- `trend_discovery_service.py`
- `idea_generator.py`

---

## Scheduler

Located in: `app/scheduler/`

Used for:
- periodic scanning
- automated trend updates
- startup scheduler registration

---

## Database

The backend currently uses more than one data store/integration:

- PostgreSQL with SQLAlchemy
- Alembic migrations
- MongoDB integration for part of the system

### Rules
- Always use migrations for relational schema changes
- Do not make undocumented manual database changes
- Check the existing SQL and MongoDB access patterns before adding new persistence logic

---

## Frontend: `ei-ui-nextjs`

### Structure

```text
ei-ui-nextjs/
`-- src/
    |-- app/          # Next.js App Router
    |-- components/   # UI components
    `-- types/        # TypeScript types
```

### Responsibilities

- Render public articles and content
- Fetch data from backend APIs
- Manage routing and UI state

### Frontend Rules

- Do not hardcode API URLs
- Use environment variables where needed
- Handle loading and error states
- Keep components reusable

---

## Frontend: `ei-admin-ui-nextjs`

## Purpose

Internal tool for managing system data and operations

### Structure

```text
ei-admin-ui-nextjs/
`---src
    |   proxy.ts
    |   
    +---app								# Next.js App Router
    |   |   favicon.ico
    |   |   globals.css
    |   |   layout.tsx
    |   |   page.tsx
    |   |   tailwindcss
    |   |   
    |   +---(auth)
    |   |   \---login
    |   |           page.tsx
    |   |           
    |   \---(protected)
    |       |   layout.tsx
    |       |   
    |       +---dashboard
    |       |       page.tsx
    |       |       
    |       +---niches
    |       |       page.tsx
    |       |       
    |       \---trends
    |               page.tsx
    |               
    +---components						# UI components
    |   \---ui
    |           Button.tsx
    |           ConfirmModal.tsx
    |           Toggle.tsx
    |           VideoCard.tsx
    |           
    +---lib								# Shared client helpers/utilities
    |   |   api.ts
    |   |   
    |   +---services
    |   |       auth.ts
    |   |       keyword.ts
    |   |       niche.ts
    |   |       scaned-trends.ts
    |   |       
    |   \---utils
    |           formatters.ts
    |           
    \---types							# TypeScript types
            css.d.ts
            types.ts
```

### Responsibilities

- Provide the admin dashboard experience
- Manage admin-side content and trend workflows
- Integrate with backend admin APIs

### Frontend Rules

- Do not hardcode API URLs
- Use environment variables where needed
- Keep shared admin logic in reusable utilities/components
- Match existing app patterns before introducing new abstractions

---

## Global Rules

### Never Modify

- `.next`
- `node_modules`
- generated build outputs

### Never Do

- Duplicate logic without need
- Break API contracts
- Introduce unused code
- Mix responsibilities across layers

---

## Debugging Strategy

When debugging issues:

1. Identify the layer:
   - frontend
   - backend
   - API contract
   - data/storage integration

2. Trace the flow:

`UI -> API -> Service -> Query/Client -> DB or external API`

3. Validate:
- request payload
- response shape
- schema mismatch
- environment/config issues
- database or scheduler side effects

4. Fix the root cause, not just the symptom

---

## Common Tasks for Codex

- Fix API integration issues
- Add features end-to-end
- Debug scanning failures
- Improve trend scoring
- Refactor services safely
- Add endpoints without duplicating behavior
- Keep docs and code structure aligned

---

## Development Philosophy

- Prefer small, safe changes
- Reuse existing code patterns
- Maintain clean separation of concerns
- Read existing code before modifying
- Verify structure from the repo instead of assuming

---

## Run Commands

### Backend

```bash
uvicorn app.main:app --reload
```

### Frontend Apps

```bash
npm run dev
```

Run frontend commands from the specific app directory you want to start.

---

## Codex Working Guidelines

- Always analyze related files before making changes
- Do not assume structure; verify it
- Prefer modifying existing files over creating new ones
- Explain changes before applying them
- Avoid large rewrites unless necessary
- Keep this file aligned with the real repo structure as the system evolves
