import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auth

from cloudmailmanual_app import database, routes
from cloudmailmanual_app.factory import create_app
from cloudmailmanual_app.repositories import verification_rules


class VerificationRulesApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.config_path.write_text('{"web_port":8080}', encoding="utf-8")
        self.original_config_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path
        self.database_path = Path(self.tmpdir.name) / "cloudmailmanual.db"
        self.original_database_path = database.DB_PATH
        self.original_auth_database_path = auth.DB_PATH
        database.DB_PATH = self.database_path
        auth.DB_PATH = self.database_path

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_config_path
        database.DB_PATH = self.original_database_path
        auth.DB_PATH = self.original_auth_database_path
        self.tmpdir.cleanup()

    def login(self):
        with self.client.session_transaction() as session:
            session["user"] = "admin"

    def test_get_returns_normalized_rules_and_available_presets(self):
        self.login()

        response = self.client.get("/api/settings/verification-code-rules")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["available_presets"]), 5)
        self.assertEqual(
            data["enabled_presets"],
            [item["id"] for item in verification_rules.PRESET_METADATA],
        )
        self.assertEqual(data["custom_patterns"], [])
        self.assertEqual(data["custom_patterns_text"], "")

    def test_verification_rule_endpoints_require_login(self):
        requests = [
            ("get", "/api/settings/verification-code-rules"),
            ("post", "/api/settings/verification-code-rules"),
            ("post", "/api/settings/verification-code-rules/test"),
        ]

        for method, path in requests:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json()["ok"], False)

    def test_create_app_uses_temporary_database(self):
        self.assertEqual(database.DB_PATH, self.database_path)
        self.assertEqual(auth.DB_PATH, self.database_path)
        self.assertTrue(self.database_path.exists())

    def test_save_rejects_non_object_json(self):
        self.login()

        for payload in ([], ["rules"], "rules", 123, True):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/settings/verification-code-rules",
                    json=payload,
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json(),
                    {"ok": False, "error": "请求体必须是对象"},
                )

    def test_test_endpoint_rejects_non_object_json(self):
        self.login()

        for payload in ([], ["rules"], "rules", 123, True):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/settings/verification-code-rules/test",
                    json=payload,
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json(),
                    {"ok": False, "error": "请求体必须是对象"},
                )

    def test_test_endpoint_rejects_non_string_content(self):
        self.login()

        for content in (123, ["123456"], {"code": "123456"}, True, None):
            with self.subTest(content=content):
                response = self.client.post(
                    "/api/settings/verification-code-rules/test",
                    json={
                        "content": content,
                        "enabled_presets": ["digits_6"],
                        "custom_patterns_text": "",
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("content 必须是字符串", response.get_json()["error"])

    def test_invalid_save_returns_400_without_changing_config(self):
        self.login()
        original_config = self.config_path.read_bytes()

        response = self.client.post(
            "/api/settings/verification-code-rules",
            json={
                "enabled_presets": [],
                "custom_patterns_text": "Bad :: ([",
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("正则表达式无效", data["error"])
        self.assertEqual(self.config_path.read_bytes(), original_config)

    def test_invalid_structured_rules_do_not_change_config(self):
        self.login()
        original_config = self.config_path.read_bytes()

        response = self.client.post(
            "/api/settings/verification-code-rules",
            json={
                "enabled_presets": ["digits_6"],
                "custom_patterns": [{"name": 123, "pattern": r"(\d{6})"}],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "custom_patterns 第 1 项",
            response.get_json()["error"],
        )
        self.assertEqual(self.config_path.read_bytes(), original_config)

    def test_valid_save_does_not_report_corrupt_config_as_client_error(self):
        self.login()
        self.config_path.write_text("{broken", encoding="utf-8")
        self.app.testing = True

        with self.assertRaises(json.JSONDecodeError):
            self.client.post(
                "/api/settings/verification-code-rules",
                json={
                    "enabled_presets": ["digits_6"],
                    "custom_patterns_text": "",
                },
            )

    def test_successful_save_returns_normalized_rules(self):
        self.login()

        response = self.client.post(
            "/api/settings/verification-code-rules",
            json={
                "enabled_presets": [],
                "custom_patterns_text": r"Eight :: token: (\d{8})",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(
            data["custom_patterns"],
            [{"name": "Eight", "pattern": r"token: (\d{8})"}],
        )
        self.assertEqual(data["custom_patterns_text"], r"Eight :: token: (\d{8})")
        self.assertIn('"web_port": 8080', self.config_path.read_text(encoding="utf-8"))

    def test_save_returns_json_500_when_atomic_write_fails(self):
        self.login()
        original_config = self.config_path.read_bytes()

        with patch.object(
            routes,
            "save_verification_code_rules",
            side_effect=OSError("disk full"),
        ):
            response = self.client.post(
                "/api/settings/verification-code-rules",
                json={
                    "enabled_presets": ["digits_6"],
                    "custom_patterns_text": "",
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"ok": False, "error": "disk full"})
        self.assertEqual(self.config_path.read_bytes(), original_config)

    def test_test_endpoint_uses_unsaved_rules_without_side_effects(self):
        self.login()
        original_config = self.config_path.read_bytes()
        payload = {
            "content": "token: 87654321",
            "enabled_presets": [],
            "custom_patterns_text": r"Eight :: token: (\d{8})",
        }

        with (
            patch.object(routes, "save_verification_code_rules", create=True) as save_rules,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
            patch.object(routes.CloudMailClient, "_email_list") as email_list,
        ):
            response = self.client.post(
                "/api/settings/verification-code-rules/test",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "code": "87654321"})
        save_rules.assert_not_called()
        save_query.assert_not_called()
        mark_used.assert_not_called()
        email_list.assert_not_called()
        self.assertEqual(self.config_path.read_bytes(), original_config)

    def test_test_endpoint_rejects_content_over_100000_characters(self):
        self.login()

        response = self.client.post(
            "/api/settings/verification-code-rules/test",
            json={
                "content": "x" * 100001,
                "enabled_presets": ["digits_6"],
                "custom_patterns_text": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"ok": False, "error": "测试内容最多 100000 个字符"},
        )

    def test_test_endpoint_reports_custom_pattern_timeout(self):
        self.login()

        response = self.client.post(
            "/api/settings/verification-code-rules/test",
            json={
                "content": "a" * 99999 + "X",
                "enabled_presets": [],
                "custom_patterns_text": "Slow :: ((a+)+$)",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["ok"], False)
        self.assertIn("自定义验证码规则匹配超时: Slow", response.get_json()["error"])

    def test_query_code_includes_empty_verification_url_when_no_message(self):
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = None
            response = self.client.post(
                "/api/query-code", json={"email": "a@example.com"}
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["verification_url"], "")
        self.assertFalse(data["saved"])
        self.assertFalse(data["auto_marked_used"])
        save_query.assert_not_called()
        mark_used.assert_called_once_with(
            "a@example.com", used=False, platform=""
        )

    def test_link_only_query_returns_url_without_history_and_marks_unused(self):
        href = "https://awstrack.me/L0/https:%2F%2Fservice.test%2Fverify?token=redacted"
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": None,
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": None,
                "received_time": "2026-07-29 10:00:00",
            }
            response = self.client.post(
                "/api/query-code", json={"email": "a@example.com"}
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["code"], "")
        self.assertEqual(data["verification_url"], href)
        self.assertEqual(data["subject"], "")
        self.assertFalse(data["saved"])
        self.assertFalse(data["auto_marked_used"])
        save_query.assert_not_called()
        mark_used.assert_called_once_with(
            "a@example.com", used=False, platform=""
        )

    def test_code_plus_link_is_saved_without_persisting_url_and_marks_used(self):
        href = "https://example.test/confirm?token=redacted"
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": "123456",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Confirm",
                "received_time": "2026-07-29 10:00:00",
            }
            response = self.client.post(
                "/api/query-code",
                json={"email": "a@example.com", "platform": "Test"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["code"], "123456")
        self.assertEqual(data["verification_url"], href)
        self.assertTrue(data["saved"])
        self.assertTrue(data["auto_marked_used"])
        save_query.assert_called_once_with(
            "a@example.com",
            {
                "code": "123456",
                "sender": "sender@example.test",
                "subject": "Confirm",
                "received_time": "2026-07-29 10:00:00",
            },
        )
        self.assertNotIn("verification_url", save_query.call_args.args[1])
        mark_used.assert_called_once_with(
            "a@example.com", used=True, platform="Test"
        )

    def test_url_bearing_metadata_is_masked_only_in_saved_history(self):
        href = "https://example.test/confirm?token=ABC123"
        sender = "https://metadata.example.test/sender?token=SENDER123"
        subject = f"Verification code: 654321\n  Activate using {href}  now"
        received_time = (
            "2026-07-29 10:00:00 "
            "https://metadata.example.test/time?token=TIME123"
        )
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": "654321",
                "verification_url": href,
                "sender": sender,
                "subject": subject,
                "received_time": received_time,
            }
            response = self.client.post(
                "/api/query-code",
                json={"email": "a@example.com", "platform": "Test"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["verification_url"], href)
        self.assertEqual(data["sender"], sender)
        self.assertEqual(data["subject"], subject)
        self.assertEqual(data["received_time"], received_time)
        save_query.assert_called_once_with(
            "a@example.com",
            {
                "code": "654321",
                "sender": "",
                "subject": "Verification code: 654321 Activate using now",
                "received_time": "2026-07-29 10:00:00",
            },
        )
        saved_detail = repr(save_query.call_args.args[1])
        self.assertNotIn("http", saved_detail)
        self.assertNotIn("token=", saved_detail)
        self.assertNotIn("ABC123", saved_detail)
        mark_used.assert_called_once_with(
            "a@example.com", used=True, platform="Test"
        )

    def test_missing_platform_uses_sanitized_sender_or_fallback(self):
        href = "https://metadata.example.test/sender?token=SENDER123"
        cases = (
            (f"Mail service {href}", "Mail service"),
            (href, "验证码查询"),
        )
        self.login()

        for sender, expected_platform in cases:
            with self.subTest(sender=sender):
                with (
                    patch.object(routes, "CloudMailClient") as client_class,
                    patch.object(routes, "save_verification_query") as save_query,
                    patch.object(routes, "mark_account_used") as mark_used,
                ):
                    client_class.return_value.query_verification_detail.return_value = {
                        "code": "654321",
                        "verification_url": "",
                        "sender": sender,
                        "subject": "Verification code",
                        "received_time": "2026-07-29 10:00:00",
                    }
                    response = self.client.post(
                        "/api/query-code",
                        json={"email": "a@example.com"},
                    )

                data = response.get_json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(data["sender"], sender)
                self.assertEqual(data["mark_platform"], expected_platform)
                mark_used.assert_called_once_with(
                    "a@example.com",
                    used=True,
                    platform=expected_platform,
                )
                self.assertNotIn("http", repr(save_query.call_args.args[1]))
                self.assertNotIn("token=", repr(save_query.call_args.args[1]))
                self.assertNotIn("http", repr(mark_used.call_args))
                self.assertNotIn("token=", repr(mark_used.call_args))

    def test_code_only_query_normalizes_missing_link_and_marks_used(self):
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": "123456",
                "verification_url": None,
                "sender": "sender@example.test",
                "subject": "Code",
                "received_time": "2026-07-29 10:00:00",
            }
            response = self.client.post(
                "/api/query-code",
                json={"email": "a@example.com", "platform": "Test"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["code"], "123456")
        self.assertEqual(data["verification_url"], "")
        self.assertTrue(data["saved"])
        self.assertTrue(data["auto_marked_used"])
        save_query.assert_called_once_with(
            "a@example.com",
            {
                "code": "123456",
                "sender": "sender@example.test",
                "subject": "Code",
                "received_time": "2026-07-29 10:00:00",
            },
        )
        self.assertNotIn("verification_url", save_query.call_args.args[1])
        mark_used.assert_called_once_with(
            "a@example.com", used=True, platform="Test"
        )

    def test_query_code_requires_login(self):
        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            response = self.client.post(
                "/api/query-code", json={"email": "a@example.com"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["ok"])
        client_class.assert_not_called()
        save_query.assert_not_called()
        mark_used.assert_not_called()


if __name__ == "__main__":
    unittest.main()
