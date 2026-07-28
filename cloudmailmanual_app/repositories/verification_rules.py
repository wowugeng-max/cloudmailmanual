from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, List

from ..config import CONFIG_PATH

MAX_CUSTOM_PATTERNS = 50
MAX_PATTERN_LENGTH = 500
PRESET_METADATA = [
    {"id": "digits_6", "label": "连续 6 位数字", "example": "123456"},
    {
        "id": "digits_spaced_3_3",
        "label": "3+3 位空格数字",
        "example": "331 781",
    },
    {"id": "alnum_6", "label": "6 位字母数字", "example": "6PN6XW"},
    {
        "id": "alnum_hyphen_3_3",
        "label": "3+3 位连字符",
        "example": "ABC-123",
    },
    {
        "id": "labeled_code",
        "label": "带验证码标签",
        "example": "Verification code: 123456",
    },
]
PRESET_IDS = tuple(item["id"] for item in PRESET_METADATA)


def _read_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _write_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _patterns_to_text(patterns: List[Dict[str, str]]) -> str:
    return "\n".join(f"{item['name']} :: {item['pattern']}" for item in patterns)


def _parse_custom_patterns(text: str) -> List[Dict[str, str]]:
    custom_patterns: List[Dict[str, str]] = []
    names: set[str] = set()
    patterns: set[str] = set()

    for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "::" not in line:
            raise ValueError(f"第 {line_number} 行缺少 :: 分隔符")

        name, pattern = (part.strip() for part in line.split("::", 1))
        if not name or not pattern:
            raise ValueError(f"第 {line_number} 行名称和正则表达式不能为空")
        if len(pattern) > MAX_PATTERN_LENGTH:
            raise ValueError(
                f"第 {line_number} 行正则表达式最多 {MAX_PATTERN_LENGTH} 个字符"
            )

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"第 {line_number} 行正则表达式无效: {exc}") from exc
        if compiled.groups < 1:
            raise ValueError(f"第 {line_number} 行必须包含至少一个捕获组")
        if name in names:
            raise ValueError(f"第 {line_number} 行规则名称重复: {name}")
        if pattern in patterns:
            raise ValueError(f"第 {line_number} 行正则表达式重复")

        names.add(name)
        patterns.add(pattern)
        custom_patterns.append({"name": name, "pattern": pattern})

    if len(custom_patterns) > MAX_CUSTOM_PATTERNS:
        raise ValueError(f"自定义规则最多 {MAX_CUSTOM_PATTERNS} 条")
    return custom_patterns


def validate_verification_code_rules(payload: Dict[str, Any]) -> Dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("验证码规则配置必须是对象")

    raw_presets = payload.get("enabled_presets", [])
    if not isinstance(raw_presets, list):
        raise ValueError("enabled_presets 必须是数组")

    enabled_presets = [str(item or "").strip() for item in raw_presets]
    unknown_presets = [item for item in enabled_presets if item not in PRESET_IDS]
    if unknown_presets:
        raise ValueError(f"未知内置格式: {', '.join(unknown_presets)}")
    enabled_presets = list(dict.fromkeys(enabled_presets))

    if "custom_patterns_text" in payload:
        custom_patterns = _parse_custom_patterns(
            str(payload.get("custom_patterns_text", "") or "")
        )
    else:
        raw_custom_patterns = payload.get("custom_patterns", [])
        if not isinstance(raw_custom_patterns, list):
            raise ValueError("custom_patterns 必须是数组")

        persisted_patterns: List[Dict[str, str]] = []
        for index, item in enumerate(raw_custom_patterns, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"custom_patterns 第 {index} 项必须是对象")
            persisted_patterns.append(
                {
                    "name": str(item.get("name", "") or ""),
                    "pattern": str(item.get("pattern", "") or ""),
                }
            )
        custom_patterns = _parse_custom_patterns(_patterns_to_text(persisted_patterns))

    if not enabled_presets and not custom_patterns:
        raise ValueError("至少启用一个内置格式或添加一条自定义规则")

    return {
        "enabled_presets": enabled_presets,
        "custom_patterns": custom_patterns,
        "custom_patterns_text": _patterns_to_text(custom_patterns),
    }


def get_default_verification_code_rules() -> Dict[str, object]:
    return {
        "enabled_presets": list(PRESET_IDS),
        "custom_patterns": [],
        "custom_patterns_text": "",
    }


def get_verification_code_rules() -> Dict[str, object]:
    try:
        raw_rules = _read_config().get("verification_code_rules")
    except (OSError, json.JSONDecodeError):
        return get_default_verification_code_rules()
    if not isinstance(raw_rules, dict):
        return get_default_verification_code_rules()

    filtered_rules = dict(raw_rules)
    raw_presets = raw_rules.get("enabled_presets", [])
    if isinstance(raw_presets, list):
        filtered_rules["enabled_presets"] = [
            item for item in raw_presets if item in PRESET_IDS
        ]

    try:
        return validate_verification_code_rules(filtered_rules)
    except ValueError:
        return get_default_verification_code_rules()


def save_verification_code_rules(payload: Dict[str, Any]) -> Dict[str, object]:
    normalized_rules = validate_verification_code_rules(payload)
    config = _read_config()
    config["verification_code_rules"] = {
        "enabled_presets": normalized_rules["enabled_presets"],
        "custom_patterns": normalized_rules["custom_patterns"],
    }
    _write_config(config)
    return deepcopy(normalized_rules)
