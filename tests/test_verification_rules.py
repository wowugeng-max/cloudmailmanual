import json
import tempfile
import unittest
from pathlib import Path

from cloud_mail_client import CloudMailClient
from cloudmailmanual_app.repositories import verification_rules

OVERFLOW_PATTERN = "(a){999999999999999999999999999999999999999}"


class VerificationRulesRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.original_config_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_config_path
        self.tmpdir.cleanup()

    def write_config(self, value):
        self.config_path.write_text(json.dumps(value), encoding="utf-8")

    def test_public_preset_metadata_and_limits(self):
        self.assertEqual(verification_rules.MAX_CUSTOM_PATTERNS, 50)
        self.assertEqual(verification_rules.MAX_PATTERN_LENGTH, 500)
        self.assertEqual(
            verification_rules.PRESET_METADATA,
            [
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
            ],
        )
        self.assertEqual(
            verification_rules.PRESET_IDS,
            (
                "digits_6",
                "digits_spaced_3_3",
                "alnum_6",
                "alnum_hyphen_3_3",
                "labeled_code",
            ),
        )

    def test_missing_config_uses_all_presets(self):
        rules = verification_rules.get_verification_code_rules()

        self.assertEqual(rules, verification_rules.get_default_verification_code_rules())
        self.assertEqual(rules["enabled_presets"], list(verification_rules.PRESET_IDS))
        self.assertEqual(rules["custom_patterns"], [])
        self.assertEqual(rules["custom_patterns_text"], "")

    def test_validate_deduplicates_presets_and_normalizes_custom_text(self):
        rules = verification_rules.validate_verification_code_rules(
            {
                "enabled_presets": ["alnum_6", "digits_6", "alnum_6"],
                "custom_patterns_text": (
                    "  Eight digits  ::  token: (\\d{8})  \n\n"
                    "Code with separator :: code::([A-Z]{3})"
                ),
            }
        )

        self.assertEqual(rules["enabled_presets"], ["alnum_6", "digits_6"])
        self.assertEqual(
            rules["custom_patterns"],
            [
                {"name": "Eight digits", "pattern": "token: (\\d{8})"},
                {"name": "Code with separator", "pattern": "code::([A-Z]{3})"},
            ],
        )
        self.assertEqual(
            rules["custom_patterns_text"],
            "Eight digits :: token: (\\d{8})\n"
            "Code with separator :: code::([A-Z]{3})",
        )

    def test_custom_patterns_text_must_be_string_when_present(self):
        invalid_values = [
            ["Rule :: (\\d{6})"],
            {"Rule": "(\\d{6})"},
            123,
            None,
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError, "custom_patterns_text 必须是字符串"
                ):
                    verification_rules.validate_verification_code_rules(
                        {
                            "enabled_presets": ["digits_6"],
                            "custom_patterns_text": value,
                        }
                    )

    def test_validate_accepts_and_checks_persisted_custom_patterns(self):
        rules = verification_rules.validate_verification_code_rules(
            {
                "enabled_presets": [],
                "custom_patterns": [
                    {"name": "Letters", "pattern": "token: ([a-z]{6})"},
                ],
            }
        )

        self.assertEqual(
            rules["custom_patterns_text"], "Letters :: token: ([a-z]{6})"
        )
        with self.assertRaisesRegex(ValueError, "custom_patterns 必须是数组"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": ["digits_6"], "custom_patterns": {}}
            )
        with self.assertRaisesRegex(ValueError, "第 1 行.*不能为空"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns": [{"name": "", "pattern": "(\\d+)"}],
                }
            )

    def test_persisted_custom_pattern_name_and_pattern_must_be_strings(self):
        invalid_patterns = [
            {"name": 123, "pattern": "(\\d{6})"},
            {"name": "Digits", "pattern": {"source": "(\\d{6})"}},
        ]

        for custom_pattern in invalid_patterns:
            with self.subTest(custom_pattern=custom_pattern):
                with self.assertRaisesRegex(
                    ValueError,
                    "custom_patterns 第 1 项.*名称和正则表达式必须是字符串",
                ):
                    verification_rules.validate_verification_code_rules(
                        {
                            "enabled_presets": ["digits_6"],
                            "custom_patterns": [custom_pattern],
                        }
                    )

    def test_save_preserves_unrelated_config_and_mail_profiles(self):
        original = {
            "web_port": 8080,
            "admin_username": "管理员",
            "mail_profiles": [{"id": "work", "name": "工作邮箱"}],
            "verification_code_rules": {
                "enabled_presets": ["alnum_6"],
                "custom_patterns": [],
            },
        }
        self.write_config(original)

        saved = verification_rules.save_verification_code_rules(
            {
                "enabled_presets": ["digits_6", "digits_6"],
                "custom_patterns_text": "八位数字 :: token: (\\d{8})",
            }
        )

        raw_text = self.config_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
        self.assertEqual(raw["web_port"], original["web_port"])
        self.assertEqual(raw["admin_username"], original["admin_username"])
        self.assertEqual(raw["mail_profiles"], original["mail_profiles"])
        self.assertEqual(
            raw["verification_code_rules"],
            {
                "enabled_presets": ["digits_6"],
                "custom_patterns": [
                    {"name": "八位数字", "pattern": "token: (\\d{8})"}
                ],
            },
        )
        self.assertTrue(raw_text.endswith("\n"))
        self.assertIn('  "verification_code_rules": {', raw_text)
        self.assertIn("管理员", raw_text)
        self.assertNotIn("\\u7ba1", raw_text)
        self.assertEqual(saved["custom_patterns_text"], "八位数字 :: token: (\\d{8})")

        saved["enabled_presets"].append("alnum_6")
        saved["custom_patterns"][0]["name"] = "mutated"
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted["verification_code_rules"]["enabled_presets"], ["digits_6"]
        )
        self.assertEqual(
            persisted["verification_code_rules"]["custom_patterns"][0]["name"],
            "八位数字",
        )

    def test_invalid_pattern_reports_source_line(self):
        with self.assertRaisesRegex(ValueError, "第 2 行.*正则表达式无效"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns_text": "Good :: (\\d{6})\nBad :: ([",
                }
            )

    def test_regex_compile_overflow_reports_source_line(self):
        with self.assertRaisesRegex(ValueError, "第 1 行.*正则表达式无效"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns_text": f"Huge :: {OVERFLOW_PATTERN}",
                }
            )

    def test_manual_config_with_regex_compile_overflow_falls_back_to_default(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns": [
                        {"name": "Huge", "pattern": OVERFLOW_PATTERN},
                    ],
                }
            }
        )

        self.assertEqual(
            verification_rules.get_verification_code_rules(),
            verification_rules.get_default_verification_code_rules(),
        )

    def test_pattern_requires_capture_group(self):
        with self.assertRaisesRegex(ValueError, "第 1 行.*捕获组"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": "No group :: \\d{6}"}
            )

    def test_unknown_preset_and_duplicates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "enabled_presets 必须是数组"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": "digits_6", "custom_patterns_text": ""}
            )
        with self.assertRaisesRegex(ValueError, "未知内置格式"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": ["unknown"], "custom_patterns_text": ""}
            )
        with self.assertRaisesRegex(ValueError, "第 2 行.*名称重复"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": [],
                    "custom_patterns_text": (
                        "Same :: (\\d{6})\nSame :: ([A-Z]{6})"
                    ),
                }
            )
        with self.assertRaisesRegex(ValueError, "第 2 行.*正则表达式重复"):
            verification_rules.validate_verification_code_rules(
                {
                    "enabled_presets": [],
                    "custom_patterns_text": (
                        "First :: (\\d{6})\nSecond :: (\\d{6})"
                    ),
                }
            )

    def test_malformed_lines_and_empty_rules_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "第 1 行.*缺少 ::"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": ["digits_6"], "custom_patterns_text": "No separator"}
            )
        with self.assertRaisesRegex(ValueError, "第 1 行.*不能为空"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": ["digits_6"], "custom_patterns_text": "Name :: "}
            )
        with self.assertRaisesRegex(ValueError, "至少启用"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": ""}
            )

    def test_unknown_preset_is_ignored_when_reading_manual_config(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": [
                        "digits_6",
                        "future_format",
                        "digits_6",
                    ],
                    "custom_patterns": [],
                }
            }
        )

        rules = verification_rules.get_verification_code_rules()

        self.assertEqual(rules["enabled_presets"], ["digits_6"])

    def test_invalid_manual_config_falls_back_to_default(self):
        invalid_configs = [
            {"verification_code_rules": []},
            {
                "verification_code_rules": {
                    "enabled_presets": [],
                    "custom_patterns": [{"name": "Bad", "pattern": "["}],
                }
            },
            {
                "verification_code_rules": {
                    "enabled_presets": [],
                    "custom_patterns": [],
                }
            },
        ]
        for config in invalid_configs:
            with self.subTest(config=config):
                self.write_config(config)
                self.assertEqual(
                    verification_rules.get_verification_code_rules(),
                    verification_rules.get_default_verification_code_rules(),
                )

    def test_limits_are_enforced(self):
        too_many = "\n".join(f"R{i} :: (\\d{{6}}X{i})" for i in range(51))
        with self.assertRaisesRegex(ValueError, "最多 50"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": too_many}
            )

        too_long = "Long :: (" + "a" * 501 + ")"
        with self.assertRaisesRegex(ValueError, "第 1 行.*最多 500"):
            verification_rules.validate_verification_code_rules(
                {"enabled_presets": [], "custom_patterns_text": too_long}
            )


class ConfigurableExtractionTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.original_config_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_config_path
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
            "custom_patterns": [
                {"name": "Grouped", "pattern": r"token:\s*(\d{3}\s+\d{3})"}
            ],
        }

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "token: 331 781",
                rules=rules,
            ),
            "331781",
        )

    def test_disabled_preset_does_not_match(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

        self.assertIsNone(
            CloudMailClient.extract_verification_code("code: 123456", rules=rules)
        )

    def test_alnum_preset_continues_after_plain_word(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "Please enter ABC123",
                rules=rules,
            ),
            "ABC123",
        )

    def test_alnum_preset_rejects_lowercase_bare_code(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

        self.assertIsNone(
            CloudMailClient.extract_verification_code(
                "order abc123 shipped",
                rules=rules,
            )
        )

    def test_alnum_preset_continues_after_lowercase_bare_code(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "order abc123 CODE99",
                rules=rules,
            ),
            "CODE99",
        )

    def test_hyphen_preset_rejects_lowercase_bare_code(self):
        rules = {"enabled_presets": ["alnum_hyphen_3_3"], "custom_patterns": []}

        self.assertIsNone(
            CloudMailClient.extract_verification_code(
                "tracking abc-123 complete",
                rules=rules,
            )
        )

    def test_hyphen_preset_continues_after_lowercase_bare_code(self):
        rules = {"enabled_presets": ["alnum_hyphen_3_3"], "custom_patterns": []}

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "tracking abc-123 ABC-123",
                rules=rules,
            ),
            "ABC-123",
        )

    def test_digits_preset_continues_after_sentinel(self):
        rules = {"enabled_presets": ["digits_6"], "custom_patterns": []}

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "177010 654321",
                rules=rules,
            ),
            "654321",
        )

    def test_spaced_digits_preset_continues_after_sentinel(self):
        rules = {
            "enabled_presets": ["digits_spaced_3_3"],
            "custom_patterns": [],
        }

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "177 010 331 781",
                rules=rules,
            ),
            "331781",
        )

    def test_query_reloads_rules_without_recreating_client(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": [],
                    "custom_patterns": [
                        {"name": "Eight", "pattern": r"token: (\d{8})"}
                    ],
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


if __name__ == "__main__":
    unittest.main()
