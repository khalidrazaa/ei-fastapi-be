# =========================
# Builder stage
# =========================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache-dir .

# =========================
# Runtime stage
# =========================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"


WORKDIR /app

# Only runtime deps (NO build tools)
RUN apt-get update && apt-get install -y \
    libpq5 \
    libssl3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python packages only
COPY --from=builder /usr/local /usr/local
COPY --from=builder /root/.local /root/.local

# Install Playwright browsers (runtime)

RUN uv pip install playwright \
    && uv run playwright install --with-deps

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w ${WORKERS:-2} \
  --bind 0.0.0.0:${PORT:-8000} \
  --access-logfile - \
  --error-logfile - \
  --log-level info"]