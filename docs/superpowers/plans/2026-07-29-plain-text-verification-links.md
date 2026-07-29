# Plain-Text Verification Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize verification links that appear as complete URLs in visible HTML or plain-text email bodies while preserving the existing safe link, history, and account-state behavior.

**Architecture:** Extend the existing stdlib `HTMLParser` service so it emits anchor candidates plus visible-text content, then scan visible HTML and plain text with a bounded HTTP(S) URL matcher. Feed every candidate through the existing URL validator and action-term scorer, excluding the URL itself from nearby text evidence so opaque token values cannot create false positives. Pass both message body representations from `CloudMailClient` without changing routes, persistence, or UI contracts.

**Tech Stack:** Python 3.9, stdlib `html.parser`, `re`, `urllib.parse`, `unittest`, `pytest`, existing Flask application and Node VM UI tests.

---

## File Responsibilities

- `cloudmailmanual_app/services/verification_links.py`: Parse anchor and bare-text URL candidates, validate them, score action evidence, and return one untouched URL.
- `cloud_mail_client.py`: Supply both HTML and plain-text message bodies to the parser while preserving code extraction precedence.
- `tests/test_verification_links.py`: Define the parser's positive, negative, boundary, preservation, and security contracts.
- `tests/test_verification_rules.py`: Verify `CloudMailClient` integration and unchanged link-only/code-plus-link semantics.

### Task 1: Define the bare-link parser contract

**Files:**
- Modify: `tests/test_verification_links.py:1-230`
- Reference: `cloudmailmanual_app/services/verification_links.py:1-245`

- [ ] **Step 1: Add a screenshot-shaped visible HTML URL test**

Add this test to `VerificationLinkExtractionTest`:

```python
def test_extracts_visible_html_bare_activation_url_with_long_query(self):
    href = (
        "https://app.example.test/api/auth/verify-email?"
        "token=eyJhbGciOiJIUzI1NiJ9.synthetic.signature"
        "&callbackURL=%2Fmanage%2Freferral"
    )
    html = (
        "<h1>Activate your account</h1>"
        "<p>Please click the link below to activate your account.</p>"
        f"<p>{href.replace('&', '&amp;')}</p>"
        "<p>If you did not create an account, ignore this email.</p>"
    )

    self.assertEqual(extract_verification_link(html), href)
```

This mirrors the reported format without storing the real token shown in the mailbox screenshot.

- [ ] **Step 2: Add plain-text and full-URL-label tests**

Add:

```python
def test_extracts_plain_text_bare_verification_url(self):
    href = "https://example.test/verify-email?token=synthetic-value"
    text = f"Activate your account\n\n{href}\n\nIgnore this email if unexpected."

    self.assertEqual(extract_verification_link("", text), href)

def test_extracts_anchor_whose_visible_label_is_the_full_url(self):
    href = "https://example.test/activate?token=synthetic-value"
    html = f'<a href="{href}">{href}</a>'

    self.assertEqual(extract_verification_link(html), href)
```

- [ ] **Step 3: Add nearby-context and opaque-token separation tests**

Add:

```python
def test_nearby_action_copy_qualifies_generic_bare_token_url(self):
    href = "https://example.test/account?token=synthetic-value"
    text = f"Complete your account setup using this link: {href}"

    self.assertEqual(extract_verification_link("", text), href)

def test_action_word_inside_opaque_bare_token_is_not_text_evidence(self):
    text = (
        "Account details: "
        "https://example.test/account?token=prefix-confirm-suffix"
    )

    self.assertIsNone(extract_verification_link("", text))
```

The second test is critical: nearby context must exclude the URL itself, otherwise `confirm` inside an opaque token would bypass the existing false-positive protection.

- [ ] **Step 4: Add invisible-content, punctuation, and no-reconstruction tests**

Add:

```python
def test_ignores_bare_links_inside_invisible_html_content(self):
    html = (
        "<script>https://example.test/verify?token=script</script>"
        "<style>https://example.test/confirm?token=style</style>"
        "<template>https://example.test/activate?token=template</template>"
        "<p>Read the account update.</p>"
    )

    self.assertIsNone(extract_verification_link(html))

def test_trims_sentence_punctuation_without_truncating_query(self):
    href = (
        "https://example.test/verify-email?token=synthetic-value"
        "&callbackURL=%2Fmanage%2Freferral"
    )
    text = f"Activate your account here ({href})."

    self.assertEqual(extract_verification_link("", text), href)

def test_does_not_reconstruct_bare_url_across_whitespace(self):
    text = "Activate using https://\nexample.test/verify?token=synthetic-value"

    self.assertIsNone(extract_verification_link("", text))
```

- [ ] **Step 5: Run the new parser tests and confirm the red state**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_extracts_visible_html_bare_activation_url_with_long_query \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_extracts_plain_text_bare_verification_url \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_nearby_action_copy_qualifies_generic_bare_token_url \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_action_word_inside_opaque_bare_token_is_not_text_evidence \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_ignores_bare_links_inside_invisible_html_content \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_trims_sentence_punctuation_without_truncating_query \
  tests/test_verification_links.py::VerificationLinkExtractionTest::test_does_not_reconstruct_bare_url_across_whitespace -q
