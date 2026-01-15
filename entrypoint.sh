#!/bin/sh
set -e

PORT=${PORT:-10000}

exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w ${WORKERS:-4} \
  -b 0.0.0.0:$PORT
