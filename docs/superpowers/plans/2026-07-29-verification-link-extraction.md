# Verification Link Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract verification action links from HTML email messages, expose the original safe link through the query API, and render a user-clicked `打开验证链接` action in both query surfaces without persisting token-bearing URLs.

**Architecture:** Add a small standard-library HTML anchor parser under `cloudmailmanual_app/services/verification_links.py`. `CloudMailClient.query_verification_detail()` will combine that parser with the existing code extraction and return a `verification_url` field; the route will persist and mark usage only when a code exists. The existing top query and row shortcut will use one DOM-building helper that assigns `href`, `target`, and `rel` as properties, so the URL never enters an HTML template string.

**Tech Stack:** Python 3, `html.parser.HTMLParser`, `urllib.parse.urlsplit`, Flask test client, `unittest`, Node.js `vm` harness for the inline browser script, and the existing local Flask UI.

---

### Task 1: Define the HTML link extractor contract with failing tests

**Files:**
- Create: `tests/test_verification_links.py`
- Reference: `cloudmailmanual_app/services/verification_links.py` (the module under test)

- [ ] **Step 1: Write the failing parser tests**

Create a focused `unittest.TestCase` with these exact cases:

```python
from unittest import TestCase

from cloudmailmanual_app.services.verification_links import extract_verification_link


class VerificationLinkExtractionTest(TestCase):
    def test_extracts_action_link_and_preserves_original_tracking_href(self):
        href = (
            "https://awstrack.me/L0/https:%2F%2Fservice.example%2Fverify-email"
            "%3Ftoken%3Dredacted/abc"
        )
        html = f'<a href="{href}">Verify Email Address</a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_prefers_verify_action_over_footer_links(self):
        html = (
            '<a href="https://example.test/">Company logo</a>'
            '<a href="https://example.test/preferences">Manage preferences</a>'
            '<a href="https://example.test/confirm?token=abc">Confirm account</a>'
        )

        self.assertEqual(
            extract_verification_link(html),
            "https://example.test/confirm?token=abc",
        )

    def test_rejects_unsafe_relative_and_unrelated_links(self):
        html = (
            '<a href="javascript:alert(1)">Verify</a>'
            '<a href="data:text/html,verify">Verify</a>'
            '<a href="mailto:help@example.test">Confirm</a>'
            '<a href="/verify-email?token=abc">Verify</a>'
            '<a href="https://example.test/privacy">Privacy policy</a>'
        )

        self.assertIsNone(extract_verification_link(html))

    def test_tolerates_malformed_html_and_missing_href(self):
        html = (
            '<a>Missing href</a><a href="https://example.test/activate?token=abc">'
            '<strong>Activate</strong>'
        )

        self.assertEqual(
            extract_verification_link(html),
            "https://example.test/activate?token=abc",
        )

    def test_returns_none_when_no_action_evidence_exists(self):
        html = '<a href="https://example.test/news">Read our news</a>'

        self.assertIsNone(extract_verification_link(html))
```

The tests deliberately include the AWS-style percent-encoded destination and assert that the returned value is the exact tracking `href`, not a decoded or rewritten URL.

- [ ] **Step 2: Run the focused tests and verify they fail for the intended reason**

Run:

```bash
python -m pytest tests/test_verification_links.py -q
```

Expected: collection fails with `ModuleNotFoundError` because `cloudmailmanual_app/services/verification_links.py` does not yet exist. Do not change production code before recording this failing result.

- [ ] **Step 3: Commit the failing-test contract**

```bash
git add tests/test_verification_links.py
git commit -m "test: define verification link extraction contract"
```

### Task 2: Implement and harden the standard-library link parser

**Files:**
- Create: `cloudmailmanual_app/services/verification_links.py`
- Test: `tests/test_verification_links.py`

- [ ] **Step 1: Implement the minimal parser and scoring rules**

Add this complete module. It collects anchor text before any HTML stripping, accepts only absolute web URLs, requires verification evidence, and keeps document order as the tie breaker:

