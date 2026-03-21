#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Load nvm if present (needed when npm isn't in system PATH) ─────────────────
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

# ── Verify node is available ───────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "  ERROR: node not found. Run ./setup.sh first."
  exit 1
fi

echo ""
echo "  ALM Inventory Tracker"
echo "  ====================="
echo "  Node $(node -v) | $(python3 --version 2>&1)"
echo ""

# ── Backend ───────────────────────────────────────────────────────────────────
cd "$ROOT/backend"
source venv/bin/activate 2>/dev/null || {
  echo "  Venv not found. Run ./setup.sh first."
  exit 1
}

uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  Backend:  http://localhost:8000  (PID $BACKEND_PID)"

# ── Frontend ──────────────────────────────────────────────────────────────────
cd "$ROOT/frontend"

if command -v bun &>/dev/null; then
  bun run dev &
else
  npm run dev &
fi
FRONTEND_PID=$!
echo "  Frontend: http://localhost:5173  (PID $FRONTEND_PID)"
echo ""
echo "  Open http://localhost:5173 in your browser"
echo "  Press Ctrl+C to stop both servers"
echo ""

# ── Cleanup on exit ───────────────────────────────────────────────────────────
trap "echo ''; echo '  Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; deactivate 2>/dev/null; exit 0" INT TERM

wait
