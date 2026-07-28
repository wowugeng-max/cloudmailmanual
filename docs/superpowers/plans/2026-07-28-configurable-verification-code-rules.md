# Configurable Verification Code Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add globally configurable built-in and custom verification-code formats to the mail settings tab, with validation, in-page testing, and next-query hot loading.

**Architecture:** A new `verification_rules` repository owns config persistence and validation. `CloudMailClient` accepts a normalized rule set and reloads it once per mailbox query; authenticated settings endpoints expose read, save, and side-effect-free test operations. The existing single-page UI renders preset checkboxes and textareas beneath the mail profile table and saves rules independently.

**Tech Stack:** Python 3.9, Flask, JSON configuration, Python `re`, vanilla JavaScript, HTML/CSS, `unittest`, SQLite-backed existing application tests.

---

## File Map

- Create `cloudmailmanual_app/repositories/verification_rules.py`: preset metadata, defaults, parser, validation, config reads and writes.
- Modify `cloud_mail_client.py`: configurable extraction engine and per-query rule loading.
- Modify `cloudmailmanual_app/routes.py`: authenticated GET, POST, and test endpoints.
- Modify `templates/index.html`: rule controls, independent load/save/test JavaScript, responsive styling.
- Modify `config.example.json`: document the persisted rule shape.
- Create `tests/test_verification_rules.py`: repository and extraction behavior tests.
- Create `tests/test_verification_rules_api.py`: endpoint validation and side-effect tests.
- Modify `tests/test_verification_code_extraction.py`: preserve current default extraction behavior.
- Modify `tests/test_app_structure.py`: require the new routes.
- Modify `tests/test_row_verification_ui.py`: require the settings controls and JavaScript wiring.

## Execution Prerequisite

The shared working tree currently contains completed but uncommitted account-history, row-query, email-layout, and theme work. Before task commits, stage every intended source/test change except `.DS_Store`, review the staged diff, and create one baseline commit. This keeps later task commits focused and preserves the already verified behavior.

```bash
git add cloudmailmanual_app/database.py \
  cloudmailmanual_app/repositories/accounts.py \
  cloudmailmanual_app/routes.py \
  cloudmailmanual_app/services/registration.py \
  templates/index.html \
  tests/test_account_history_search.py \
  tests/test_row_verification_ui.py
git diff --cached --check
git commit -m "feat: improve account history verification workflow"
```

Do not add or delete `.DS_Store`.

### Task 1: Rule Configuration Repository

**Files:**
- Create: `cloudmailmanual_app/repositories/verification_rules.py`
- Create: `tests/test_verification_rules.py`
- Modify: `config.example.json`

- [ ] **Step 1: Write failing repository tests**

Create `tests/test_verification_rules.py` with temporary-config isolation and explicit validation cases:

```python
import json
import tempfile
import unittest
from pathlib import Path

from cloudmailmanual_app.repositories import verification_rules


class VerificationRulesRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.original_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_path
        self.tmpdir.cleanup()

    def write_config(self, value):
        self.config_path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_config_uses_all_presets(self):
        rules = verification_rules.get_verification_code_rules()
        self.assertEqual(
            rules["enabled_presets"],
            [item["id"] for item in verification_rules.PRESET_METADATA],
        )
        self.assertEqual(rules["custom_patterns"], [])

    def test_save_preserves_unrelated_config(self):
        self.write_config({"web_port": 8080, "mail_profiles": [{"id": "work"}]})
        saved = verification_rules.save_verification_code_rules(
            {
                "enabled_presets": ["digits_6"],
                "custom_patterns_text": "Eight digits :: token: (\\d{8})",
            }
        )
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["web_port"], 8080)
        self.assertEqual(raw["mail_profiles"], [{"id": "work"}])
        self.assertEqual(saved["custom_patterns"][0]["name"], "Eight digits")

    def test_invalid_pattern_reports_source_line(self):
        with self.assertRaisesRegex(ValueError, "第 2 行.*正则表达式无效"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns_text": "Good :: (\\d{6})\nBad :: ([",
                }
            )

    def test_pattern_requires_capture_group(self):
        with self.assertRaisesRegex(ValueError, "第 1 行.*捕获组"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": "No group :: \\d{6}"}
            )

    def test_unknown_preset_and_duplicates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "未知内置格式"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": ["unknown"], "custom_patterns_text": ""}
            )
        with self.assertRaisesRegex(ValueError, "名称重复"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": [],
                    "custom_patterns_text": "Same :: (\\d{6})\nSame :: ([A-Z]{6})",
                }
            )
        with self.assertRaisesRegex(ValueError, "正则表达式重复"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": [],
                    "custom_patterns_text": "First :: (\\d{6})\nSecond :: (\\d{6})",
                }
            )

    def test_unknown_preset_is_ignored_when_reading_manual_config(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": ["digits_6", "future_format"],
                    "custom_patterns": [],
                }
            }
        )
        rules = verification_rules.get_verification_code_rules()
        self.assertEqual(rules["enabled_presets"], ["digits_6"])

    def test_limits_are_enforced(self):
        too_many = "\n".join(f"R{i} :: (\\d{{6}}X{i})" for i in range(51))
        with self.assertRaisesRegex(ValueError, "最多 50"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": too_many}
            )
        with self.assertRaisesRegex(ValueError, "最多 500"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": "Long :: (" + "a" * 501 + ")"}
            )
```