```python
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urlsplit


_ACTION_TERMS = ("verify", "confirm", "activate", "complete")
_SUPPORT_TERMS = ("token", "verification", "email")
_NEGATIVE_TERMS = ("unsubscribe", "privacy", "preferences", "terms")


@dataclass
class _Anchor:
    href: str
    text: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[_Anchor] = []
        self._href: Optional[str] = None
        self._text: List[str] = []

    def _finish_anchor(self) -> None:
        if self._href is not None:
            self.anchors.append(_Anchor(self._href, "".join(self._text)))
        self._href = None
        self._text = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        self._finish_anchor()
        attributes = dict(attrs)
        self._href = str(attributes.get("href") or "")

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        self._finish_anchor()
        attributes = dict(attrs)
        href = str(attributes.get("href") or "")
        self.anchors.append(_Anchor(href, ""))

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self._finish_anchor()

    def close(self) -> None:
        super().close()
        self._finish_anchor()


def _is_absolute_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _score(anchor: _Anchor) -> int:
    text = anchor.text.strip().casefold()
    href = anchor.href.casefold()
    combined = f"{text} {href}"
    action_text = sum(1 for term in _ACTION_TERMS if term in text)
    action_url = sum(1 for term in _ACTION_TERMS if term in href)
    support = sum(1 for term in _SUPPORT_TERMS if term in combined)
    negative = sum(1 for term in _NEGATIVE_TERMS if term in text)
    score = action_text * 10 + action_url * 5 + support * 2 - negative * 4
    return score if action_text or action_url or support else 0


def extract_verification_link(raw_html: str) -> Optional[str]:
    if not raw_html:
        return None

    parser = _AnchorParser()
    try:
        parser.feed(str(raw_html))
        parser.close()
    except Exception:
        return None

    candidates = []
    for index, anchor in enumerate(parser.anchors):
        href = anchor.href.strip()
        if not href or not _is_absolute_http_url(href):
            continue
        score = _score(_Anchor(href, anchor.text))
        if score > 0:
            candidates.append((score, -index, href))

    if not candidates:
        return None
    return max(candidates)[2]
```

The parser must not call `requests`, resolve redirects, decode the AWS tracking path, or log `href` values. `HTMLParser.close()` must flush an unterminated final anchor so malformed but readable messages still work.

- [ ] **Step 2: Run the parser tests and the existing extraction tests**

Run:

```bash
python -m pytest tests/test_verification_links.py tests/test_verification_code_extraction.py tests/test_verification_rules.py -q
```

Expected: all parser and pre-existing code-format tests pass. A failure in an existing code-format test means the parser integration or imports changed unrelated behavior and must be corrected before continuing.

- [ ] **Step 3: Commit the parser**

```bash
git add cloudmailmanual_app/services/verification_links.py tests/test_verification_links.py
git commit -m "feat: extract verification links from email html"
```

### Task 3: Extend client detail data for link-only and code-plus-link messages

**Files:**
- Modify: `cloud_mail_client.py:1-25,250-325`
- Modify: `tests/test_verification_rules.py:576-610`

- [ ] **Step 1: Add failing client-detail tests**

Add these tests to `ConfigurableExtractionTest` (or a neighboring client query test class) so they use the existing temporary config and `CloudMailClient.__new__` pattern:

