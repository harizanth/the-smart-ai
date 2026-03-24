#!/bin/bash

# ─── Jarvis Startup Script ────────────────────────────────────────────────────
# Starts all 3 services: token server, agent backend, and frontend
# Press Ctrl+C once to shut everything down cleanly.

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv/bin/activate"

echo ""
echo "  ╔══════════════════════════════╗"
echo "  ║       J.A.R.V.I.S  v1.0     ║"
echo "  ╚══════════════════════════════╝"
echo ""

# Trap Ctrl+C and kill all child processes
cleanup() {
  echo ""
  echo "  [Jarvis] Shutting down all services..."
  kill 0
  exit 0
}
trap cleanup SIGINT SIGTERM

# 1. Token server
echo "  [1/3] Starting token server on :8000..."
(source "$VENV" && python "$PROJECT_DIR/token_server.py") &

# 2. Agent backend
echo "  [2/3] Starting Jarvis agent..."
(source "$VENV" && python "$PROJECT_DIR/agent.py" dev) &

# 3. Frontend
echo "  [3/3] Starting frontend on :3000..."
(cd "$PROJECT_DIR/frontend" && npm run dev) &

echo ""
echo "  ✅ All services started."
echo "  🌐 Open: http://localhost:3000"
echo "  Press Ctrl+C to stop everything."
echo ""

# Wait for all background jobs
wait
