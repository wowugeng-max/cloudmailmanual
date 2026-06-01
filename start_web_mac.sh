#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$PROJECT_DIR/run"
PID_FILE="$RUN_DIR/cloudmailmanual.pid"
LOG_FILE="$RUN_DIR/cloudmailmanual.log"

cd "$PROJECT_DIR"

resolve_port() {
  if [ -n "${WEB_PORT:-}" ]; then
    printf '%s\n' "$WEB_PORT"
    return 0
  fi

  if [ -f "config.json" ]; then
    python3 - <<'PY'
import json
try:
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    port = str(cfg.get("web_port", "") or "").strip()
    print(port if port.isdigit() and 1 <= int(port) <= 65535 else "5000")
except Exception:
    print("5000")
PY
    return 0
  fi

  if [ -n "${APP_PORT:-}" ]; then
    printf '%s\n' "$APP_PORT"
    return 0
  fi

  if [ -n "${PORT:-}" ]; then
    printf '%s\n' "$PORT"
    return 0
  fi

  printf '5000\n'
}

is_running() {
  local pid="${1:-}"
  [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

if [ "${1:-}" = "--print-port" ]; then
  resolve_port
  exit 0
fi

mkdir -p "$RUN_DIR"

echo "[1/6] Checking Python3..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found. Please install Python 3.10+ first."
  read -n 1 -s -r -p "Press any key to exit..."
  echo
  exit 1
fi

echo "[2/6] Creating virtual environment (.venv-mac)..."
if [ ! -d ".venv-mac" ]; then
  python3 -m venv .venv-mac
fi

# shellcheck disable=SC1091
source .venv-mac/bin/activate

echo "[3/6] Installing dependencies..."
if [ "${SKIP_DEP_INSTALL:-}" = "1" ]; then
  echo "Skipping dependency install because SKIP_DEP_INSTALL=1."
else
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

echo "[4/6] Preparing config..."
if [ ! -f "config.json" ]; then
  cp config.example.json config.json
  echo "Created config.json from config.example.json."
  echo "Please edit config.json with your real settings, then run this launcher again."
  read -n 1 -s -r -p "Press any key to exit..."
  echo
  exit 1
fi

PORT_VALUE="$(resolve_port)"

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if is_running "$OLD_PID"; then
    echo "[5/6] Cloud Mail is already running with PID $OLD_PID."
    echo "URL: http://127.0.0.1:${PORT_VALUE}"
    open "http://127.0.0.1:${PORT_VALUE}" >/dev/null 2>&1 || true
    read -n 1 -s -r -p "Press any key to close this window..."
    echo
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "[5/6] Starting Cloud Mail in the background..."
: > "$LOG_FILE"
if [ -n "${WEB_PORT:-}" ]; then
  nohup python app.py --host 127.0.0.1 --port "$WEB_PORT" >>"$LOG_FILE" 2>&1 &
else
  nohup python app.py --host 127.0.0.1 >>"$LOG_FILE" 2>&1 &
fi
APP_PID="$!"
echo "$APP_PID" > "$PID_FILE"

sleep 2
if ! is_running "$APP_PID"; then
  echo "Cloud Mail failed to start. Log:"
  tail -n 80 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  read -n 1 -s -r -p "Press any key to exit..."
  echo
  exit 1
fi

echo "[6/6] Started."
echo "PID: $APP_PID"
echo "URL: http://127.0.0.1:${PORT_VALUE}"
echo "Log: $LOG_FILE"
open "http://127.0.0.1:${PORT_VALUE}" >/dev/null 2>&1 || true
read -n 1 -s -r -p "Press any key to close this window..."
echo
