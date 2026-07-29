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
        self.assertIn(
            "updateHistoryRowUsage(row, email, true, data.mark_platform)", html
        )
        self.assertIn(
            "updateHistoryRowUsage(row, email, false, data.mark_platform)", html
        )
        self.assertIn('data-role="account-platform"', html)
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
const secretMarker = 'AbC123XyZ';
const maliciousFields = {
  code: '<img src=x onerror=globalThis.__codeXss=1>',
  sender: '<svg onload=globalThis.__senderXss=1>',
  subject: '<img src=x onerror=globalThis.__subjectXss=1>',
  received_time: '<details open ontoggle=globalThis.__timeXss=1>',
};
const innerHTMLWrites = [];
const attributeWrites = [];
const handlerWrites = [];
const hrefWrites = [];
const allElements = [];
const elementById = new Map();

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
  let href = '';
  const attributes = {};
  const closestElements = {};
  const querySelectorElements = {};
  const element = {
    tagName: String(tagName).toUpperCase(),
    nodeName: String(tagName).toUpperCase(),
    className: '',
    textContent: '',
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
      return querySelectorElements[selector] || findDescendants(this, selector)[0] || null;
    },
    setQuerySelector(selector, target) {
      querySelectorElements[selector] = target;
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
      if (normalizedName.startsWith('data-')) {
        const datasetName = normalizedName
          .slice(5)
          .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        this.dataset[datasetName] = normalizedValue;
      }
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
  Object.defineProperty(element, 'href', {
    get() { return href; },
    set(value) {
      href = String(value);
      hrefWrites.push({ element, value: href });
    },
  });
  Object.defineProperty(element, 'onclick', {
    get() { return onclick; },
    set(value) {
      onclick = value;
      handlerWrites.push({ element, name: 'onclick', value: String(value) });
    },
  });
  allElements.push(element);
  return element;
};

