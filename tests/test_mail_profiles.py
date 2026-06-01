import json
import tempfile
import unittest
from pathlib import Path

from cloudmailmanual_app.repositories import mail_profiles


class MailProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.original_config_path = mail_profiles.CONFIG_PATH
        mail_profiles.CONFIG_PATH = self.config_path

    def tearDown(self):
        mail_profiles.CONFIG_PATH = self.original_config_path
        self.tmpdir.cleanup()

    def write_config(self, data):
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def test_legacy_config_becomes_default_profile(self):
        self.write_config(
            {
                "cloud_mail_api_base": "https://api.example.test",
                "cloud_mail_admin_email": "admin@example.com",
                "cloud_mail_admin_password": "secret",
                "cloud_mail_role_name": "user",
                "proxy": "",
                "domain_suffix_options": ["example.com", "mx.example.com"],
                "default_domain_suffix": "mx.example.com",
                "web_port": 8080,
            }
        )

        data = mail_profiles.get_mail_profiles_config()

        self.assertEqual(data["active_profile_id"], "default")
        self.assertEqual(len(data["profiles"]), 1)
        profile = data["profiles"][0]
        self.assertEqual(profile["id"], "default")
        self.assertEqual(profile["name"], "admin@example.com")
        self.assertEqual(profile["cloud_mail_api_base"], "https://api.example.test")
        self.assertEqual(profile["default_domain_suffix"], "mx.example.com")

    def test_save_profiles_preserves_non_mail_config(self):
        self.write_config({"web_port": 8080, "admin_username": "admin", "admin_password": "pw"})

        saved = mail_profiles.save_mail_profiles_config(
            [
                {
                    "id": "work",
                    "name": "Work",
                    "cloud_mail_api_base": "https://api.work.test",
                    "cloud_mail_admin_email": "admin@work.test",
                    "cloud_mail_admin_password": "secret",
                    "cloud_mail_role_name": "",
                    "proxy": "",
                    "domain_suffix_options": ["work.test"],
                    "default_domain_suffix": "work.test",
                }
            ],
            active_profile_id="work",
        )

        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["active_profile_id"], "work")
        self.assertEqual(raw["web_port"], 8080)
        self.assertEqual(raw["admin_username"], "admin")
        self.assertEqual(raw["mail_profiles"][0]["id"], "work")
        self.assertNotIn("cloud_mail_api_base", raw)

    def test_get_mail_profile_by_id_falls_back_to_active(self):
        self.write_config(
            {
                "active_mail_profile_id": "b",
                "mail_profiles": [
                    {
                        "id": "a",
                        "name": "A",
                        "cloud_mail_api_base": "https://api.a.test",
                        "cloud_mail_admin_email": "admin@a.test",
                        "cloud_mail_admin_password": "secret-a",
                    },
                    {
                        "id": "b",
                        "name": "B",
                        "cloud_mail_api_base": "https://api.b.test",
                        "cloud_mail_admin_email": "admin@b.test",
                        "cloud_mail_admin_password": "secret-b",
                    },
                ],
            }
        )

        profile = mail_profiles.get_mail_profile_by_id("")

        self.assertEqual(profile["id"], "b")
        self.assertEqual(profile["cloud_mail_admin_email"], "admin@b.test")


if __name__ == "__main__":
    unittest.main()