- [ ] **Step 2: Run the repository tests and verify the import fails**

Run:

```bash
.venv-mac/bin/python -m unittest tests.test_verification_rules.VerificationRulesRepositoryTest -v
```

Expected: FAIL because `cloudmailmanual_app.repositories.verification_rules` does not exist.

- [ ] **Step 3: Implement the repository**

Create `cloudmailmanual_app/repositories/verification_rules.py` with these public constants and functions:

```python
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
    {"id": "digits_spaced_3_3", "label": "3+3 位空格数字", "example": "331 781"},
    {"id": "alnum_6", "label": "6 位字母数字", "example": "6PN6XW"},
    {"id": "alnum_hyphen_3_3", "label": "3+3 位连字符", "example": "ABC-123"},
    {"id": "labeled_code", "label": "带验证码标签", "example": "Verification code: 123456"},
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
    items: List[Dict[str, str]] = []
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
            raise ValueError(f"第 {line_number} 行正则表达式最多 500 个字符")
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
        items.append({"name": name, "pattern": pattern})
    if len(items) > MAX_CUSTOM_PATTERNS:
        raise ValueError("自定义规则最多 50 条")
    return items


def validate_verification_code_rules(payload: Dict[str, Any]) -> Dict[str, object]:
    raw_presets = payload.get("enabled_presets", [])
    if not isinstance(raw_presets, list):
        raise ValueError("enabled_presets 必须是数组")
    enabled = [str(item or "").strip() for item in raw_presets]
    unknown = [item for item in enabled if item not in PRESET_IDS]
    if unknown:
        raise ValueError(f"未知内置格式: {', '.join(unknown)}")
    enabled = list(dict.fromkeys(enabled))

    if "custom_patterns_text" in payload:
        custom = _parse_custom_patterns(str(payload.get("custom_patterns_text", "") or ""))
    else:
        raw_custom = payload.get("custom_patterns", [])
        if not isinstance(raw_custom, list):
            raise ValueError("custom_patterns 必须是数组")
        text = _patterns_to_text(
            [
                {"name": str(item.get("name", "")), "pattern": str(item.get("pattern", ""))}
                for item in raw_custom
                if isinstance(item, dict)
            ]
        )
        custom = _parse_custom_patterns(text)
    if not enabled and not custom:
        raise ValueError("至少启用一个内置格式或添加一条自定义规则")
    return {
        "enabled_presets": enabled,
        "custom_patterns": custom,
        "custom_patterns_text": _patterns_to_text(custom),
    }


def get_default_verification_code_rules() -> Dict[str, object]:
    return {
        "enabled_presets": list(PRESET_IDS),
        "custom_patterns": [],
        "custom_patterns_text": "",
    }


def get_verification_code_rules() -> Dict[str, object]:
    raw = _read_config().get("verification_code_rules")
    if not isinstance(raw, dict):
        return get_default_verification_code_rules()
    filtered = dict(raw)
    raw_presets = raw.get("enabled_presets", [])
    if isinstance(raw_presets, list):
        filtered["enabled_presets"] = [item for item in raw_presets if item in PRESET_IDS]
    try:
        return validate_verification_code_rules(filtered)
    except ValueError:
        return get_default_verification_code_rules()


def save_verification_code_rules(payload: Dict[str, Any]) -> Dict[str, object]:
    normalized = validate_verification_code_rules(payload)
    config = _read_config()
    config["verification_code_rules"] = {
        "enabled_presets": normalized["enabled_presets"],
        "custom_patterns": normalized["custom_patterns"],
    }
    _write_config(config)
    return deepcopy(normalized)
```