```python
    def test_query_detail_returns_link_only_without_code(self):
        href = "https://awstrack.me/L0/https:%2F%2Fservice.test%2Fverify?token=redacted"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": f'<a href="{href}">Verify Email Address</a>',
                "sendEmail": "sender@example.test",
                "subject": "Please verify",
                "createTime": "2026-07-29 10:00:00",
            }
        ]

        self.assertEqual(
            client.query_verification_detail("a@example.com"),
            {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Please verify",
                "received_time": "2026-07-29 10:00:00",
            },
        )

    def test_query_detail_returns_code_and_link_from_same_message(self):
        href = "https://example.test/confirm?token=redacted"
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {
                "content": f'<p>Code: 123456</p><a href="{href}">Confirm</a>',
                "text": "Code: 123456",
            }
        ]

        detail = client.query_verification_detail("a@example.com")

        self.assertEqual(detail["code"], "123456")
        self.assertEqual(detail["verification_url"], href)

    def test_query_verification_code_remains_code_only_for_link_message(self):
        client = CloudMailClient.__new__(CloudMailClient)
        client._email_list = lambda **_: [
            {"content": '<a href="https://example.test/verify?token=x">Verify</a>'}
        ]

        self.assertIsNone(client.query_verification_code("a@example.com"))
```

- [ ] **Step 2: Run the new tests to verify they fail before integration**

Run:

```bash
python -m pytest tests/test_verification_rules.py::ConfigurableExtractionTest::test_query_detail_returns_link_only_without_code tests/test_verification_rules.py::ConfigurableExtractionTest::test_query_detail_returns_code_and_link_from_same_message tests/test_verification_rules.py::ConfigurableExtractionTest::test_query_verification_code_remains_code_only_for_link_message -q
```

Expected: the link-only test fails because `query_verification_detail()` currently returns `None`; the code-plus-link test either lacks `verification_url` or fails with a missing key. The code-only compatibility test must remain passing or be adjusted only to the explicit `None` contract above.

- [ ] **Step 3: Integrate the parser without changing code precedence**

Import the service function under a private alias and, inside the existing row loop, compute the link from `content` independently of code extraction:

```python
from cloudmailmanual_app.services.verification_links import (
    extract_verification_link,
)


# inside query_verification_detail(), after subject/text/html are read
try:
    verification_url = extract_verification_link(html) or ""
except Exception:
    verification_url = ""

# keep all existing subject/text/html code extraction in its current order
if code or verification_url:
    return {
        "code": code or "",
        "verification_url": verification_url,
        "sender": str(row.get("sendEmail") or row.get("sendName") or ""),
        "subject": subject,
        "received_time": str(row.get("createTime") or ""),
    }
```

Update `query_verification_code()` so it returns only the code and returns `None` when a detail contains only a link:

```python
def query_verification_code(self, email: str) -> Optional[str]:
    detail = self.query_verification_detail(email)
    if not detail or not detail.get("code"):
        return None
    return str(detail["code"])
```

Do not move the existing extraction order or let the URL become the `code` field.

- [ ] **Step 4: Run the client tests and confirm the full existing rule suite**

Run:

```bash
python -m pytest tests/test_verification_rules.py tests/test_verification_links.py -q
```

Expected: all tests pass, including link-only, code-plus-link, hot-reloaded code rules, timeout handling, and the original numeric-code tests.

- [ ] **Step 5: Commit the client integration**

```bash
git add cloud_mail_client.py tests/test_verification_rules.py
git commit -m "feat: include verification links in mail query details"
```

### Task 4: Define API persistence and account-state semantics with failing tests

**Files:**
- Modify: `tests/test_verification_rules_api.py:1-40,218-280`
- Reference: `cloudmailmanual_app/routes.py:276-329`

- [ ] **Step 1: Add route tests for empty, link-only, and code-plus-link results**

Use the existing `VerificationRulesApiTest.setUp()` and `login()` helpers. Add these tests; patch the client class so the route does not need a real mail profile:

