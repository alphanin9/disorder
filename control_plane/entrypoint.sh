#!/bin/sh
set -e

alembic -c /app/control_plane/alembic.ini upgrade head

exec uvicorn control_plane.app.main:app --host 0.0.0.0 --port 8000