- [ ] **Step 4: Add the example configuration**

Add a top-level default block to `config.example.json` without changing the sample mail profile:

```json
"verification_code_rules": {
  "enabled_presets": [
    "digits_6",
    "digits_spaced_3_3",
    "alnum_6",
    "alnum_hyphen_3_3",
    "labeled_code"
  ],
  "custom_patterns": []
}
```

- [ ] **Step 5: Run repository tests**

Run:

```bash
.venv-mac/bin/python -m unittest tests.test_verification_rules.VerificationRulesRepositoryTest -v
```

Expected: all repository tests PASS.

- [ ] **Step 6: Commit the repository slice**

```bash
git add cloudmailmanual_app/repositories/verification_rules.py tests/test_verification_rules.py config.example.json
git commit -m "feat: add verification rule configuration repository"
```

### Task 2: Configurable Extraction And Hot Loading

**Files:**
- Modify: `cloud_mail_client.py:130-221`
- Modify: `tests/test_verification_code_extraction.py`
- Modify: `tests/test_verification_rules.py`

- [ ] **Step 1: Add failing extraction tests**

Append these tests, using the existing temporary config fixture from Task 1 where required:

```python
from cloud_mail_client import CloudMailClient


class ConfigurableExtractionTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.original_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_path
        self.tmpdir.cleanup()

    def write_config(self, value):
        self.config_path.write_text(json.dumps(value), encoding="utf-8")

    def test_custom_pattern_runs_before_builtins(self):
        rules = {
            "enabled_presets": ["digits_6"],
            "custom_patterns": [
                {"name": "Preferred", "pattern": r"preferred:\s*(\d{8})"}
            ],
        }
        code = CloudMailClient.extract_verification_code(
            "Fallback 123456, preferred: 87654321",
            rules=rules,
        )
        self.assertEqual(code, "87654321")

    def test_custom_pattern_removes_captured_whitespace(self):
        rules = {
            "enabled_presets": [],
            "custom_patterns": [{"name": "Grouped", "pattern": r"token:\s*(\d{3}\s+\d{3})"}],
        }
        self.assertEqual(
            CloudMailClient.extract_verification_code("token: 331 781", rules=rules),
            "331781",
        )

    def test_disabled_preset_does_not_match(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}
        self.assertIsNone(CloudMailClient.extract_verification_code("code: 123456", rules=rules))

    def test_query_reloads_rules_without_recreating_client(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": [],
                    "custom_patterns": [{"name": "Eight", "pattern": r"token: (\d{8})"}],
                }
            }
        )
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [{"subject": "token: 87654321"}]
        self.assertEqual(client.query_verification_code("a@example.com"), "87654321")

        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns": [],
                }
            }
        )
        self.assertIsNone(client.query_verification_code("a@example.com"))
```

- [ ] **Step 2: Run extraction tests and verify signature/behavior failures**

```bash
.venv-mac/bin/python -m unittest tests.test_verification_code_extraction tests.test_verification_rules.ConfigurableExtractionTest -v
```

Expected: FAIL because `extract_verification_code()` does not accept `rules` and queries do not reload configuration.

- [ ] **Step 3: Add pattern definitions and configurable extraction**

Import `get_default_verification_code_rules` and `get_verification_code_rules` from the new repository. Add preset regex specifications near the imports in `cloud_mail_client.py`:

