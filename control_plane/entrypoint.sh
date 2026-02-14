#!/bin/sh
set -e

MAX_ATTEMPTS=60
ATTEMPT=1

until alembic -c /app/control_plane/alembic.ini upgrade head; do
  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo "alembic migration failed after ${MAX_ATTEMPTS} attempts"
    exit 1
  fi
  echo "alembic attempt ${ATTEMPT}/${MAX_ATTEMPTS} failed, retrying in 2s"
  ATTEMPT=$((ATTEMPT + 1))
  sleep 2
done

exec uvicorn control_plane.app.main:app --host 0.0.0.0 --port 8000
