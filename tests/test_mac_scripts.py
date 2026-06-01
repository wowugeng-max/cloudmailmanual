import stat
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class MacScriptsTest(unittest.TestCase):
    def test_double_click_scripts_exist_and_are_executable(self):
        for name in ("run_web_mac.command", "stop_web_mac.command"):
            path = ROOT / name
            self.assertTrue(path.exists(), f"{name} should exist")
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR, f"{name} should be executable")

    def test_start_script_can_resolve_port_without_starting_server(self):
        result = subprocess.run(
            ["bash", str(ROOT / "start_web_mac.sh"), "--print-port"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertRegex(result.stdout.strip(), r"^\d+$")

    def test_stop_script_supports_dry_run(self):
        result = subprocess.run(
            ["bash", str(ROOT / "stop_web_mac.sh"), "--dry-run"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn("Cloud Mail", result.stdout)


if __name__ == "__main__":
    unittest.main()