```python
PRESET_PATTERNS = {
    "alnum_hyphen_3_3": [r"(?<![A-Z0-9-])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9-])"],
    "alnum_6": [r"(?<![A-Z0-9])((?=[A-Z0-9]{0,5}[A-Z])(?=[A-Z0-9]{6}(?![A-Z0-9]))[A-Z0-9]{6})(?![A-Z0-9])"],
    "labeled_code": [
        r"(?:verification code|验证码|your code|code is|code below|enter this code)[^A-Z0-9]{0,20}([A-Z0-9-]{6,8})\b",
        r"(?:verification code|验证码|your code|code is|code below|enter this code)[^\d]{0,40}(\d{6})",
    ],
    "digits_spaced_3_3": [r"(?<![A-Z0-9])(\d{3}\s+\d{3})(?![A-Z0-9])"],
    "digits_6": [r"(?<![A-Z0-9])(\d{6})(?![A-Z0-9])"],
}
PRESET_ORDER = (
    "alnum_hyphen_3_3",
    "alnum_6",
    "labeled_code",
    "digits_spaced_3_3",
    "digits_6",
)
```

Replace the extraction method with a rules-aware implementation that preserves `allow_digits`:

```python
@staticmethod
def extract_verification_code(
    content: str,
    *,
    allow_digits: bool = True,
    rules: Optional[Dict[str, object]] = None,
) -> Optional[str]:
    if not content:
        return None
    normalized = str(content)
    normalized = re.sub(r"<head\b[\s\S]*?</head>", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"<style\b[\s\S]*?</style>", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"<script\b[\s\S]*?</script>", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"<!--.*?-->", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()[:200_000]

    selected = rules or get_default_verification_code_rules()
    pattern_specs = [
        str(item.get("pattern", ""))
        for item in selected.get("custom_patterns", [])
        if isinstance(item, dict) and item.get("pattern")
    ]
    enabled = set(str(item) for item in selected.get("enabled_presets", []))
    for preset_id in PRESET_ORDER:
        if preset_id in enabled:
            pattern_specs.extend(PRESET_PATTERNS[preset_id])

    for pattern in pattern_specs:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        code = re.sub(r"\s+", "", str(match.group(1) or ""))
        if not code or code == "177010":
            continue
        if not allow_digits and code.replace("-", "").isdigit():
            continue
        return code
    return None
```

At the start of `query_verification_detail()`, load once and pass the same object to all six extraction calls:

```python
rules = get_verification_code_rules()
rows = self._email_list(to_email=email, size=50)
# ...
code = self.extract_verification_code(subject, allow_digits=False, rules=rules)
```

- [ ] **Step 4: Run extraction and compatibility tests**

```bash
.venv-mac/bin/python -m unittest \
  tests.test_verification_code_extraction \
  tests.test_verification_rules.ConfigurableExtractionTest -v
```

Expected: custom priority, whitespace normalization, preset disablement, hot loading, and existing `331 781` behavior all PASS.

- [ ] **Step 5: Commit the extraction slice**

```bash
git add cloud_mail_client.py tests/test_verification_code_extraction.py tests/test_verification_rules.py
git commit -m "feat: hot load configurable verification formats"
```

### Task 3: Authenticated Settings And Test APIs

**Files:**
- Modify: `cloudmailmanual_app/routes.py:1-115`
- Modify: `tests/test_app_structure.py`
- Create: `tests/test_verification_rules_api.py`

- [ ] **Step 1: Add failing route and API tests**

Require all endpoints in `tests/test_app_structure.py`:

```python
self.assertIn("/api/settings/verification-code-rules", routes)
self.assertIn("/api/settings/verification-code-rules/test", routes)
```

