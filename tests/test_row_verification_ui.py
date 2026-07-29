import re
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

    def test_tab_panels_allow_wide_tables_to_scroll_inside_cards(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r"\.tab-pane\s*\{[^}]*min-width:\s*0")

    def test_top_query_tables_have_verification_link_columns(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        for table_id in ("queryResultTable", "queryOnlyResultTable"):
            table_marker = f'<table id="{table_id}"'
            self.assertTrue(table_marker in html, f"missing {table_id}")
            table = html.split(table_marker, 1)[1].split("</table>", 1)[0]
            table_header = table.split("</thead>", 1)[0]
            self.assertIn("验证链接", table_header)

        query_marker = "async function queryCodeCommon"
        self.assertTrue(query_marker in html, "missing queryCodeCommon")
        query_renderer = html.split(query_marker, 1)[1].split(
            "async function queryCode", 1
        )[0]
        self.assertTrue(
            'class="verification-link-cell"' in query_renderer,
            "top query row must include verification-link-cell",
        )

    def test_verification_link_renderer_assigns_safe_dom_properties(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        helper_marker = "function appendVerificationLinkAction"
        self.assertTrue(helper_marker in html, "missing verification link helper")
        helper_tail = html.split(helper_marker, 1)[1]
        self.assertTrue(
            "async function queryCodeCommon" in helper_tail,
            "missing queryCodeCommon after verification link helper",
        )
        helper = helper_marker + helper_tail.split(
            "async function queryCodeCommon", 1
        )[0]
        identifier = r"[A-Za-z_$][A-Za-z0-9_$]*"

        signature = re.search(
            rf"function\s+appendVerificationLinkAction\s*\(\s*"
            rf"({identifier})\s*,\s*({identifier})",
            helper,
        )
        self.assertTrue(signature is not None, "missing helper container parameter")
        container_name = signature.group(1)

        anchor_match = re.search(
            rf"\b(?:const|let)\s+({identifier})\s*=\s*"
            r"document\.createElement\(\s*['\"]a['\"]\s*\)",
            helper,
        )
        self.assertTrue(anchor_match is not None, "helper must create an anchor")
        anchor_name = anchor_match.group(1)

        href_match = re.search(
            rf"\b{re.escape(anchor_name)}\.href\s*=\s*"
            rf"({identifier})\s*;?",
            helper,
        )
        self.assertTrue(href_match is not None, "helper must assign anchor href")
        href_value = href_match.group(1)

        for property_name, value in (
            ("target", "_blank"),
            ("rel", "noopener noreferrer"),
            ("textContent", "打开验证链接"),
        ):
            self.assertRegex(
                helper,
                rf"\b{re.escape(anchor_name)}\.{property_name}\s*=\s*"
                rf"['\"]{re.escape(value)}['\"]\s*;?",
            )

        self.assertRegex(
            helper,
            rf"new\s+URL\(\s*{re.escape(href_value)}\s*\)",
        )
        self.assertRegex(
            helper,
            rf"\[\s*['\"]http:['\"]\s*,\s*['\"]https:['\"]\s*\]"
            rf"\s*\.includes\(\s*{identifier}\.protocol\s*\)",
        )
        append_match = re.search(
            rf"\b{re.escape(container_name)}\.(?:appendChild|append)\(\s*"
            rf"{re.escape(anchor_name)}\s*\)\s*;?",
            helper,
        )
        self.assertTrue(
            append_match is not None,
            "helper must append the anchor to its container",
        )

        self.assertTrue("innerHTML" not in helper, "helper must not use innerHTML")
        self.assertTrue("onclick" not in helper, "helper must not use onclick")
        dangerous_inner_html = re.search(
            r"\.innerHTML\s*=\s*`[^`]*(?:verification_url|verificationUrl)[^`]*`",
            html,
            re.DOTALL,
        )
        self.assertTrue(
            dangerous_inner_html is None,
            "verification URL must not enter an innerHTML template",
        )
        dangerous_inline_onclick = re.search(
            r'onclick\s*=\s*["\'][^"\']*(?:verification_url|verificationUrl)'
            r'[^"\']*["\']',
            html,
            re.DOTALL,
        )
        self.assertTrue(
            dangerous_inline_onclick is None,
            "verification URL must not enter inline onclick",
        )

    def test_row_shortcut_has_separate_link_result_container(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        history_renderer = html.split("async function loadHistory", 1)[1].split(
            "async function setUsed", 1
        )[0]
        quick_query = html.split("async function quickQueryCode", 1)[1].split(
            "async function loadHistory", 1
        )[0]

        self.assertTrue(
            'class="history-link-result"' in history_renderer,
            "history row must include a separate link result container",
        )
        link_call_pattern = (
            r"appendVerificationLinkAction\s*\([^;]*?,\s*"
            r"data\.verification_url\s*,?\s*\)"
        )
        link_calls = list(re.finditer(link_call_pattern, quick_query, re.DOTALL))
        self.assertEqual(len(link_calls), 1, "quick query must append one link action")
        remaining = quick_query
        for allowed_pattern in (
            link_call_pattern,
            r"!!\s*data\.verification_url",
            r"Boolean\(\s*data\.verification_url\s*\)",
            r"if\s*\(\s*data\.verification_url\s*\)",
        ):
            remaining = re.sub(allowed_pattern, "", remaining, flags=re.DOTALL)
        self.assertTrue(
            "data.verification_url" not in remaining,
            "quick query must only check or append data.verification_url",
        )

        identifier = r"[A-Za-z_$][A-Za-z0-9_$]*"
        code_alias = re.search(
            rf"\b(?:const|let)\s+({identifier})\s*=\s*"
            r"(?:!!\s*data\.code|Boolean\(\s*data\.code\s*\))",
            quick_query,
        )
        code_expression = re.escape(code_alias.group(1)) if code_alias else r"data\.code"
        guard = re.search(
            rf"\bif\s*\(\s*{code_expression}\s*\)", quick_query
        )
        self.assertTrue(guard is not None, "quick query needs a code-only branch")
        history_loads = list(re.finditer(r"loadQueryHistory\(1\)", quick_query))
        self.assertEqual(len(history_loads), 1, "quick query must load history once")
        self.assertLess(
            link_calls[0].end(),
            guard.start(),
            "quick query must append the link before checking for code",
        )
        self.assertLess(
            guard.end(),
            history_loads[0].start(),
            "quick query history load must stay inside the code path",
        )
        self.assertEqual(
            len(
                re.findall(
                    r"updateHistoryRowUsage\(\s*row\s*,\s*email\s*,\s*false\s*\)",
                    quick_query,
                )
            ),
            1,
            "link-only quick query must keep account usage false",
        )

    def test_top_query_handles_link_only_results(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        query_common = html.split("async function queryCodeCommon", 1)[1].split(
            "async function queryCode", 1
        )[0]
        identifier = r"[A-Za-z_$][A-Za-z0-9_$]*"
        code_alias = re.search(
            rf"\b(?:const|let)\s+({identifier})\s*=\s*"
            r"(?:!!\s*data\.code|Boolean\(\s*data\.code\s*\))",
            query_common,
        )
        link_alias = re.search(
            rf"\b(?:const|let)\s+({identifier})\s*=\s*"
            r"(?:!!\s*data\.verification_url|"
            r"Boolean\(\s*data\.verification_url\s*\))",
            query_common,
        )
        result_guard = re.search(
            r"\bif\s*\(\s*data\.code\s*\|\|\s*"
            r"data\.verification_url\s*\)",
            query_common,
        )
        if result_guard is None and code_alias and link_alias:
            result_guard = re.search(
                rf"\bif\s*\(\s*{re.escape(code_alias.group(1))}\s*\|\|\s*"
                rf"{re.escape(link_alias.group(1))}\s*\)",
                query_common,
            )
        self.assertTrue(result_guard is not None, "top query must accept code or link")
        self.assertIn("已找到验证链接", query_common)
        link_call_pattern = (
            r"appendVerificationLinkAction\s*\([^;]*?,\s*"
            r"data\.verification_url\s*,?\s*\)"
        )
        link_calls = list(re.finditer(link_call_pattern, query_common, re.DOTALL))
        self.assertEqual(len(link_calls), 1, "top query must append one link action")
        remaining = query_common
        for allowed_pattern in (
            link_call_pattern,
            r"!!\s*data\.verification_url",
            r"Boolean\(\s*data\.verification_url\s*\)",
            r"data\.code\s*\|\|\s*data\.verification_url",
        ):
            remaining = re.sub(allowed_pattern, "", remaining, flags=re.DOTALL)
        self.assertTrue(
            "data.verification_url" not in remaining,
            "top query must only check or append data.verification_url",
        )

        code_expression = (
            re.escape(code_alias.group(1)) if code_alias else r"data\.code"
        )
        guard = re.search(
            rf"\bif\s*\(\s*{code_expression}\s*\)", query_common
        )
        self.assertTrue(guard is not None, "top query needs a code-only history guard")
        history_loads = list(re.finditer(r"loadQueryHistory\(1\)", query_common))
        self.assertEqual(len(history_loads), 1, "top query must load history once")
        self.assertLess(
            result_guard.end(),
            link_calls[0].start(),
            "top query must append the link inside the shared result path",
        )
        self.assertLess(
            link_calls[0].end(),
            guard.start(),
            "top query must append the link before its code-only history guard",
        )
        self.assertLess(
            guard.end(),
            history_loads[0].start(),
            "top query history load must stay inside the code path",
        )

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
