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

stop_pid() {
  local pid="$1"
  if [ -z "$pid" ] || ! kill -0 "$pid" >/dev/null 2>&1; then
    return 1
  fi

  echo "Stopping PID $pid..."
  kill "$pid" >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "PID $pid did not exit; forcing stop..."
  kill -9 "$pid" >/dev/null 2>&1 || true
  return 0
}

if [ "${1:-}" = "--dry-run" ]; then
  echo "Cloud Mail stop launcher is ready."
  echo "PID file: $PID_FILE"
  echo "Log file: $LOG_FILE"
  echo "Port: $(resolve_port)"
  exit 0
fi

STOPPED=0

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if stop_pid "$PID"; then
    STOPPED=1
  fi
  rm -f "$PID_FILE"
fi

PORT_VALUE="$(resolve_port)"
PORT_PIDS="$(lsof -ti tcp:"$PORT_VALUE" 2>/dev/null || true)"
if [ -n "$PORT_PIDS" ]; then
  echo "Found process listening on port $PORT_VALUE."
  for pid in $PORT_PIDS; do
    if stop_pid "$pid"; then
      STOPPED=1
    fi
  done
fi

if [ "$STOPPED" = "1" ]; then
  echo "Cloud Mail stopped."
else
  echo "Cloud Mail was not running."
fi

echo "Log: $LOG_FILE"
read -n 1 -s -r -p "Press any key to close this window..."
echo
