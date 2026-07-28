import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cloudmailmanual_app import routes
from cloudmailmanual_app.factory import create_app
from cloudmailmanual_app.repositories import verification_rules


class VerificationRulesApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.config_path.write_text('{"web_port":8080}', encoding="utf-8")
        self.original_config_path = verification_rules.CONFIG_PATH
        verification_rules.CONFIG_PATH = self.config_path

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        verification_rules.CONFIG_PATH = self.original_config_path
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

    def test_get_requires_login(self):
        response = self.client.get("/api/settings/verification-code-rules")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["ok"], False)

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


if __name__ == "__main__":
    unittest.main()
