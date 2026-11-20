#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
if [[ "${APP_MODE:-local}" != local ]]; then
  echo 'ERROR: This launcher requires APP_MODE=local; LAN is disabled until Phase 5B.2.' >&2
  exit 1
fi
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --no-build ) ]]; then
  echo 'Usage: ./start-dashboard.sh [--no-build]' >&2; exit 1
fi
PYTHON_BIN="$PROJECT_DIR/backend/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo 'ERROR: backend/.venv missing. Follow README production installation instructions.' >&2; exit 1
fi
if ! env -u PYTHONPATH "$PYTHON_BIN" -c 'import uvicorn, fastapi' ; then
  echo 'ERROR: Install project dependencies: backend/.venv/bin/python -m pip install -r backend/requirements.lock.txt' >&2; exit 1
fi
if [[ $# -eq 0 ]]; then
  if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
    if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
      source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
      nvm use 24
    fi
  fi
  if ! command -v npm >/dev/null || ! command -v node >/dev/null; then
    echo 'ERROR: Node.js 24/npm required to build. Load nvm or use --no-build with an existing build.' >&2; exit 1
  fi
  if [[ ! -x frontend/node_modules/.bin/vite ]]; then
    echo 'ERROR: Frontend dependencies missing. Run npm --prefix frontend ci.' >&2; exit 1
  fi
  npm --prefix frontend run build
fi
# exec preserves signals/PID: no hidden background process, PID file, reload child or extra worker.
cd "$PROJECT_DIR/backend"
exec env -u PYTHONPATH "$PYTHON_BIN" -m app.local_server
