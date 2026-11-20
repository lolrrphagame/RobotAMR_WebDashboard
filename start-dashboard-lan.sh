#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$PROJECT_DIR/backend/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo 'ERROR: backend/.venv missing. Follow README project-local installation steps.' >&2
  exit 1
fi
cd "$PROJECT_DIR/backend"
exec env -u PYTHONPATH "$PYTHON_BIN" -m app.lan_server "$@"
