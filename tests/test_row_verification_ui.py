import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class RowVerificationUiTest(unittest.TestCase):
    def test_history_table_has_compact_selection_and_verification_columns(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('class="history-select-col"', html)
        self.assertIn('class="history-code-col"', html)
        self.assertIn('class="history-code-result"', html)
        self.assertIn("quickQueryCode", html)

    def test_verification_column_follows_app_password(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        table_header = html.split('<table id="historyTable"', 1)[1].split("</thead>", 1)[0]
        history_renderer = html.split("async function loadHistory", 1)[1].split("async function setUsed", 1)[0]

        self.assertLess(table_header.index("history-app-password-col"), table_header.index("history-code-col"))
        self.assertLess(table_header.index("history-code-col"), table_header.index("history-name-col"))
        self.assertLess(history_renderer.index("history-app-password-col"), history_renderer.index("history-code-col"))
        self.assertLess(history_renderer.index("history-code-col"), history_renderer.index("history-name-col"))

    def test_row_query_uses_stored_profile_and_syncs_usage_state(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn("if (stored) return stored;", html)
        self.assertIn("matchedSuffixLength", html)
        self.assertIn("updateHistoryRowUsage(row, email, true)", html)
        self.assertIn("updateHistoryRowUsage(row, email, false)", html)
        usage_helper = html.split("function updateHistoryRowUsage", 1)[1].split("function toggleHistoryUsed", 1)[0]
        self.assertIn("currentInUseEmail = email", usage_helper)
        self.assertIn("currentInUseEmail = '';", usage_helper)

    def test_history_rows_escape_imported_values_and_avoid_inline_email_code(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn("escapeAttr(r.password || '')", html)
        self.assertIn("escapeAttr(r.name || '')", html)
        self.assertIn("escapeAttr(r.platforms || '')", html)
        self.assertIn('onclick="toggleHistoryUsed(this)"', html)
        self.assertNotIn('onclick="setUsed(\'${', html)

    def test_history_email_is_split_into_prefix_and_domain_lines(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn("splitEmailForDisplay", html)
        self.assertIn('class="history-email-prefix"', html)
        self.assertIn('class="history-email-domain"', html)

    def test_page_supports_persistent_light_and_dark_themes(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn(':root[data-theme="light"]', html)
        self.assertIn('id="themeToggle"', html)
        self.assertIn("applyTheme", html)
        self.assertIn("cloudmailmanual-theme", html)

    def test_mail_settings_exposes_verification_rule_editor(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        for control_id in (
            "verificationPresetOptions",
            "verificationCustomPatterns",
            "verificationRuleTestContent",
            "testVerificationRulesBtn",
            "saveVerificationRulesBtn",
            "verificationRulesStatus",
        ):
            self.assertIn(f'id="{control_id}"', html)

        for function_name in (
            "loadVerificationRules",
            "testVerificationRules",
            "saveVerificationRules",
        ):
            self.assertIn(f"function {function_name}", html)

        self.assertIn("loadVerificationRules();", html)
        self.assertIn("fetch('/api/settings/verification-code-rules')", html)
        self.assertIn("fetch('/api/settings/verification-code-rules/test'", html)

        preset_renderer = html.split("function renderVerificationPresets", 1)[1].split(
            "async function loadVerificationRules", 1
        )[0]
        self.assertIn("container.innerHTML = '';", preset_renderer)
        self.assertIn("document.createElement('label')", preset_renderer)
        self.assertIn("span.textContent = `${preset.label} (${preset.example})`;", preset_renderer)
        self.assertNotIn("innerHTML = `", preset_renderer)

        self.assertIn("验证码规则已保存，下次查询立即生效", html)


if __name__ == "__main__":
    unittest.main()
