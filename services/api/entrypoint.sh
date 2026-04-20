#!/bin/sh
set -e

echo "Running database migrations..."
cd /app/services/api && uv run alembic upgrade head

echo "Starting API server..."
exec "$@"