Create `tests/test_verification_rules_api.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cloudmailmanual_app.factory import create_app
from cloudmailmanual_app.repositories import verification_rules


class VerificationRulesApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.config_path.write_text(json.dumps({"web_port": 8080}), encoding="utf-8")
        self.original_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user"] = "admin"

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_path
        self.tmpdir.cleanup()

    def test_get_returns_preset_metadata(self):
        response = self.client.get("/api/settings/verification-code-rules")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["available_presets"]), 5)

    def test_api_requires_login(self):
        anonymous = self.app.test_client()
        response = anonymous.get("/api/settings/verification-code-rules")
        self.assertEqual(response.status_code, 401)

    def test_invalid_save_does_not_overwrite_config(self):
        before = self.config_path.read_text(encoding="utf-8")
        response = self.client.post(
            "/api/settings/verification-code-rules",
            json={"enabled_presets": [], "custom_patterns_text": "Bad :: (["},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), before)

    def test_test_endpoint_uses_unsaved_rules_without_writing(self):
        before = self.config_path.read_text(encoding="utf-8")
        with patch("cloudmailmanual_app.routes.save_verification_query") as save_query, patch(
            "cloudmailmanual_app.routes.mark_account_used"
        ) as mark_used:
            response = self.client.post(
                "/api/settings/verification-code-rules/test",
                json={
                    "enabled_presets": [],
                    "custom_patterns_text": r"Eight :: token: (\d{8})",
                    "content": "token: 87654321",
                },
            )
            save_query.assert_not_called()
            mark_used.assert_not_called()
        self.assertEqual(response.get_json()["code"], "87654321")
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), before)

    def test_test_content_limit_is_enforced(self):
        response = self.client.post(
            "/api/settings/verification-code-rules/test",
            json={
                "enabled_presets": ["digits_6"],
                "custom_patterns_text": "",
                "content": "x" * 100_001,
            },
        )
        self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Run tests and verify 404 failures**

```bash
.venv-mac/bin/python -m unittest tests.test_app_structure tests.test_verification_rules_api -v
```

Expected: FAIL because the new URLs are not registered.

- [ ] **Step 3: Add repository imports and routes**

Import:

```python
from .repositories.verification_rules import (
    PRESET_METADATA,
    get_verification_code_rules,
    save_verification_code_rules,
    validate_verification_code_rules,
)
```

Register these authenticated routes near the mail profile settings routes:

```python
@app.get("/api/settings/verification-code-rules")
@login_required
def api_get_verification_code_rules():
    data = get_verification_code_rules()
    return jsonify({"ok": True, "available_presets": PRESET_METADATA, **data})


@app.post("/api/settings/verification-code-rules")
@login_required
def api_save_verification_code_rules():
    payload = request.get_json(silent=True) or {}
    try:
        data = save_verification_code_rules(payload)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/settings/verification-code-rules/test")
@login_required
def api_test_verification_code_rules():
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content", "") or "")
    if len(content) > 100_000:
        return jsonify({"ok": False, "error": "测试内容最多 100000 个字符"}), 400
    try:
        rules = validate_verification_code_rules(payload)
        code = CloudMailClient.extract_verification_code(content, rules=rules)
        return jsonify({"ok": True, "code": code or ""})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
```

- [ ] **Step 4: Run API tests**

```bash
.venv-mac/bin/python -m unittest tests.test_app_structure tests.test_verification_rules_api -v
```

Expected: all route, save-validation, no-write tester, and content-limit tests PASS.

- [ ] **Step 5: Commit the API slice**

```bash
git add cloudmailmanual_app/routes.py tests/test_app_structure.py tests/test_verification_rules_api.py
git commit -m "feat: expose verification rule settings APIs"
```

### Task 4: Mail Settings User Interface

**Files:**
- Modify: `templates/index.html:410-445, 470-700, 1600-1620`
- Modify: `tests/test_row_verification_ui.py`

- [ ] **Step 1: Add failing UI wiring tests**

Append:

```python
def test_mail_settings_exposes_verification_rule_editor(self):
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    self.assertIn('id="verificationPresetOptions"', html)
    self.assertIn('id="verificationCustomPatterns"', html)
    self.assertIn('id="verificationRuleTestContent"', html)
    self.assertIn('id="testVerificationRulesBtn"', html)
    self.assertIn('id="saveVerificationRulesBtn"', html)
    self.assertIn("loadVerificationRules", html)
    self.assertIn("testVerificationRules", html)
    self.assertIn("saveVerificationRules", html)
```

- [ ] **Step 2: Run the UI test and verify it fails**

```bash
.venv-mac/bin/python -m unittest \
  tests.test_row_verification_ui.RowVerificationUiTest.test_mail_settings_exposes_verification_rule_editor -v