```python
    def test_query_code_includes_empty_verification_url_when_no_message(self):
        self.login()
        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = None
            response = self.client.post(
                "/api/query-code", json={"email": "a@example.com"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["verification_url"], "")
        mark_used.assert_called_once_with("a@example.com", used=False, platform="")

    def test_link_only_query_returns_url_without_history_or_used_side_effect(self):
        href = "https://awstrack.me/L0/https:%2F%2Fservice.test%2Fverify?token=redacted"
        self.login()
        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": "",
                "verification_url": href,
                "sender": "sender@example.test",
                "subject": "Verify",
                "received_time": "2026-07-29 10:00:00",
            }
            response = self.client.post(
                "/api/query-code", json={"email": "a@example.com"}
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["verification_url"], href)
        self.assertFalse(data["saved"])
        self.assertFalse(data["auto_marked_used"])
        save_query.assert_not_called()
        mark_used.assert_called_once_with("a@example.com", used=False, platform="")

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
        self.assertEqual(data["code"], "123456")
        self.assertEqual(data["verification_url"], href)
        self.assertTrue(data["saved"])
        save_query.assert_called_once_with(
            "a@example.com",
            {
                "code": "123456",
                "sender": "sender@example.test",
                "subject": "Confirm",
                "received_time": "2026-07-29 10:00:00",
            },
        )
        mark_used.assert_called_once_with(
            "a@example.com", used=True, platform="Test"
        )
        self.assertNotIn("verification_url", save_query.call_args.args[1])
```

- [ ] **Step 2: Run the route tests and verify the new assertions fail**

Run:

```bash
python -m pytest tests/test_verification_rules_api.py -q
```

Expected: the new tests fail because the route currently omits `verification_url`, saves every non-empty detail, and marks a link-only detail as used.

### Task 5: Implement API response and persistence behavior

**Files:**
- Modify: `cloudmailmanual_app/routes.py:287-327`
- Test: `tests/test_verification_rules_api.py`

- [ ] **Step 1: Normalize the new field in every successful response**

Extend both route dictionaries with:

```python
"verification_url": "",
```

and normalize a non-empty detail with:

```python
normalized_detail = {
    "code": str(detail.get("code", "")),
    "verification_url": str(detail.get("verification_url", "")),
    "sender": str(detail.get("sender", "")),
    "subject": str(detail.get("subject", "")),
    "received_time": str(detail.get("received_time", "")),
}
```

- [ ] **Step 2: Separate code persistence from link discovery**

Replace the unconditional save/mark block with this behavior:

```python
if not normalized_detail["code"]:
    # A link is an action the user has not taken yet; it is not a used account
    # and its token must not enter verification query history.
    mark_account_used(email, used=False, platform="")
    return jsonify({
        "ok": True,
        "email": email,
        "saved": False,
        "auto_marked_used": False,
        "mark_platform": "",
        **normalized_detail,
    })

history_subject = " ".join(
    mask_http_urls(normalized_detail["subject"]).split()
)
save_verification_query(
    email,
    {
        "code": normalized_detail["code"],
        "sender": normalized_detail["sender"],
        "subject": history_subject,
        "received_time": normalized_detail["received_time"],
    },
)
auto_platform = platform or normalized_detail["sender"] or "验证码查询"
mark_account_used(email, used=True, platform=auto_platform)
return jsonify({
    "ok": True,
    "email": email,
    "saved": True,
    "auto_marked_used": True,
    "mark_platform": auto_platform,
    **normalized_detail,
})
```

This keeps the existing code behavior, returns a link alongside a code, and
guarantees that neither `verification_url` nor a literal HTTP(S) URL embedded
in the persisted subject reaches `save_verification_query()`. The API response
continues to expose the original subject.

- [ ] **Step 3: Run focused and regression API tests**

Run:

```bash
python -m pytest tests/test_verification_rules_api.py tests/test_app_structure.py -q
```

Expected: all API tests pass, including authentication, rule-test side-effect tests, invalid-payload handling, empty query compatibility, link-only no-save behavior, and code-plus-link persistence.

- [ ] **Step 4: Commit the API contract**

```bash
git add cloudmailmanual_app/routes.py tests/test_verification_rules_api.py
git commit -m "feat: expose verification links without persisting tokens"
```

### Task 6: Specify safe link rendering in both query surfaces with failing UI tests

**Files:**
- Modify: `tests/test_row_verification_ui.py:9-207`
- Reference: `templates/index.html:231-241,348-370,944-1000,1273-1316,1350-1395`

- [ ] **Step 1: Add static UI contract tests**

