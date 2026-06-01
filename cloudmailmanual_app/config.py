from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(BASE_DIR / "cloudmailmanual.db")
DEFAULT_MAX_GENERATE = 50
CONFIG_PATH = BASE_DIR / "config.json"


def _read_config_web_port() -> int | None:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None

    raw = str(cfg.get("web_port", "") or "").strip()
    if raw.isdigit() and 1 <= int(raw) <= 65535:
        return int(raw)
    return None

def resolve_run_port(cli_port: int | None = None) -> int:
    """按优先级解析启动端口：CLI > config.json(web_port) > APP_PORT/PORT > 默认 5000。"""
    if cli_port is not None:
        if 1 <= cli_port <= 65535:
            return cli_port
        raise ValueError("端口必须在 1-65535")

    config_port = _read_config_web_port()
    if config_port is not None:
        return config_port

    for key in ("APP_PORT", "PORT"):
        raw = str(os.getenv(key, "") or "").strip()
        if not raw:
            continue
        if raw.isdigit() and 1 <= int(raw) <= 65535:
            return int(raw)

    return 5000

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cloud Mail Web 应用")
    parser.add_argument("--port", type=int, default=None, help="自定义启动端口（1-65535）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="自定义监听地址，默认 0.0.0.0")
    parser.add_argument("--debug", action="store_true", help="开启 Flask debug 模式")
    return parser.parse_args()
