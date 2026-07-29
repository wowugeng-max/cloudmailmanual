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
            self.assertTrue(
                "验证链接" in table_header,
                f"{table_id} must include a verification link header",
            )

    def test_verification_link_helper_is_declared(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertTrue(
            "function appendVerificationLinkAction" in html,
            "missing verification link helper",
        )

    def test_row_shortcut_has_separate_link_result_container(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        history_marker = "async function loadHistory"
        self.assertTrue(history_marker in html, "missing history row renderer")
        history_renderer = html.split(history_marker, 1)[1].split(
            "async function setUsed", 1
        )[0]

        self.assertTrue(
            'class="history-link-result"' in history_renderer,
            "history row must include a separate link result container",
        )

    def test_verification_link_runtime_contract(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        main_script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync(0, 'utf8');
const safeUrl = 'https://awstrack.me/L0/https:%2F%2FService.Example%2Fapi%2FVerify-Email%3Ftoken%3DAbC123XyZ/TrackCase';
const innerHTMLWrites = [];
const attributeWrites = [];
const handlerWrites = [];

const matchesSelector = (element, selector) => {
  if (selector.startsWith('.')) {
    const className = selector.slice(1);
    return String(element.className || '').split(/\s+/).includes(className);
  }
  return element.tagName.toLowerCase() === selector.toLowerCase();
};

const findDescendants = (element, selector) => {
  const matches = [];
  for (const child of element.children) {
    if (matchesSelector(child, selector)) matches.push(child);
    matches.push(...findDescendants(child, selector));
  }
  return matches;
};

const makeElement = (tagName = 'div') => {
  let innerHTML = '';
  let onclick = null;
  const attributes = {};
  const closestElements = {};
  const element = {
    tagName: String(tagName).toUpperCase(),
    nodeName: String(tagName).toUpperCase(),
    className: '',
    textContent: '',
    href: '',
    target: '',
    rel: '',
    title: '',
    value: '',
    disabled: false,
    dataset: {},
    style: {},
    children: [],
    parentNode: null,
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    append(...children) {
      children.forEach((child) => this.appendChild(child));
    },
    replaceChildren(...children) {
      this.children = [];
      children.forEach((child) => this.appendChild(child));
    },
    querySelector(selector) {
      return findDescendants(this, selector)[0] || null;
    },
    querySelectorAll(selector) {
      return findDescendants(this, selector);
    },
    closest(selector) {
      return closestElements[selector] || null;
    },
    setClosest(selector, target) {
      closestElements[selector] = target;
    },
    setAttribute(name, value) {
      const normalizedName = String(name);
      const normalizedValue = String(value);
      attributes[normalizedName] = normalizedValue;
      attributeWrites.push({ name: normalizedName, value: normalizedValue });
      if (/^on/i.test(normalizedName)) {
        handlerWrites.push({ element: this, name: normalizedName, value: normalizedValue });
      }
      if (normalizedName === 'class') this.className = normalizedValue;
      if (normalizedName === 'href') this.href = normalizedValue;
    },
    getAttribute(name) {
      return attributes[String(name)] || null;
    },
  };

  element.classList = {
    add(...names) {
      const values = new Set(String(element.className || '').split(/\s+/).filter(Boolean));
      names.forEach((name) => values.add(name));
      element.className = Array.from(values).join(' ');
    },
    remove(...names) {
      const blocked = new Set(names);
      element.className = String(element.className || '')
        .split(/\s+/)
        .filter((name) => name && !blocked.has(name))
        .join(' ');
    },
    toggle(name, force) {
      const values = new Set(String(element.className || '').split(/\s+/).filter(Boolean));
      const enabled = force === undefined ? !values.has(name) : !!force;
      if (enabled) values.add(name);
      else values.delete(name);
      element.className = Array.from(values).join(' ');
      return enabled;
    },
  };

  Object.defineProperty(element, 'innerHTML', {
    get() { return innerHTML; },
    set(value) {
      innerHTML = String(value);
      innerHTMLWrites.push({ element, value: innerHTML });
      element.children = [];
      if (innerHTML.includes('verification-link-cell')) {
        const cell = makeElement('td');
        cell.className = 'verification-link-cell';
        element.appendChild(cell);
      }
    },
  });
  Object.defineProperty(element, 'onclick', {
    get() { return onclick; },
    set(value) {
      onclick = value;
      handlerWrites.push({ element, name: 'onclick', value: String(value) });
    },
  });
  return element;
};

const document = {
  documentElement: { dataset: {} },
  body: makeElement('body'),
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  createElement(tagName) { return makeElement(tagName); },
  execCommand() { return true; },
};
const windowObject = { addEventListener() {} };
const context = vm.createContext({
  document,
  window: windowObject,
  console,
  URL,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  navigator: {},
});
vm.runInContext(source, context);

context.__onHistoryLoad = () => {};
context.__onUsageUpdate = () => {};
vm.runInContext(`
  bindCopyHandlers = () => {};
  loadHistory = () => {};
  loadQueryHistory = (...args) => __onHistoryLoad(...args);
  updateHistoryRowUsage = (...args) => __onUsageUpdate(...args);
  resolveHistoryProfileId = () => 'profile-1';
`, context);

const assertAnchor = (container, label) => {
  assert.strictEqual(container.children.length, 1, `${label} should contain one anchor`);
  const anchor = container.children[0];
  assert.strictEqual(anchor.tagName, 'A', `${label} should append an A node`);
  assert.strictEqual(anchor.href, safeUrl);
  assert.strictEqual(anchor.target, '_blank');
  assert.strictEqual(anchor.rel, 'noopener noreferrer');
  assert.strictEqual(anchor.textContent, '打开验证链接');
  assert.strictEqual(
    handlerWrites.filter((write) => write.element === anchor && /^on/i.test(write.name)).length,
    0,
    `${label} anchor must not receive inline handlers`,
  );
  for (const propertyName of Object.getOwnPropertyNames(anchor).filter((name) => /^on/i.test(name))) {
    assert.ok(
      anchor[propertyName] == null || anchor[propertyName] === '',
      `${label} anchor ${propertyName} must be empty`,
    );
  }
  return anchor;
};

const installFetch = (payload) => {
  context.fetch = async () => ({
    ok: true,
    json: async () => payload,
  });
};

const makeTopSurface = () => {
  const table = makeElement('table');
  const tbody = makeElement('tbody');
  table.appendChild(tbody);
  return {
    table,
    tbody,
    status: makeElement('div'),
    button: makeElement('button'),
  };
};

const runTopQuery = async (payload, label) => {
  const surface = makeTopSurface();
  let historyLoads = 0;
  context.__onHistoryLoad = () => { historyLoads += 1; };
  installFetch(payload);
  context.__topStatus = surface.status;
  context.__topButton = surface.button;
  context.__topTable = surface.table;
  await vm.runInContext(
    "queryCodeCommon('top@example.com', '', 'profile-1', " +
      "__topStatus, __topButton, __topTable, false)",
    context,
  );
  const linkCell = surface.tbody.querySelector('.verification-link-cell');
  assert.ok(linkCell, `${label} should create verification-link-cell`);
  assertAnchor(linkCell, label);
  return { surface, historyLoads };
};

const makeQuickSurface = () => {
  const row = makeElement('tr');
  const stack = makeElement('div');
  const codeResult = makeElement('div');
  const linkResult = makeElement('div');
  const button = makeElement('button');
  stack.className = 'history-code-stack';
  codeResult.className = 'history-code-result';
  linkResult.className = 'history-link-result';
  stack.appendChild(codeResult);
  stack.appendChild(linkResult);
  row.appendChild(stack);
  button.dataset.email = 'row@example.com';
  button.dataset.profileId = 'profile-1';
  button.setClosest('.history-code-stack', stack);
  button.setClosest('tr', row);
  return { row, stack, codeResult, linkResult, button };
};

const runQuickQuery = async (payload, expectedUsed, expectedHistoryLoads, label) => {
  const surface = makeQuickSurface();
  let historyLoads = 0;
  const usageUpdates = [];
  context.__onHistoryLoad = () => { historyLoads += 1; };
  context.__onUsageUpdate = (row, email, used) => {
    usageUpdates.push({ row, email, used });
  };
  installFetch(payload);
  context.__quickButton = surface.button;
  await vm.runInContext('quickQueryCode(__quickButton)', context);
  assertAnchor(surface.linkResult, label);
  assert.strictEqual(usageUpdates.length, 1, `${label} should update usage once`);
  assert.strictEqual(usageUpdates[0].row, surface.row);
  assert.strictEqual(usageUpdates[0].email, 'row@example.com');
  assert.strictEqual(usageUpdates[0].used, expectedUsed);
  assert.strictEqual(historyLoads, expectedHistoryLoads);
};

(async () => {
  const helperContainer = makeElement('div');
  context.__helperContainer = helperContainer;
  context.__safeUrl = safeUrl;
  const helperResult = vm.runInContext(
    'appendVerificationLinkAction(__helperContainer, __safeUrl)',
    context,
  );
  assert.strictEqual(helperResult, true);
  assertAnchor(helperContainer, 'helper');

  const unsafeContainer = makeElement('div');
  context.__unsafeContainer = unsafeContainer;
  const unsafeResult = vm.runInContext(
    "appendVerificationLinkAction(__unsafeContainer, 'javascript:alert(1)')",
    context,
  );
  assert.strictEqual(unsafeResult, false);
  assert.strictEqual(unsafeContainer.children.length, 0);

  const topLinkOnly = await runTopQuery({
    ok: true,
    code: '',
    verification_url: safeUrl,
    sender: 'sender@example.com',
    subject: 'Verify account',
    received_time: '2026-07-29 10:00:00',
  }, 'top link-only');
  assert.ok(topLinkOnly.surface.status.textContent.includes('已找到验证链接'));
  assert.strictEqual(topLinkOnly.historyLoads, 0);

  const topCodeAndLink = await runTopQuery({
    ok: true,
    code: '123456',
    verification_url: safeUrl,
    sender: 'sender@example.com',
    subject: 'Verify account',
    received_time: '2026-07-29 10:00:00',
  }, 'top code+link');
  assert.strictEqual(topCodeAndLink.historyLoads, 1);

  await runQuickQuery({
    ok: true,
    code: '',
    verification_url: safeUrl,
  }, false, 0, 'quick link-only');

  await runQuickQuery({
    ok: true,
    code: '654321',
    verification_url: safeUrl,
  }, true, 1, 'quick code+link');

  for (const write of innerHTMLWrites) {
    assert.ok(!write.value.includes(safeUrl), 'safe URL leaked into innerHTML');
  }
  for (const write of attributeWrites) {
    assert.ok(!write.value.includes(safeUrl), 'safe URL leaked through setAttribute');
  }
  for (const write of handlerWrites) {
    assert.ok(!write.value.includes(safeUrl), 'safe URL leaked into inline handler');
  }
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