```

Expected: FAIL because the controls do not exist.

- [ ] **Step 3: Add the settings markup and scoped styles**

Below `mailProfilesTable`, add an unframed section rather than a nested card:

```html
<section class="verification-rule-settings" aria-labelledby="verificationRuleHeading">
  <h3 id="verificationRuleHeading">验证码格式</h3>
  <div id="verificationPresetOptions" class="verification-preset-options"></div>
  <label for="verificationCustomPatterns">自定义正则</label>
  <textarea id="verificationCustomPatterns" rows="7" spellcheck="false"></textarea>
  <label for="verificationRuleTestContent">测试内容</label>
  <textarea id="verificationRuleTestContent" rows="6"></textarea>
  <div class="row verification-rule-actions">
    <button id="testVerificationRulesBtn" class="btn-secondary" onclick="testVerificationRules()">测试规则</button>
    <button id="saveVerificationRulesBtn" onclick="saveVerificationRules()">保存验证码规则</button>
  </div>
  <div id="verificationRulesStatus" class="status"></div>
</section>
```

Add stable dimensions and light/dark-compatible styles using existing variables:

```css
.verification-rule-settings { margin-top:22px; padding-top:18px; border-top:1px solid var(--border); }
.verification-rule-settings h3 { margin:0 0 12px; font-size:16px; }
.verification-preset-options { display:flex; flex-wrap:wrap; gap:8px 16px; margin-bottom:14px; }
.verification-preset-option { display:inline-flex; align-items:center; gap:6px; }
.verification-preset-option input { width:16px; height:16px; margin:0; padding:0; }
.verification-rule-settings textarea { display:block; box-sizing:border-box; width:100%; max-width:900px; margin:6px 0 14px; padding:10px 11px; border:1px solid var(--border); border-radius:8px; background:var(--field-bg); color:var(--text); font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; resize:vertical; }
.verification-rule-actions { margin-top:4px; }
```

- [ ] **Step 4: Add independent load, collect, test, and save functions**

Add global metadata state and functions to the existing script:

```javascript
let verificationPresetMetadata = [];

function collectVerificationRules() {
  return {
    enabled_presets: Array.from(document.querySelectorAll('[data-verification-preset]:checked'))
      .map((input) => input.value),
    custom_patterns_text: String(document.getElementById('verificationCustomPatterns').value || ''),
  };
}

function renderVerificationPresets(enabledPresets) {
  const container = document.getElementById('verificationPresetOptions');
  container.innerHTML = '';
  verificationPresetMetadata.forEach((preset) => {
    const label = document.createElement('label');
    label.className = 'verification-preset-option';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = preset.id;
    input.dataset.verificationPreset = '1';
    input.checked = enabledPresets.includes(preset.id);
    const text = document.createElement('span');
    text.textContent = `${preset.label} (${preset.example})`;
    label.append(input, text);
    container.appendChild(label);
  });
}

async function loadVerificationRules() {
  const status = document.getElementById('verificationRulesStatus');
  try {
    const res = await fetch('/api/settings/verification-code-rules');
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '加载失败');
    verificationPresetMetadata = data.available_presets || [];
    renderVerificationPresets(data.enabled_presets || []);
    document.getElementById('verificationCustomPatterns').value = data.custom_patterns_text || '';
  } catch (error) {
    status.className = 'status err';
    status.textContent = `加载验证码规则失败：${error.message || error}`;
  }
}

