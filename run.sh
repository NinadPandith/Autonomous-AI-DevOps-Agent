#!/usr/bin/env bash
# CodeSentinel - one-command launcher for macOS / Linux:  ./run.sh
# First run installs everything; later runs start in seconds. Ctrl+C stops both servers.
# Needs: Python 3.12+ and Node.js 20+.
set -euo pipefail
cd "$(dirname "$0")"

API_PORT=8010
WEB_PORT=5180
WEB_URL="http://localhost:$WEB_PORT"

echo
echo "  CodeSentinel - autonomous AI DevOps agent"
echo "  -----------------------------------------"

PY=""
for candidate in python3.13 python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || { echo "  [!!] Python 3.12+ is required: https://www.python.org/downloads/"; exit 1; }
echo "  [ok] Python found ($PY)"

command -v node >/dev/null 2>&1 &&
  node -e 'process.exit(+process.versions.node.split(".")[0] >= 20 ? 0 : 1)' ||
  { echo "  [!!] Node.js 20+ is required: https://nodejs.org/"; exit 1; }
echo "  [ok] Node.js found"

# Backend: virtualenv + dependencies (reinstalled only when requirements.txt changes)
VENV_PY="backend/.venv/bin/python"
[ -x "$VENV_PY" ] || { echo "  [..] Creating the Python environment - first run only"; "$PY" -m venv backend/.venv; }
if ! cmp -s backend/requirements.txt backend/.venv/requirements.installed; then
  echo "  [..] Installing backend packages - this can take a few minutes"
  "$VENV_PY" -m pip install --disable-pip-version-check -q -r backend/requirements.txt
  cp backend/requirements.txt backend/.venv/requirements.installed
fi
echo "  [ok] Backend ready"

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo
  echo "  CodeSentinel uses Google Gemini - free, no credit card: https://aistudio.google.com"
  echo "  Press Enter to skip (recorded runs still work; add the key later in backend/.env)."
  read -r -p "  Paste your Gemini API key: " key || key=""
  if [ -n "$key" ]; then
    "$VENV_PY" - "$key" <<'EOF'
import re, sys
from pathlib import Path
p = Path("backend/.env")
p.write_text(re.sub(r"(?m)^GEMINI_API_KEY=.*$", "GEMINI_API_KEY=" + sys.argv[1].strip(), p.read_text()))
EOF
    echo "  [ok] Key saved to backend/.env (never uploaded to GitHub)"
  fi
fi

# Frontend: packages (reinstalled only when package-lock.json changes) + .env
if ! cmp -s frontend/package-lock.json frontend/node_modules/.package-lock.installed; then
  echo "  [..] Installing dashboard packages - first run only"
  (cd frontend && npm install --no-audit --no-fund --loglevel=error)
  cp frontend/package-lock.json frontend/node_modules/.package-lock.installed
fi
[ -f frontend/.env ] || cp frontend/.env.example frontend/.env
echo "  [ok] Dashboard ready"

echo
echo "  Starting the API (port $API_PORT) and the dashboard (port $WEB_PORT)..."
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --port "$API_PORT") &
API_PID=$!
(cd frontend && exec npm run dev -- --clearScreen false) &
WEB_PID=$!
trap 'echo; echo "  Stopping CodeSentinel..."; kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM EXIT

for _ in $(seq 1 60); do
  curl -fs "$WEB_URL" >/dev/null 2>&1 && break
  sleep 1
done
echo
echo "  CodeSentinel is running: $WEB_URL   (API docs: http://localhost:$API_PORT/docs)"
echo "  Press Ctrl+C to stop."
if [ -z "${CODESENTINEL_NO_BROWSER:-}" ]; then
  (command -v open >/dev/null && open "$WEB_URL") || (command -v xdg-open >/dev/null && xdg-open "$WEB_URL") || true
fi
wait
