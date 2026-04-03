#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

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

echo "[5/5] Starting web app on http://127.0.0.1:5000"
python app.py
