#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Ensure mac startup scripts are executable
chmod +x "$PROJECT_DIR/run_web_mac.sh" "$PROJECT_DIR/run_web_mac.command" 2>/dev/null || true

echo "[1/5] Checking Python3..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found. Please install Python 3.10+ first."
  exit 1
fi

echo "[2/5] Creating virtual environment (.venv-mac)..."
if [ ! -d ".venv-mac" ]; then
  python3 -m venv .venv-mac
fi

# shellcheck disable=SC1091
source .venv-mac/bin/activate

echo "[3/5] Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[4/5] Preparing config..."
if [ ! -f "config.json" ]; then
  cp config.example.json config.json
  echo "Created config.json from config.example.json"
  echo "Please edit config.json with your real settings, then rerun this script."
  exit 1
fi

if [ -n "${WEB_PORT:-}" ]; then
  echo "[5/5] Starting web app on http://127.0.0.1:${WEB_PORT}"
  python app.py --port "${WEB_PORT}" --debug
else
  echo "[5/5] Starting web app (port from config.json web_port or APP_PORT/PORT, default 5000)"
  python app.py --debug
fi