```

Expected: tests that pass a second argument fail with a signature error; visible HTML bare-link and punctuation tests fail because only anchor `href` values are currently collected. Existing anchor behavior remains green.

- [ ] **Step 6: Commit the parser contract**

```bash
git add tests/test_verification_links.py
git commit -m "test: define plain-text verification link contract"
```

### Task 2: Collect and score visible-text URL candidates

**Files:**
- Modify: `cloudmailmanual_app/services/verification_links.py:1-245`
- Test: `tests/test_verification_links.py`

- [ ] **Step 1: Add bounded URL-matching constants**

After the existing encoded-query patterns, add:

```python
_BARE_HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TEXT_CONTEXT_RADIUS = 160
_TRAILING_SENTENCE_PUNCTUATION = ".,!"
_CLOSING_BRACKETS = {")": "(", "]": "[", "}": "{"}
```

This matcher has no nested quantifiers and stops at whitespace, quotes, or markup delimiters.

- [ ] **Step 2: Extend the HTML parser with visible text collection**

Add `visible_text_parts` in `_AnchorParser.__init__()`:

```python
self.visible_text_parts: List[str] = []
```

Replace `handle_data()` with:

```python
def handle_data(self, data: str) -> None:
    if self._invisible_depth:
        return
    self.visible_text_parts.append(data)
    if self._href is not None:
        self._text_parts.append(data)
```

This preserves nested visible anchor labels while excluding `script`, `style`, and `template` text from both anchor and bare-link evidence.

- [ ] **Step 3: Add conservative bare-URL cleanup and context helpers**

Place these helpers before `_score()`:

```python
def _trim_bare_url_candidate(value: str) -> str:
    trimmed = value.rstrip(_TRAILING_SENTENCE_PUNCTUATION)
    while trimmed and trimmed[-1] in _CLOSING_BRACKETS:
        closing = trimmed[-1]
        opening = _CLOSING_BRACKETS[closing]
        if trimmed.count(opening) >= trimmed.count(closing):
            break
        trimmed = trimmed[:-1]
    return trimmed


def _bare_url_candidates(value: str) -> List[_Anchor]:
    candidates: List[_Anchor] = []
    for match in _BARE_HTTP_URL_PATTERN.finditer(value):
        href = _trim_bare_url_candidate(match.group(0))
        if not href:
            continue

        before = value[max(0, match.start() - _TEXT_CONTEXT_RADIUS):match.start()]
        after = value[match.end():match.end() + _TEXT_CONTEXT_RADIUS]
        candidates.append(_Anchor(href=href, text=f"{before} {after}"))
    return candidates
```

Do not include `match.group(0)` in `text`; action terms inside `token`, `signature`, and other opaque URL values must remain URL evidence only.

- [ ] **Step 4: Update the public extractor while preserving compatibility**

Replace `extract_verification_link()` with:

```python
def extract_verification_link(
    raw_html: str,
    raw_text: str = "",
) -> Optional[str]:
    if not isinstance(raw_html, str) or not isinstance(raw_text, str):
        return None
    if not raw_html and not raw_text:
        return None

    parser = _AnchorParser()
    if raw_html:
        try:
            parser.feed(raw_html)
            parser.close()
        except (TypeError, ValueError):
            return None

    visible_html = " ".join(parser.visible_text_parts)
    candidates = [
        *parser.anchors,
        *_bare_url_candidates(visible_html),
        *_bare_url_candidates(raw_text),
    ]

    seen_hrefs = set()
    best_href: Optional[str] = None
    best_score: Optional[int] = None
    for candidate in candidates:
        href = candidate.href.strip()
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        if not _is_absolute_http_url(href):
            continue

        score = _score(_Anchor(href, candidate.text))
        if score is not None and (best_score is None or score > best_score):
            best_href = href
            best_score = score

    return best_href
```

Keep the existing `RuntimeError` propagation test green: unexpected parser failures must not be converted into a false successful result.

- [ ] **Step 5: Run the full parser suite**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest tests/test_verification_links.py -q
```

Expected: every anchor and bare-link parser test passes, including opaque-token, malformed URL, invisible-content, and exact-href preservation cases.

- [ ] **Step 6: Check formatting and commit the parser implementation**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

Commit:

```bash
git add cloudmailmanual_app/services/verification_links.py
git commit -m "feat: extract verification links from visible message text"
```

### Task 3: Pass the plain-text message body through the client

**Files:**
- Modify: `tests/test_verification_rules.py:600-750`
- Modify: `cloud_mail_client.py:251-320`

- [ ] **Step 1: Add a failing plain-text-only client test**

Add to `ConfigurableExtractionTest`:

