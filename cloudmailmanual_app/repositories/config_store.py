from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict


_CONFIG_LOCK = threading.RLock()


def _read_config_unlocked(path: Path) -> Any:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_config_unlocked(path: Path, config: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def read_config(path: Path, *, tolerate_non_object: bool = False) -> Dict[str, Any]:
    with _CONFIG_LOCK:
        config = _read_config_unlocked(Path(path))
        if isinstance(config, dict):
            return config
        if tolerate_non_object:
            return {}
        raise ValueError("config.json 根配置必须是对象")


def update_config(
    path: Path,
    mutator: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    with _CONFIG_LOCK:
        config_path = Path(path)
        config = _read_config_unlocked(config_path)
        if not isinstance(config, dict):
            raise ValueError("config.json 根配置必须是对象")
        mutator(config)
        _write_config_unlocked(config_path, config)
        return config