Add assertions for both result tables and the shared DOM helper:

```python
    def test_top_query_tables_have_verification_link_columns(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        for table_id in ("queryResultTable", "queryOnlyResultTable"):
            table = html.split(f'<table id="{table_id}"', 1)[1].split("</table>", 1)[0]
            self.assertIn("验证链接", table)
            self.assertIn("verification-link-cell", table)

    def test_verification_link_renderer_assigns_safe_dom_properties(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        helper = html.split("function appendVerificationLinkAction", 1)[1].split(
            "async function queryCodeCommon", 1
        )[0]

        for expected in (
            "createElement('a')",
            "link.href = verificationUrl",
            "link.target = '_blank'",
            "link.rel = 'noopener noreferrer'",
            "link.textContent = '打开验证链接'",
        ):
            self.assertIn(expected, helper)
        self.assertNotIn("verificationUrl}", helper)

    def test_row_shortcut_has_separate_link_result_container(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('class="history-link-result"', html)
        quick_query = html.split("async function quickQueryCode", 1)[1].split(
            "async function loadHistory", 1
        )[0]
        self.assertIn("appendVerificationLinkAction", quick_query)
        self.assertIn("data.verification_url", quick_query)
```

- [ ] **Step 2: Run the UI tests and verify they fail**

Run:

```bash
python -m pytest tests/test_row_verification_ui.py -q
```

Expected: the new assertions fail because the result tables, helper, and row link container do not yet exist.

### Task 7: Implement link rendering without raw URL interpolation

**Files:**
- Modify: `templates/index.html:64-114,231-241,360-370,944-1000,1273-1316,1376-1381`
- Test: `tests/test_row_verification_ui.py`

- [ ] **Step 1: Add stable styles and result columns**

Add an anchor-button style and a bounded row link result below the existing query result:

```css
.verification-link-btn {
  display:inline-block;
  padding:7px 10px;
  border-radius:9px;
  color:white;
  background:var(--secondary-bg);
  text-decoration:none;
  font-weight:600;
  white-space:nowrap;
}
.verification-link-btn:hover { filter:brightness(1.08); }
.history-link-result { min-height:18px; max-width:116px; }
```

Add `<th>验证链接</th>` to both top query tables and a static empty cell with class `verification-link-cell` in the row renderer. Add this to each row shortcut stack immediately below the existing code result:

```html
<div class="history-code-result"></div>
<div class="history-link-result"></div>
```

- [ ] **Step 2: Add one safe DOM helper**

Place this helper immediately before `queryCodeCommon()`:

```javascript
function appendVerificationLinkAction(container, rawUrl) {
  if (!container) return false;
  const verificationUrl = String(rawUrl || '').trim();
  if (!verificationUrl) return false;

  let parsed;
  try {
    parsed = new URL(verificationUrl);
  } catch (_) {
    return false;
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) {
    return false;
  }

  const link = document.createElement('a');
  link.className = 'verification-link-btn';
  link.textContent = '打开验证链接';
  link.href = verificationUrl;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.setAttribute('aria-label', '打开验证链接');
  container.appendChild(link);
  return true;
}
```

The URL is assigned only through `link.href`; it must not appear inside a template literal, `innerHTML`, an inline `onclick`, or a visible text node. The helper must return `false` for an empty or non-HTTP(S) value.

- [ ] **Step 3: Render top-query link actions for link-only and code-plus-link responses**

Update `queryCodeCommon()` to treat either field as a discovered result:

