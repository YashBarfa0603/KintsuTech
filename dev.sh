#!/usr/bin/env bash
# KintsuTech — Start both Backend (FastAPI) and Frontend (Next.js) simultaneously
# Press Ctrl+C to stop both processes cleanly.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo ""
  echo "Shutting down KintsuTech processes..."
  kill 0
}

trap cleanup SIGINT SIGTERM EXIT

echo "=================================================="
echo "  KintsuTech — Detect. Adapt. Recover."
echo "=================================================="
echo " Starting Backend on http://localhost:8000"
echo " Starting Frontend on http://localhost:3000"
echo " Press Ctrl+C at any time to stop both."
echo "=================================================="

# Start backend
(cd "$ROOT_DIR/backend" && uv run uvicorn app.main:app --reload --port 8000) &

# Start frontend
(cd "$ROOT_DIR/frontend" && npm run dev) &

# Wait for both processes
wait