const document = {
  documentElement: { dataset: {} },
  body: makeElement('body'),
  getElementById(id) { return elementById.get(String(id)) || null; },
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

context.__realLoadQueryHistory = vm.runInContext('loadQueryHistory', context);
context.__onHistoryLoad = () => {};
vm.runInContext(`
  bindCopyHandlers = () => {};
  loadHistory = () => {};
  loadQueryHistory = (...args) => __onHistoryLoad(...args);
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

const assertNoAnchor = (container, label) => {
  assert.strictEqual(container.children.length, 0, `${label} should not contain a link`);
};

const installFetch = (payload, ok = true) => {
  context.fetch = async () => ({
    ok,
    json: async () => payload,
  });
};

const installFetchError = (message) => {
  context.fetch = async () => { throw new Error(message); };
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

const runTopQuery = async (surface, payload) => {
  if (payload instanceof Error) installFetchError(payload.message);
  else installFetch(payload);
  context.__topStatus = surface.status;
  context.__topButton = surface.button;
  context.__topTable = surface.table;
  await vm.runInContext(
    "queryCodeCommon('top@example.com', '', 'profile-1', " +
      "__topStatus, __topButton, __topTable, false)",
    context,
  );
};

const assertTopRow = (surface, expectedValues, label) => {
  assert.strictEqual(surface.tbody.children.length, 1, `${label} should render one row`);
  const row = surface.tbody.children[0];
  assert.strictEqual(row.children.length, 5, `${label} should preserve the five columns`);
  expectedValues.forEach((expected, index) => {
    const cell = row.children[index];
    assert.strictEqual(cell.tagName, 'TD');
    assert.strictEqual(cell.textContent, expected, `${label} column ${index} text mismatch`);
    assert.strictEqual(cell.dataset.copy, expected, `${label} column ${index} copy data mismatch`);
    assert.strictEqual(cell.children.length, 0, `${label} column ${index} must contain text only`);
  });
  assert.ok(
    String(row.children[4].className).split(/\s+/).includes('verification-link-cell'),
    `${label} should preserve the link column`,
  );
  return row;
};

const makeQuickSurface = () => {
  const row = makeElement('tr');
  const stack = makeElement('div');
  const codeResult = makeElement('div');
  const linkResult = makeElement('div');
  const button = makeElement('button');
  const statusCell = makeElement('td');
  const platformCell = makeElement('td');
  const actionCell = makeElement('td');
  const actionButton = makeElement('button');
  stack.className = 'history-code-stack';
  codeResult.className = 'history-code-result';
  linkResult.className = 'history-link-result';
  statusCell.textContent = '未使用';
  statusCell.setAttribute('data-copy', '未使用');
  platformCell.textContent = 'Existing Platform';
  platformCell.setAttribute('data-copy', 'Existing Platform');
  actionCell.className = 'history-action-col';
  actionCell.appendChild(actionButton);
  stack.appendChild(codeResult);
  stack.appendChild(linkResult);
  row.appendChild(stack);
  row.appendChild(statusCell);
  row.appendChild(platformCell);
  row.appendChild(actionCell);
  row.setQuerySelector('[data-role="account-status"]', statusCell);
  row.setQuerySelector('[data-role="account-platform"]', platformCell);
  row.setQuerySelector('.history-action-col button', actionButton);
  button.dataset.email = 'row@example.com';
  button.dataset.profileId = 'profile-1';
  button.setClosest('.history-code-stack', stack);
  button.setClosest('tr', row);
  return {
    row,
    stack,
    codeResult,
    linkResult,
    button,
    statusCell,
    platformCell,
    actionButton,
  };
};

const runQuickQuery = async (surface, payload) => {
  if (payload instanceof Error) installFetchError(payload.message);
  else installFetch(payload);
  context.__quickButton = surface.button;
  await vm.runInContext('quickQueryCode(__quickButton)', context);
};

const makeQueryHistorySurface = () => {
  const table = makeElement('table');
  const tbody = makeElement('tbody');
  table.appendChild(tbody);
  const elements = {
    queryHistoryPageSize: makeElement('input'),
    queryHistoryStatus: makeElement('div'),
    queryHistoryTable: table,
    queryHistoryEmailFilter: makeElement('input'),
    prevQueryHistoryBtn: makeElement('button'),
    nextQueryHistoryBtn: makeElement('button'),
  };
  elements.queryHistoryPageSize.value = '20';
  elements.queryHistoryEmailFilter.value = '';
  Object.entries(elements).forEach(([id, element]) => elementById.set(id, element));
  return { table, tbody, elements };
};

const runQueryHistory = async (surface, payload) => {
  installFetch(payload);
  context.__queryHistorySurface = surface;
  await vm.runInContext('__realLoadQueryHistory(1)', context);
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

  for (const [label, invalidUrl] of [
    ['empty', ''],
    ['leading whitespace', ` ${safeUrl}`],
    ['trailing whitespace', `${safeUrl}\n`],
    ['embedded whitespace', 'https://example.com/verify token'],
    ['unsafe scheme', 'javascript:alert(1)'],
    ['missing hostname', 'https://'],
  ]) {
    const invalidContainer = makeElement('div');
    context.__invalidContainer = invalidContainer;
    context.__invalidUrl = invalidUrl;
    const invalidResult = vm.runInContext(
      'appendVerificationLinkAction(__invalidContainer, __invalidUrl)',
      context,
    );
    assert.strictEqual(invalidResult, false, `${label} URL must be rejected`);
    assertNoAnchor(invalidContainer, label);
  }

  let historyLoads = 0;
  context.__onHistoryLoad = () => { historyLoads += 1; };
  const topSurface = makeTopSurface();
  await runTopQuery(topSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
    sender: 'sender@example.com',
    subject: 'Verify account',
    received_time: '2026-07-29 10:00:00',
  });
  let topRow = assertTopRow(
    topSurface,
    ['', 'sender@example.com', 'Verify account', '2026-07-29 10:00:00'],
    'top link-only',
  );
  assertAnchor(topRow.children[4], 'top link-only');
  assert.strictEqual(topSurface.table.style.display, 'table');
  assert.ok(topSurface.status.textContent.includes('已找到验证链接'));
  assert.strictEqual(historyLoads, 0);

  await runTopQuery(topSurface, {
    ok: true,
    code: '',
    verification_url: '',
    sender: '',
    subject: '',
    received_time: '',
  });
  assert.strictEqual(topSurface.tbody.children.length, 0, 'top empty must clear the old row');
  assert.strictEqual(topSurface.table.style.display, 'none');
  assert.ok(topSurface.status.textContent.includes('暂未查询到'));
  assert.ok(!topSurface.status.textContent.includes('已找到验证链接'));

  await runTopQuery(topSurface, {
    ok: true,
    code: '',
    verification_url: ` ${safeUrl}`,
  });
  assert.strictEqual(topSurface.tbody.children.length, 0, 'top invalid URL must not render a row');
  assert.strictEqual(topSurface.table.style.display, 'none');
  assert.ok(topSurface.status.textContent.includes('暂未查询到'));

  await runTopQuery(topSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
  });
  assertAnchor(topSurface.tbody.children[0].children[4], 'top before error');
  await runTopQuery(topSurface, new Error('top network failure'));
  assert.strictEqual(topSurface.tbody.children.length, 0, 'top error must clear the old row');
  assert.strictEqual(topSurface.table.style.display, 'none');
  assert.ok(topSurface.status.textContent.includes('top network failure'));

  const topCodeAndLink = makeTopSurface();
  await runTopQuery(topCodeAndLink, {
    ok: true,
    code: '123456',
    verification_url: safeUrl,
    sender: 'sender@example.com',
    subject: 'Verify account',
    received_time: '2026-07-29 10:00:00',
  });
  topRow = assertTopRow(
    topCodeAndLink,
    ['123456', 'sender@example.com', 'Verify account', '2026-07-29 10:00:00'],
    'top code+link',
  );
  assertAnchor(topRow.children[4], 'top code+link');
  assert.strictEqual(historyLoads, 1);

  const topCodeInvalidLink = makeTopSurface();
  await runTopQuery(topCodeInvalidLink, {
    ok: true,
    code: '246810',
    verification_url: `${safeUrl} `,
    sender: 'sender@example.com',
    subject: 'Code only',
    received_time: '2026-07-29 11:00:00',
  });
  topRow = assertTopRow(
    topCodeInvalidLink,
    ['246810', 'sender@example.com', 'Code only', '2026-07-29 11:00:00'],
    'top code + invalid link',
  );
  assertNoAnchor(topRow.children[4], 'top code + invalid link');
  assert.ok(topCodeInvalidLink.status.textContent.includes('已查询到验证码'));

  const maliciousTop = makeTopSurface();
  await runTopQuery(maliciousTop, {
    ok: true,
    verification_url: safeUrl,
    ...maliciousFields,
  });
  topRow = assertTopRow(
    maliciousTop,
    [maliciousFields.code, maliciousFields.sender, maliciousFields.subject, maliciousFields.received_time],
    'top malicious fields',
  );
  assertAnchor(topRow.children[4], 'top malicious fields');

  let quickHistoryLoads = 0;
  context.__onHistoryLoad = () => { quickHistoryLoads += 1; };
  const quickSurface = makeQuickSurface();
  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
    mark_platform: 'Acme, Inc.',
  });
  assertAnchor(quickSurface.linkResult, 'quick link-only');
  assert.strictEqual(quickSurface.codeResult.textContent, '仅发现验证链接');
  assert.strictEqual(quickSurface.statusCell.textContent, '未使用');
  assert.strictEqual(quickSurface.actionButton.dataset.used, '0');
  assert.strictEqual(
    quickSurface.platformCell.textContent,
    'Existing Platform, Acme, Inc.',
  );
  assert.strictEqual(
    quickSurface.platformCell.dataset.copy,
    'Existing Platform, Acme, Inc.',
  );

  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
    mark_platform: 'Acme, Inc.',
  });
  assertAnchor(quickSurface.linkResult, 'quick duplicate platform');
  assert.strictEqual(
    quickSurface.platformCell.textContent,
    'Existing Platform, Acme, Inc.',
  );

  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: '',
  });
  assertNoAnchor(quickSurface.linkResult, 'quick empty');
  assert.strictEqual(quickSurface.codeResult.textContent, '暂未查到');

  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: ` ${safeUrl}`,
  });
  assertNoAnchor(quickSurface.linkResult, 'quick invalid URL');
  assert.strictEqual(quickSurface.codeResult.textContent, '暂未查到');

  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
  });
  assertAnchor(quickSurface.linkResult, 'quick before error');
  await runQuickQuery(quickSurface, new Error('quick network failure'));
  assertNoAnchor(quickSurface.linkResult, 'quick error');
  assert.strictEqual(quickSurface.codeResult.textContent, 'quick network failure');

  const quickCodeAndLink = makeQuickSurface();
  await runQuickQuery(quickCodeAndLink, {
    ok: true,
    code: '654321',
    verification_url: safeUrl,
    mark_platform: 'Code Platform',
  });
  assertAnchor(quickCodeAndLink.linkResult, 'quick code+link');
  assert.strictEqual(quickCodeAndLink.codeResult.textContent, '654321');
  assert.strictEqual(quickCodeAndLink.statusCell.textContent, '正在使用');
  assert.strictEqual(quickCodeAndLink.actionButton.dataset.used, '1');
  assert.strictEqual(
    quickCodeAndLink.platformCell.textContent,
    'Existing Platform, Code Platform',
  );
  assert.strictEqual(quickHistoryLoads, 1);

  const queryHistory = makeQueryHistorySurface();
  await runQueryHistory(queryHistory, {
    ok: true,
    page: 1,
    total_pages: 1,
    total: 1,
    items: [{
      id: maliciousFields.code,
      email: maliciousFields.sender,
      code: maliciousFields.code,
      sender: maliciousFields.sender,
      subject: maliciousFields.subject,
      received_time: maliciousFields.received_time,
      queried_at: maliciousFields.subject,
    }],
  });
  assert.strictEqual(queryHistory.tbody.children.length, 1);
  const historyRow = queryHistory.tbody.children[0];
  assert.strictEqual(historyRow.children.length, 8, 'query history must preserve column order');
  const checkbox = historyRow.children[0].children[0];
  assert.strictEqual(checkbox.tagName, 'INPUT');
  assert.strictEqual(checkbox.type, 'checkbox');
  assert.strictEqual(checkbox.className, 'query-history-check');
  assert.strictEqual(checkbox.value, maliciousFields.code);
  [
    maliciousFields.code,
    maliciousFields.sender,
    maliciousFields.code,
    maliciousFields.sender,
    maliciousFields.subject,
    maliciousFields.received_time,
    maliciousFields.subject,
  ].forEach((expected, index) => {
    const cell = historyRow.children[index + 1];
    assert.strictEqual(cell.textContent, expected, `query history column ${index} text mismatch`);
    assert.strictEqual(cell.dataset.copy, expected, `query history column ${index} copy data mismatch`);
    assert.strictEqual(cell.children.length, 0, `query history column ${index} must contain text only`);
  });

  for (const write of innerHTMLWrites) {
    assert.ok(!write.value.includes(safeUrl), 'safe URL leaked into innerHTML');
    assert.ok(
      !String(write.value).toLowerCase().includes(secretMarker.toLowerCase()),
      'decoded verification token leaked into innerHTML',
    );
    for (const payload of Object.values(maliciousFields)) {
      assert.ok(!write.value.includes(payload), 'XSS payload leaked into innerHTML');
    }
  }
  for (const write of attributeWrites) {
    assert.ok(!write.value.includes(safeUrl), 'safe URL leaked through setAttribute');
    assert.ok(
      !String(write.value).toLowerCase().includes(secretMarker.toLowerCase()),
      'decoded verification token leaked through setAttribute',
    );
    for (const payload of Object.values(maliciousFields)) {
      assert.ok(!write.value.includes(payload), 'XSS payload leaked through setAttribute');
    }
  }
  for (const write of handlerWrites) {
    assert.ok(!write.value.includes(safeUrl), 'safe URL leaked into inline handler');
    assert.ok(
      !String(write.value).toLowerCase().includes(secretMarker.toLowerCase()),
      'decoded verification token leaked into inline handler',
    );
    for (const payload of Object.values(maliciousFields)) {
      assert.ok(!write.value.includes(payload), 'XSS payload leaked into handler');
    }
  }
  assert.ok(hrefWrites.length > 0, 'safe links should be assigned through href properties');
  for (const write of hrefWrites) {
    assert.strictEqual(write.element.tagName, 'A', 'only anchors may receive href values');
    assert.strictEqual(write.value, safeUrl, 'href must preserve the original safe URL');
  }
  for (const element of allElements) {
    assert.ok(!String(element.textContent).includes(safeUrl), 'verification URL became visible text');
    assert.ok(
      !String(element.textContent).toLowerCase().includes(secretMarker.toLowerCase()),
      'verification token became visible text',
    );
    assert.ok(!['IMG', 'SVG', 'DETAILS'].includes(element.tagName), 'XSS payload created an element');
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