```javascript
const hasCode = !!data.code;
const hasVerificationLink = !!data.verification_url;
if (hasCode || hasVerificationLink) {
  status.className = 'status ok';
  status.textContent = hasCode
    ? `邮箱 ${email} 已查询到验证码`
    : `邮箱 ${email} 已找到验证链接`;
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td data-copy="${data.code || ''}">${data.code || ''}</td>
    <td data-copy="${data.sender || ''}">${data.sender || ''}</td>
    <td data-copy="${data.subject || ''}">${data.subject || ''}</td>
    <td data-copy="${data.received_time || ''}">${data.received_time || ''}</td>
    <td class="verification-link-cell"></td>
  `;
  appendVerificationLinkAction(
    tr.querySelector('.verification-link-cell'),
    data.verification_url,
  );
  tbody.appendChild(tr);
  table.style.display = 'table';
  bindCopyHandlers();
  if (hasCode) loadQueryHistory(1);
  if (refreshAccountHistory) loadHistory(historyPage);
} else {
  status.className = 'status';
  status.textContent = `邮箱 ${email} 暂未查询到验证码或验证链接`;
  if (refreshAccountHistory) loadHistory(historyPage);
}
```

Use the same branch for `queryResultTable` and `queryOnlyResultTable` because both call `queryCodeCommon()`.

- [ ] **Step 4: Render row shortcut results and preserve usage semantics**

In `quickQueryCode()`, clear both result containers before each request and append the link after a successful response:

```javascript
const linkResult = stack?.querySelector('.history-link-result');
if (!email || !result || !linkResult) return;

result.replaceChildren();
linkResult.replaceChildren();
button.disabled = true;
result.className = 'history-code-result';
result.textContent = '查询中...';
result.title = '';
result.onclick = null;

const res = await fetch('/api/query-code', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, platform: '', profile_id: profileId })
});
const data = await res.json();
if (!res.ok || !data.ok) {
  throw new Error(data.error || '查询失败');
}

const hasCode = !!data.code;
const hasVerificationLink = !!data.verification_url;
if (hasCode) {
  result.className = 'history-code-result ok';
  result.textContent = data.code;
  result.title = '点击复制验证码';
  result.onclick = () => copyText(data.code);
  updateHistoryRowUsage(row, email, true);
  loadQueryHistory(1);
} else {
  result.className = 'history-code-result';
  result.textContent = hasVerificationLink ? '仅发现验证链接' : '暂未查到';
  updateHistoryRowUsage(row, email, false);
}
if (hasVerificationLink) {
  appendVerificationLinkAction(linkResult, data.verification_url);
}
```

This keeps a link-only row unmarked and does not refresh query history for a link-only result. Keep the existing error class and reset behavior for failed requests.

- [ ] **Step 5: Run static UI tests and JavaScript syntax validation**

Run:

```bash
python -m pytest tests/test_row_verification_ui.py -q
node --check <(sed -n '/<script>/,/<\/script>/p' templates/index.html | sed '1d;$d')
```

Expected: the UI test file passes and Node reports no syntax errors. If the shell does not support process substitution in the active environment, extract the script to a temporary file without committing it and run `node --check` on that file.

- [ ] **Step 6: Commit the UI implementation**

```bash
git add templates/index.html tests/test_row_verification_ui.py
git commit -m "feat: show verification link actions in query views"
```

### Task 8: Add executable frontend behavior tests for link safety and both render paths

**Files:**
- Modify: `tests/test_row_verification_ui.py`
- Reference: `templates/index.html`

- [ ] **Step 1: Extend the existing Node `vm` harness with DOM nodes for query results**

Use the current inline-script extraction approach, adding fake `document.createElement`, `querySelector`, `appendChild`, `replaceChildren`, and `setAttribute` behavior sufficient to exercise `appendVerificationLinkAction()` and `quickQueryCode()`. The test input must include a token-bearing URL:

```javascript
const href = 'https://awstrack.me/L0/https:%2F%2Fservice.test%2Fverify?token=redacted';
const container = makeElement('verification-link-cell');
const created = [];
document.createElement = (tagName) => {
  const node = makeElement();
  node.tagName = tagName.toUpperCase();
  node.attributes = {};
  node.setAttribute = (name, value) => { node.attributes[name] = String(value); };
  created.push(node);
  return node;
};

