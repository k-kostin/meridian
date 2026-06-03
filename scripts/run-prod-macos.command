#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [ ! -x "./.venv/bin/python" ]; then
    echo "Python virtualenv not found: $PROJECT_ROOT/.venv"
    echo "Create it first and install dependencies."
    exit 1
fi

export DJANGO_DEBUG="${DJANGO_DEBUG:-0}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-*}"
export WAREHOUSE_DEMO_MODE=0

./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py runserver 0.0.0.0:8000 --insecure