```python
def test_query_detail_returns_plain_text_bare_link_without_html(self):
    href = "https://example.test/verify-email?token=synthetic-value"
    client = CloudMailClient.__new__(CloudMailClient)
    client._email_list = lambda **_: [
        {
            "text": f"Activate your account using {href}",
            "sendEmail": "sender@example.test",
            "subject": "Activate your account",
            "createTime": "2026-07-29 12:00:00",
        }
    ]

    self.assertEqual(
        client.query_verification_detail("a@example.com"),
        {
            "code": "",
            "verification_url": href,
            "sender": "sender@example.test",
            "subject": "Activate your account",
            "received_time": "2026-07-29 12:00:00",
        },
    )
```

- [ ] **Step 2: Add an argument-forwarding contract test**

Add:

```python
def test_query_detail_passes_html_and_text_to_link_extractor(self):
    html = "<p>Rendered message</p>"
    text = "Plain message"
    href = "https://example.test/confirm?token=synthetic-value"
    client = CloudMailClient.__new__(CloudMailClient)
    client._email_list = lambda **_: [
        {"content": html, "text": text, "subject": "Confirm account"}
    ]

    with patch(
        "cloud_mail_client.extract_verification_link",
        return_value=href,
    ) as extract_link:
        detail = client.query_verification_detail("a@example.com")

    extract_link.assert_called_once_with(html, text)
    self.assertEqual(detail["verification_url"], href)
```

- [ ] **Step 3: Run the client tests and confirm the red state**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest \
  tests/test_verification_rules.py::ConfigurableExtractionTest::test_query_detail_returns_plain_text_bare_link_without_html \
  tests/test_verification_rules.py::ConfigurableExtractionTest::test_query_detail_passes_html_and_text_to_link_extractor -q
```

Expected: the plain-text-only detail is `None`, and the forwarding assertion reports that the extractor received only `html`.

- [ ] **Step 4: Pass both body representations to the parser**

In `CloudMailClient.query_verification_detail()`, replace:

```python
verification_url = extract_verification_link(html) or ""
```

with:

```python
verification_url = extract_verification_link(html, text) or ""
```

Do not move this call outside the current message loop and do not change the existing code extraction order.

- [ ] **Step 5: Run focused client and parser regression suites**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest \
  tests/test_verification_links.py tests/test_verification_rules.py -q
```

Expected: all tests pass. Link-only messages still return `code=""`; code-plus-link messages still return both values; results from separate messages are not combined.

- [ ] **Step 6: Commit the client integration**

```bash
git add cloud_mail_client.py tests/test_verification_rules.py
git commit -m "feat: scan plain-text email bodies for verification links"
```

### Task 4: Complete regression and security verification

**Files:**
- Inspect: `cloudmailmanual_app/services/verification_links.py`
- Inspect: `cloud_mail_client.py`
- Inspect: `cloudmailmanual_app/routes.py`
- Inspect: `templates/index.html`
- Test: `tests/test_verification_links.py`
- Test: `tests/test_verification_rules.py`
- Test: `tests/test_verification_rules_api.py`
- Test: `tests/test_row_verification_ui.py`

- [ ] **Step 1: Run the full Python test suite**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest -q
```

Expected: all tests pass. The existing urllib3 LibreSSL warning is non-blocking.

- [ ] **Step 2: Validate the main browser script syntax and UI runtime contract**

Run:

```bash
perl -0777 -ne '@m=/<script>(.*?)<\/script>/sg; print $m[-1]' \
  templates/index.html | node --check -
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest \
  tests/test_row_verification_ui.py -q
```

Expected: Node exits `0`, and all UI tests pass. The token-bearing verification URL appears only as an anchor `href` property in the runtime harness.

- [ ] **Step 3: Check diffs and scan for network, decoding, and persistence regressions**

Run:

```bash
git diff --check
git status --short
rg -n "verification_url|extract_verification_link|urlopen|requests\.|httpx\.|unquote|token=" \
  cloud_mail_client.py cloudmailmanual_app templates tests
```

Expected:

- `git diff --check` is clean.
- The worktree contains only intended commits and no uncommitted files.
- No parser code calls a network client or URL decoder.
- `verification_url` remains excluded from `save_verification_query()` input.
- Test URLs contain only synthetic or explicitly redacted token values.

- [ ] **Step 4: Inspect the final commit range**

Run:

```bash
git log --oneline --decorate origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: the branch contains the existing verification-link feature plus the plain-text parser contract, parser implementation, and client integration commits; no unrelated user files are included.

- [ ] **Step 5: Request final whole-feature review before merging**

The reviewer must inspect the complete `origin/main...HEAD` range for parser false positives, token leakage, persistence, UI link safety, and unchanged code/history/account semantics. Resolve every Critical or Important finding and rerun Steps 1-4 before merging and pushing `main`.

---

## Self-Review Checklist

- [x] Every design goal maps to a parser or client task.
- [x] Visible HTML, plain text, full-URL anchor labels, long queries, nearby context, invisible content, sentence punctuation, and whitespace boundaries have explicit tests.
- [x] The plan explicitly excludes the URL itself from nearby text evidence, preserving opaque-token false-positive protection.
- [x] Existing callers remain compatible through the optional `raw_text` argument.
- [x] No route, database, UI, Webmail, network, decoding, or persistence changes are introduced.
- [x] The final task verifies the entire pre-existing verification-link feature before merging to `main`.
