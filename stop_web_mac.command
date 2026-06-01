#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "./stop_web_mac.sh" ]; then
  chmod +x "./stop_web_mac.sh" "./start_web_mac.sh" "./run_web_mac.command" "./stop_web_mac.command" 2>/dev/null || true
  exec "./stop_web_mac.sh"
fi

echo "未找到 stop_web_mac.sh，请确认文件存在于同目录。"
read -n 1 -s -r -p "按任意键退出..."
echo
