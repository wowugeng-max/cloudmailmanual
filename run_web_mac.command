#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "./start_web_mac.sh" ]; then
  chmod +x "./start_web_mac.sh" "./stop_web_mac.sh" "./run_web_mac.sh" "./run_web_mac.command" "./stop_web_mac.command" 2>/dev/null || true
  exec "./start_web_mac.sh"
fi

echo "未找到 start_web_mac.sh，请确认文件存在于同目录。"
read -n 1 -s -r -p "按任意键退出..."
echo