async function testVerificationRules() {
  const button = document.getElementById('testVerificationRulesBtn');
  const status = document.getElementById('verificationRulesStatus');
  button.disabled = true;
  status.className = 'status';
  status.textContent = '正在测试...';
  try {
    const payload = {
      ...collectVerificationRules(),
      content: String(document.getElementById('verificationRuleTestContent').value || ''),
    };
    const res = await fetch('/api/settings/verification-code-rules/test', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '测试失败');
    status.className = data.code ? 'status ok' : 'status';
    status.textContent = data.code ? `提取结果：${data.code}` : '未提取到验证码';
  } catch (error) {
    status.className = 'status err';
    status.textContent = `测试失败：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}

async function saveVerificationRules() {
  const button = document.getElementById('saveVerificationRulesBtn');
  const status = document.getElementById('verificationRulesStatus');
  button.disabled = true;
  status.className = 'status';
  status.textContent = '正在保存验证码规则...';
  try {
    const res = await fetch('/api/settings/verification-code-rules', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(collectVerificationRules()),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '保存失败');
    renderVerificationPresets(data.enabled_presets || []);
    document.getElementById('verificationCustomPatterns').value = data.custom_patterns_text || '';
    status.className = 'status ok';
    status.textContent = '验证码规则已保存，下次查询立即生效';
  } catch (error) {
    status.className = 'status err';
    status.textContent = `保存失败：${error.message || error}`;
  } finally {
    button.disabled = false;
  }
}
```

Call `loadVerificationRules()` in the existing `window.load` handler next to `loadMailProfiles()`.

- [ ] **Step 5: Run UI and JavaScript syntax tests**

```bash
.venv-mac/bin/python -m unittest tests.test_row_verification_ui -v
node -e 'const fs=require("fs"),vm=require("vm"); const h=fs.readFileSync("templates/index.html","utf8"); [...h.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]).filter(Boolean).forEach((s,i)=>new vm.Script(s,{filename:`inline-${i}.js`}));'
```

Expected: UI tests PASS and Node exits 0.

- [ ] **Step 6: Commit the UI slice**

```bash
git add templates/index.html tests/test_row_verification_ui.py
git commit -m "feat: add verification rule settings UI"
```

### Task 5: End-To-End Verification And Visual QA

**Files:**
- Modify only if verification finds a defect in files already listed above.

- [ ] **Step 1: Run the complete automated suite**

```bash
.venv-mac/bin/python -m unittest discover -s tests -v
```

Expected: every test PASS, including existing account history, mail profile, macOS script, theme, and spaced-code tests.

- [ ] **Step 2: Run compile, JavaScript, and diff checks**

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cloudmailmanual-pycache \
  .venv-mac/bin/python -m py_compile \
  app.py auth.py cloud_mail_client.py \
  cloudmailmanual_app/*.py \
  cloudmailmanual_app/repositories/*.py \
  cloudmailmanual_app/services/*.py \
  tests/*.py
node -e 'const fs=require("fs"),vm=require("vm"); const h=fs.readFileSync("templates/index.html","utf8"); [...h.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]).filter(Boolean).forEach((s,i)=>new vm.Script(s,{filename:`inline-${i}.js`}));'
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 3: Start the local server and perform browser QA**

```bash
.venv-mac/bin/python app.py --port 18081
```

In the in-app browser:

1. Log in and open `邮箱配置`.
2. Verify both themes render readable preset labels, textareas, status text, and buttons.
3. Disable all presets, add `Eight :: token: (\d{8})`, enter `token: 87654321`, and confirm `测试规则` returns `87654321` without saving.
4. Enter an invalid expression and confirm the displayed error identifies its line.
5. Save a valid custom rule and confirm the success message states that the next query uses it.
6. Reload the page and confirm the saved presets and custom text remain.
7. Restore all default presets and clear custom rules before finishing, so QA does not alter the user's extraction behavior.
8. Check the browser console for errors and verify narrow-screen controls wrap without overlap.

- [ ] **Step 4: Stop the temporary server and review repository state**

Stop Flask with `Ctrl-C`, then run:

```bash
git status --short
git log -5 --oneline
```

Expected: only intentionally untracked `.DS_Store` remains; all feature changes are committed.

- [ ] **Step 5: Request final code review**

Ask the reviewer to compare the implementation against:

```text
docs/superpowers/specs/2026-07-28-configurable-verification-code-rules-design.md
```

Resolve every critical or important finding, rerun Steps 1-2, and make a focused fix commit if needed:

```bash
git add cloud_mail_client.py \
  cloudmailmanual_app/repositories/verification_rules.py \
  cloudmailmanual_app/routes.py \
  templates/index.html \
  tests/test_verification_code_extraction.py \
  tests/test_verification_rules.py \
  tests/test_verification_rules_api.py \
  tests/test_row_verification_ui.py
git commit -m "fix: address verification rule review findings"
```
