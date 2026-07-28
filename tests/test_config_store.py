import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cloudmailmanual_app.repositories import config_store, mail_profiles, verification_rules


class SharedConfigStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.config_path.write_text('{"web_port": 8080}', encoding="utf-8")
        self.original_mail_config_path = mail_profiles.CONFIG_PATH
        self.original_rule_config_path = verification_rules.CONFIG_PATH
        mail_profiles.CONFIG_PATH = self.config_path
        verification_rules.CONFIG_PATH = self.config_path

    def tearDown(self):
        mail_profiles.CONFIG_PATH = self.original_mail_config_path
        verification_rules.CONFIG_PATH = self.original_rule_config_path
        self.tmpdir.cleanup()

    def test_concurrent_repository_saves_preserve_both_updates(self):
        original_read = config_store._read_config_unlocked
        state_lock = threading.Lock()
        active_reads = 0
        max_active_reads = 0

        def slow_read(path):
            nonlocal active_reads, max_active_reads
            with state_lock:
                active_reads += 1
                max_active_reads = max(max_active_reads, active_reads)
            try:
                time.sleep(0.05)
                return original_read(path)
            finally:
                with state_lock:
                    active_reads -= 1

        profile = {
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
        errors = []

        def save_profiles():
            try:
                mail_profiles.save_mail_profiles_config([profile], "work")
            except Exception as exc:
                errors.append(exc)

        def save_rules():
            try:
                verification_rules.save_verification_code_rules(
                    {
                        "enabled_presets": ["digits_6"],
                        "custom_patterns_text": "",
                    }
                )
            except Exception as exc:
                errors.append(exc)

        with patch.object(config_store, "_read_config_unlocked", side_effect=slow_read):
            threads = [
                threading.Thread(target=save_profiles),
                threading.Thread(target=save_rules),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(max_active_reads, 1)
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["web_port"], 8080)
        self.assertEqual(saved["mail_profiles"][0]["id"], "work")
        self.assertEqual(
            saved["verification_code_rules"]["enabled_presets"],
            ["digits_6"],
        )

    def test_atomic_write_failures_preserve_original_and_clean_temporary_file(self):
        original = self.config_path.read_bytes()
        failures = (
            (config_store.json, "dump"),
            (config_store.os, "fsync"),
            (config_store.os, "replace"),
        )

        for owner, attribute in failures:
            with self.subTest(attribute=attribute):
                with patch.object(owner, attribute, side_effect=OSError("disk failure")):
                    with self.assertRaisesRegex(OSError, "disk failure"):
                        config_store.update_config(
                            self.config_path,
                            lambda config: config.update({"new_value": attribute}),
                        )

                self.assertEqual(self.config_path.read_bytes(), original)
                self.assertEqual(
                    list(self.config_path.parent.glob(f".{self.config_path.name}.*.tmp")),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
