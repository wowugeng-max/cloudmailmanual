import json
import itertools
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, call, patch

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

    def test_save_rejects_non_object_root_without_overwriting(self):
        self.write_config([{"recoverable": "value"}])
        original = self.config_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "根配置必须是对象"):
            verification_rules.save_verification_code_rules(
                {
                    "enabled_presets": ["digits_6"],
                    "custom_patterns_text": "",
                }
            )

        self.assertEqual(self.config_path.read_bytes(), original)

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

    def test_custom_pattern_match_has_time_budget(self):
        script = r"""
import time

from cloud_mail_client import CloudMailClient

rules = {
    "enabled_presets": [],
    "custom_patterns": [{"name": "Slow", "pattern": "((a+)+$)"}],
}
try:
    started = time.monotonic()
    CloudMailClient.extract_verification_code("a" * 100000 + "X", rules=rules)
except ValueError as exc:
    if "匹配超时" not in str(exc):
        raise
    if time.monotonic() - started > 0.75:
        raise SystemExit("custom pattern timeout exceeded its runtime budget")
else:
    raise SystemExit("expected the unsafe custom pattern to time out")
"""
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.fail("自定义正则匹配超过 5 秒，未受时间预算保护")

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_query_deadline_does_not_bypass_single_extraction_budget(self):
        clock_ticks = itertools.count()
        rules = {
            "enabled_presets": [],
            "custom_patterns": [
                {"name": f"Rule {index}", "pattern": r"token: (\d{6})"}
                for index in range(10)
            ],
        }

        with (
            patch(
                "cloud_mail_client.time.monotonic",
                side_effect=lambda: 100.0 + next(clock_ticks) * 0.06,
            ),
            patch("cloud_mail_client.regex.finditer", return_value=[]),
        ):
            with self.assertRaisesRegex(ValueError, "匹配超时"):
                CloudMailClient.extract_verification_code(
                    "no code",
                    rules=rules,
                    custom_pattern_deadline=1000.0,
                )

    def test_labeled_code_preset_extracts_verification_code(self):
        rules = {"enabled_presets": ["labeled_code"], "custom_patterns": []}

        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "Verification code: 123456",
                rules=rules,
            ),
            "123456",
        )

    def test_disabled_labeled_code_preset_does_not_match(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

        self.assertIsNone(
            CloudMailClient.extract_verification_code(
                "Verification code: 123456",
                rules=rules,
            )
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

    def test_plain_text_mode_preserves_literal_angle_bracket_code(self):
        rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

        self.assertIsNone(
            CloudMailClient.extract_verification_code(
                "<ABC123>",
                rules=rules,
            )
        )
        self.assertEqual(
            CloudMailClient.extract_verification_code(
                "<ABC123>",
                content_is_plain_text=True,
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

    def test_query_detail_returns_link_only_without_code(self):
        href = "https://example.test/verify?token=ABC123"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": f'<a href="{href}">{href}</a>',
                "sendEmail": "sender@example.test",
                "subject": "Please verify",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Please verify",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_ignores_entity_encoded_html_url_token_as_code(self):
        href = "https://example.test/verify?token=ABC123"
        encoded_hrefs = (
            "https:&#47;&#47;example.test/verify?token=ABC123",
            "htt&#112;s://example.test/verify?token=ABC123",
            "https&#58;&#47;&#47;example.test/verify?token=ABC123",
        )

        for encoded_href in encoded_hrefs:
            with self.subTest(encoded_href=encoded_href):
                client = CloudMailClient.__new__(CloudMailClient)
                client._email_list = lambda **_: [
                    {
                        "content": f"<p>Activate using {encoded_href}</p>",
                        "sendEmail": "sender@example.test",
                        "subject": "Activate your account",
                        "createTime": "2026-07-29 10:00:00",
                    }
                ]

                self.assertEqual(
                    client.query_verification_detail("a@example.com"),
                    {
                        "code": "",
                        "verification_url": href,
                        "sender": "sender@example.test",
                        "subject": "Activate your account",
                        "received_time": "2026-07-29 10:00:00",
                    },
                )

    def test_query_detail_keeps_code_outside_entity_encoded_html_url(self):
        href = "https://example.test/verify?token=ABC123"
        encoded_href = "htt&#112;s://example.test/verify?token=ABC123"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": (
                    "<p>Your verification code is 654321. "
                    f"Activate using {encoded_href}</p>"
                ),
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "654321",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_extracts_angle_bracket_code_and_entity_scheme_link(self):
        href = "https://example.test/verify-email?token=XYZ789"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": (
                    "<p>Your verification code is &lt;ABC123&gt; "
                    "Activate using "
                    "https&#58;//example.test/verify-email?token=XYZ789</p>"
                ),
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "ABC123",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_does_not_extract_codes_from_hidden_html(self):
        href = "https://example.test/verify-email?token=XYZ789"
        encoded_href = "https&#58;//example.test/verify-email?token=XYZ789"
        hidden_fragments = (
            ("attribute", '<div title="&gt;ABC123"></div>'),
            ("head", "<head>&lt;/head&gt;ABC123</head>"),
            ("script", "<script>&lt;/script&gt;ABC123</script>"),
            ("style", "<style>&lt;/style&gt;ABC123</style>"),
            ("template", "<template>&lt;/template&gt;ABC123</template>"),
        )

        for case, hidden_fragment in hidden_fragments:
            with self.subTest(case=case):
                client = CloudMailClient.__new__(CloudMailClient)
                client._email_list = lambda **_: [
                    {
                        "content": (
                            f"{hidden_fragment}"
                            f"<p>Activate using {encoded_href}</p>"
                        ),
                        "sendEmail": "sender@example.test",
                        "subject": "Activate your account",
                        "createTime": "2026-07-29 10:00:00",
                    }
                ]

                self.assertEqual(
                    client.query_verification_detail("a@example.com"),
                    {
                        "code": "",
                        "verification_url": href,
                        "sender": "sender@example.test",
                        "subject": "Activate your account",
                        "received_time": "2026-07-29 10:00:00",
                    },
                )

    def test_query_detail_ignores_code_after_mismatched_hidden_end_tag(self):
        href = "https://example.test/verify?token=XYZ789"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": (
                    "<head></style>ABC123</head>"
                    f"<p>Activate using {href}</p>"
                ),
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_uses_literal_url_masking_for_plain_text(self):
        href = (
            "https://example.test/verify?x=1"
            "&NewLine;token=ABC123"
        )
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "text": f"Activate using {href}",
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_defers_body_masking_when_subject_matches(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": [],
                    "custom_patterns": [
                        {
                            "name": "Subject token",
                            "pattern": r"subject-token: ([A-Z0-9]{6})",
                        }
                    ],
                }
            }
        )
        large_body = "&amp;" * 200_000
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "subject": "subject-token: ABC123",
                "text": large_body,
                "content": large_body,
            }
        ]

        with (
            patch("cloud_mail_client.mask_http_urls", return_value="") as mask_urls,
            patch(
                "cloud_mail_client.extract_verification_link",
                return_value=None,
            ) as extract_link,
        ):
            detail = client.query_verification_detail("a@example.com")

        mask_urls.assert_not_called()
        extract_link.assert_called_once_with(large_body, large_body)
        self.assertEqual(detail["code"], "ABC123")

    def test_query_detail_defers_html_parsing_when_text_alnum_matches(self):
        self.write_config(
            {
                "verification_code_rules": {
                    "enabled_presets": ["alnum_6"],
                    "custom_patterns": [],
                }
            }
        )
        text = "Your verification code is ABC123"
        html = "<p>Your verification code is XYZ789</p>"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "subject": "Verification message",
                "text": text,
                "content": html,
            }
        ]

        with (
            patch(
                "cloud_mail_client.extract_visible_html_text",
                return_value="Your verification code is XYZ789",
                create=True,
            ) as visible_html,
            patch(
                "cloud_mail_client.mask_http_urls",
                side_effect=lambda value, **_: value,
            ) as mask_urls,
            patch("cloud_mail_client.extract_verification_link", return_value=None),
        ):
            detail = client.query_verification_detail("a@example.com")

        visible_html.assert_not_called()
        mask_urls.assert_called_once_with(text)
        self.assertEqual(detail["code"], "ABC123")

    def test_query_detail_preserves_lazy_body_extraction_order(self):
        subject = "Subject without a code"
        text = "Text body 123456"
        html = "<p>HTML body 654321</p>"
        visible_html = "HTML body 654321"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {"subject": subject, "text": text, "content": html}
        ]

        with (
            patch.object(
                CloudMailClient,
                "extract_verification_code",
                side_effect=[None, None, None, None, None, "654321"],
            ) as extract_code,
            patch(
                "cloud_mail_client.extract_visible_html_text",
                return_value=visible_html,
                create=True,
            ) as extract_visible,
            patch(
                "cloud_mail_client.mask_http_urls",
                side_effect=lambda value, **_: f"masked:{value}",
            ) as mask_urls,
            patch("cloud_mail_client.extract_verification_link", return_value=None),
        ):
            detail = client.query_verification_detail("a@example.com")

        extract_visible.assert_called_once_with(html)
        self.assertEqual(
            mask_urls.call_args_list,
            [call(text), call(visible_html)],
        )
        self.assertEqual(
            extract_code.call_args_list,
            [
                call(
                    subject,
                    allow_digits=False,
                    rules=ANY,
                    custom_pattern_deadline=ANY,
                ),
                call(
                    subject,
                    allow_digits=True,
                    rules=ANY,
                    custom_pattern_deadline=ANY,
                ),
                call(
                    f"masked:{text}",
                    allow_digits=False,
                    content_is_plain_text=True,
                    rules=ANY,
                    custom_pattern_deadline=ANY,
                ),
                call(
                    f"masked:{visible_html}",
                    allow_digits=False,
                    content_is_plain_text=True,
                    rules=ANY,
                    custom_pattern_deadline=ANY,
                ),
                call(
                    f"masked:{text}",
                    allow_digits=True,
                    content_is_plain_text=True,
                    rules=ANY,
                    custom_pattern_deadline=ANY,
                ),
                call(
                    f"masked:{visible_html}",
                    allow_digits=True,
                    content_is_plain_text=True,
                    rules=ANY,
                    custom_pattern_deadline=ANY,
                ),
            ],
        )
        self.assertEqual(detail["code"], "654321")

    def test_query_detail_returns_plain_text_bare_link_without_html(self):
        href = "https://example.test/verify-email?token=synthetic-value"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "text": f"Activate your account using {href}",
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_ignores_plain_text_url_token_as_code(self):
        href = "https://example.test/verify-email?token=ABC123"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "text": f"Activate using {href}",
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_keeps_code_outside_plain_text_url(self):
        href = "https://example.test/verify-email?token=ABC123"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "text": (
                    "Your verification code is 654321. "
                    f"Activate using {href}"
                ),
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "654321",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Activate your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_passes_html_and_text_to_link_extractor(self):
        href = "https://example.test/verify-email?token=synthetic-value"
        html = f'<a href="{href}">Activate your account</a>'
        text = f"Activate your account using {href}"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": html,
                "text": text,
                "sendEmail": "sender@example.test",
                "subject": "Activate your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        with patch(
            "cloud_mail_client.extract_verification_link",
            return_value=href,
        ) as link_extractor:
            detail = client.query_verification_detail("a@example.com")

        link_extractor.assert_called_once_with(html, text)
        self.assertEqual(detail["verification_url"], href)

    def test_query_detail_returns_code_and_link_from_same_message(self):
        href = "https://example.test/confirm?token=redacted"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": f'<p>Code: 123456</p><a href="{href}">Confirm</a>',
                "text": "Code: 123456",
                "sendEmail": "sender@example.test",
                "subject": "Confirm your account",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "123456",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Confirm your account",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_includes_empty_link_for_code_only_message(self):
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "text": "Your verification code is 123456",
                "sendEmail": "sender@example.test",
                "subject": "Verification code",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "123456",
                "verification_url": "",
                "sender": "sender@example.test",
                "subject": "Verification code",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_verification_code_remains_none_for_link_only_message(self):
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": (
                    '<a href="https://example.test/verify?token=redacted">'
                    "Verify"
                    "</a>"
                )
            }
        ]

        self.assertIsNone(client.query_verification_code("a@example.com"))

    def test_link_extraction_failure_does_not_break_code_query(self):
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": "<p>Your code is 123456</p>",
                "text": "Your code is 123456",
            }
        ]

        with patch(
            "cloud_mail_client.extract_verification_link",
            side_effect=ValueError("malformed input"),
        ):
            detail = client.query_verification_detail("a@example.com")
            code = client.query_verification_code("a@example.com")

        self.assertEqual(code, "123456")
        self.assertEqual(detail["code"], "123456")
        self.assertEqual(detail["verification_url"], "")

    def test_query_does_not_combine_results_from_different_messages(self):
        first_href = "https://example.test/verify?token=first"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": f'<a href="{first_href}">Verify</a>',
                "sendEmail": "first@example.test",
                "subject": "Verify first",
                "createTime": "2026-07-29 10:00:00",
            },
            {
                "text": "Your verification code is 654321",
                "sendEmail": "second@example.test",
                "subject": "Code second",
                "createTime": "2026-07-29 09:00:00",
            },
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": first_href,
                "sender": "first@example.test",
                "subject": "Verify first",
                "received_time": "2026-07-29 10:00:00",
            },
        )


if __name__ == "__main__":
    unittest.main()
