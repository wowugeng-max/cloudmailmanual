import subprocess
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

        self.assertIn("function setVerificationRulesBusy", html)
        self.assertIn("let verificationRulesBusy = false;", html)
        self.assertIn(
            '<label for="verificationCustomPatterns">自定义正则</label>',
            html,
        )
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

        self.assertIn(
            'id="testVerificationRulesBtn" class="btn-secondary" '
            'onclick="testVerificationRules()"',
            html,
        )
        self.assertIn(
            'id="saveVerificationRulesBtn" onclick="saveVerificationRules()"',
            html,
        )
        self.assertIn("loadVerificationRules();", html)
        self.assertIn("fetch('/api/settings/verification-code-rules')", html)
        self.assertIn("fetch('/api/settings/verification-code-rules/test'", html)

        busy_helper = html.split("function setVerificationRulesBusy", 1)[1].split(
            "function collectVerificationRules", 1
        )[0]
        for expected in (
            "testVerificationRulesBtn",
            "saveVerificationRulesBtn",
            "verificationCustomPatterns",
            "verificationRuleTestContent",
            "[data-verification-preset]",
            "element.disabled = isBusy",
            "input.disabled = isBusy",
        ):
            self.assertIn(expected, busy_helper)

        collector = html.split("function collectVerificationRules", 1)[1].split(
            "function renderVerificationPresets", 1
        )[0]
        for expected in (
            "enabled_presets",
            "custom_patterns_text",
            "[data-verification-preset]:checked",
            "verificationCustomPatterns",
        ):
            self.assertIn(expected, collector)

        preset_renderer = html.split("function renderVerificationPresets", 1)[1].split(
            "async function loadVerificationRules", 1
        )[0]
        self.assertIn("container.innerHTML = '';", preset_renderer)
        self.assertIn("document.createElement('label')", preset_renderer)
        self.assertIn("span.textContent = `${preset.label} (${preset.example})`;", preset_renderer)
        self.assertIn("input.disabled = verificationRulesBusy;", preset_renderer)
        self.assertNotIn("innerHTML = `", preset_renderer)

        load_rules = html.split("async function loadVerificationRules", 1)[1].split(
            "async function testVerificationRules", 1
        )[0]
        for expected in (
            "if (verificationRulesBusy) return;",
            "setVerificationRulesBusy(true);",
            "finally {",
            "setVerificationRulesBusy(false);",
        ):
            self.assertIn(expected, load_rules)

        test_rules = html.split("async function testVerificationRules", 1)[1].split(
            "async function saveVerificationRules", 1
        )[0]
        for expected in (
            "...collectVerificationRules()",
            "verificationRuleTestContent",
            "/api/settings/verification-code-rules/test",
            "method: 'POST'",
            "JSON.stringify(payload)",
            "status.textContent = `提取结果：${data.code}`;",
            "status.textContent = `测试失败：${e.message || e}`;",
            "if (verificationRulesBusy) return;",
            "setVerificationRulesBusy(true);",
            "finally {",
            "setVerificationRulesBusy(false);",
        ):
            self.assertIn(expected, test_rules)
        self.assertLess(
            test_rules.index("const payload = {"),
            test_rules.index("setVerificationRulesBusy(true);"),
        )
        self.assertNotIn("saveMailProfiles", test_rules)

        save_rules = html.split("async function saveVerificationRules", 1)[1].split(
            "async function saveMaxLimit", 1
        )[0]
        for expected in (
            "/api/settings/verification-code-rules",
            "method: 'POST'",
            "const payload = collectVerificationRules();",
            "JSON.stringify(payload)",
            "if (verificationRulesBusy) return;",
            "setVerificationRulesBusy(true);",
            "finally {",
            "setVerificationRulesBusy(false);",
            "renderVerificationPresets(data.enabled_presets || []);",
            "document.getElementById('verificationCustomPatterns').value",
            "status.textContent = '验证码规则已保存，下次查询立即生效';",
            "status.textContent = `保存失败：${e.message || e}`;",
        ):
            self.assertIn(expected, save_rules)
        self.assertLess(
            save_rules.index("const payload = collectVerificationRules();"),
            save_rules.index("setVerificationRulesBusy(true);"),
        )
        self.assertNotIn("saveMailProfiles", save_rules)

        save_mail_profiles = html.split("async function saveMailProfiles", 1)[1].split(
            "function setVerificationRulesBusy", 1
        )[0]
        self.assertNotIn("saveVerificationRules", save_mail_profiles)

        self.assertIn("验证码规则已保存，下次查询立即生效", html)

    def test_verification_rule_requests_share_busy_state(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        main_script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync(0, 'utf8');
const presetInputs = [];
const makeElement = (id = '') => ({
  id,
  value: '',
  disabled: false,
  checked: false,
  dataset: {},
  children: [],
  className: '',
  textContent: '',
  appendChild(child) { this.children.push(child); },
});
const elements = {
  testVerificationRulesBtn: makeElement('testVerificationRulesBtn'),
  saveVerificationRulesBtn: makeElement('saveVerificationRulesBtn'),
  verificationCustomPatterns: makeElement('verificationCustomPatterns'),
  verificationRuleTestContent: makeElement('verificationRuleTestContent'),
  verificationPresetOptions: makeElement('verificationPresetOptions'),
  verificationRulesStatus: makeElement('verificationRulesStatus'),
};
elements.verificationCustomPatterns.value = 'Six :: code: (\\d{6})';
elements.verificationRuleTestContent.value = 'code: 123456';

const document = {
  documentElement: { dataset: {} },
  getElementById(id) { return elements[id] || null; },
  querySelectorAll(selector) {
    if (selector === '[data-verification-preset]:checked') {
      return presetInputs.filter((input) => input.checked);
    }
    if (selector === '[data-verification-preset]') return presetInputs;
    return [];
  },
  createElement(tagName) {
    const element = makeElement();
    if (tagName === 'input') presetInputs.push(element);
    return element;
  },
};
const context = vm.createContext({
  document,
  window: { addEventListener() {} },
  console,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  navigator: {},
});
vm.runInContext(source, context);

(async () => {
  vm.runInContext(`
    verificationPresetMetadata = [
      { id: 'digits_6', label: 'Six digits', example: '123456' },
    ];
    renderVerificationPresets(['digits_6']);
  `, context);
  assert.strictEqual(presetInputs.length, 1);
  assert.strictEqual(presetInputs[0].checked, true);

  let fetchCount = 0;
  let resolveFetch;
  context.fetch = () => {
    fetchCount += 1;
    return new Promise((resolve) => { resolveFetch = resolve; });
  };

  const testRequest = vm.runInContext('testVerificationRules()', context);
  const ignoredSave = vm.runInContext('saveVerificationRules()', context);
  await ignoredSave;

  assert.strictEqual(fetchCount, 1);
  for (const id of [
    'testVerificationRulesBtn',
    'saveVerificationRulesBtn',
    'verificationCustomPatterns',
    'verificationRuleTestContent',
  ]) {
    assert.strictEqual(elements[id].disabled, true, `${id} should be disabled`);
  }
  assert.strictEqual(presetInputs[0].disabled, true);

  resolveFetch({
    ok: true,
    json: async () => ({ ok: true, code: '123456' }),
  });
  await testRequest;

  assert.strictEqual(elements.verificationRulesStatus.textContent, '提取结果：123456');
  for (const id of [
    'testVerificationRulesBtn',
    'saveVerificationRulesBtn',
    'verificationCustomPatterns',
    'verificationRuleTestContent',
  ]) {
    assert.strictEqual(elements[id].disabled, false, `${id} should be enabled`);
  }
  assert.strictEqual(presetInputs[0].disabled, false);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
        result = subprocess.run(
            ["node", "-e", harness],
            input=main_script,
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