assert.strictEqual(
  vm.runInContext('appendVerificationLinkAction(container, href)', context),
  true,
);
assert.strictEqual(created[0].href, href);
assert.strictEqual(created[0].target, '_blank');
assert.strictEqual(created[0].rel, 'noopener noreferrer');
assert.strictEqual(created[0].textContent, '打开验证链接');
assert.strictEqual(
  vm.runInContext("appendVerificationLinkAction(container, 'javascript:alert(1)')", context),
  false,
);
```

Add a source-level assertion that the token-bearing URL is not passed to `innerHTML` or inserted into a visible label. Keep the URL only in the `href` property assertion.

- [ ] **Step 2: Exercise link-only and code-plus-link branches**

Stub `fetch` twice and assert that `queryCodeCommon()` creates a result row in both cases, while `loadQueryHistory()` is called only for the code-plus-link case. Assert that `quickQueryCode()` appends a link node below the code result and calls `updateHistoryRowUsage(row, email, false)` for link-only data.

Run:

```bash
python -m pytest tests/test_row_verification_ui.py -q
```

Expected: the Node harness exits with code `0`, and the Python test reports `OK` for all static and executable UI assertions.

- [ ] **Step 3: Commit the executable UI coverage**

```bash
git add tests/test_row_verification_ui.py
git commit -m "test: verify safe rendering of verification links"
```

### Task 9: Run the complete regression suite and perform browser QA

**Files:**
- No production changes expected; inspect all files changed by Tasks 1-8.
- Test commands may create only temporary files outside the repository.

- [ ] **Step 1: Run the full Python test suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass, including the existing account search, deletion, multi-profile, Mac script, theme, and configurable-code-rule coverage. Record the exact passed-test count in the final report.

- [ ] **Step 2: Check the working tree and scan for accidental token persistence**

Run:

```bash
git diff --check
git status --short
rg -n "verification_url|awstrack|token=|innerHTML.*verification" cloud_mail_client.py cloudmailmanual_app templates tests
```

Expected: `git diff --check` is clean; only intended files are modified; no real test credential, live token, or remote request code is present. The only `verification_url` database-related assertion must confirm it is excluded from `save_verification_query()` input.

- [ ] **Step 3: Start the local app on an unused port**

Use the existing macOS launcher or the project’s Flask entry point. If port `8080` is occupied, select another local port and set the corresponding environment/config value before starting. Confirm the process is reachable at the printed local URL and stop it after QA.

- [ ] **Step 4: Inspect a redacted link-only test message in the browser**

With a temporary mailbox message whose HTML contains an action-labeled AWS tracking `href`, log in and verify:

1. The top query returns a row with `打开验证链接` and no code value.
2. The row shortcut displays `仅发现验证链接` and the same action beneath the query control.
3. Clicking the action opens a new tab only on the explicit click; do not click the real credential-bearing test link during QA.
4. The link target and rel attributes are `target="_blank"` and `rel="noopener noreferrer"`.
5. The account remains `未使用`, and the verification history does not gain a row for the link-only query.
6. A message containing both a code and a link still saves the code history and marks the account as used while displaying both actions.

Capture a desktop and narrow-window screenshot if layout changes are hard to inspect, then close the local server.

- [ ] **Step 5: Commit only after verification succeeds**

```bash
git status --short
git log --oneline --decorate -8
```

Expected: the branch contains the design, plan, parser, client, API, UI, and test commits; no unrelated user changes are staged. Hand off the branch for review/merge only after the verification commands and browser checks above pass.

---

## Self-Review Checklist

- [x] The design’s parser, API, persistence, UI, security, and browser-QA requirements each have a task.
- [x] Link-only, code-plus-link, invalid-scheme, malformed-HTML, and backward-compatible empty responses have explicit tests.
- [x] The plan keeps the original tracking `href`, never requests or rewrites it, and excludes it from SQLite history.
- [x] The plan preserves the existing code extraction priority and row usage behavior.
- [x] Every implementation step names exact files, symbols, commands, and expected results; no production code is changed while the execution approach is pending.
