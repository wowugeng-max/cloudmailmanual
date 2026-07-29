# Plain-Text Verification Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize verification links that appear as complete URLs in visible HTML or plain-text email bodies while preserving the existing safe link, history, and account-state behavior.

**Architecture:** Extend the existing stdlib `HTMLParser` service so it emits anchor candidates plus decoded visible `handle_data()` content, excluding `head`, `script`, `style`, `template`, and attributes. Scan visible HTML and plain text with a bounded HTTP(S) URL matcher, mask every literal URL span before collecting nearby text, feed distinct candidate evidence through the existing URL validator and action-term scorer, and cache URL work by `href` within one extraction call. `CloudMailClient` masks plain text directly and parser-produced visible HTML text separately; it never maps decoded URL spans back into raw HTML or runs whole-document `html.unescape()`. Routes, persistence, and UI contracts remain unchanged.

**Tech Stack:** Python 3.9, stdlib `html.parser`, `re`, `urllib.parse`, `unittest`, `pytest`, existing Flask application and Node VM UI tests.

---

## File Responsibilities

- `cloudmailmanual_app/services/verification_links.py`: Parse anchor and bare-text URL candidates, expose decoded visible HTML text, validate and score action evidence, return one untouched URL, and export literal equal-length HTTP(S) URL masking.
- `cloud_mail_client.py`: Supply both original body representations to the link parser while lazily scanning URL-masked plain text and parser-produced visible HTML text in the established precedence order.
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

The second test is critical: nearby context must exclude every matched URL span,
otherwise `confirm` inside the current or a neighboring opaque token could
bypass the existing false-positive protection.

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

- [ ] **Step 1: Add repeated-link context and caching regression coverage**

Add these context tests to `VerificationLinkExtractionTest`:

```python
def test_repeated_href_uses_strongest_occurrence_context(self):
    href = "https://example.test/account?token=synthetic-value"
    html = (
        "<p>Activate your account:</p>"
        f'<a href="{href}">{href}</a>'
    )

    self.assertEqual(extract_verification_link(html), href)


def test_repeated_opaque_urls_do_not_become_nearby_action_text(self):
    href = "https://example.test/account?token=prefix-confirm-suffix"
    text = f"Account details: {href} {href}"

    self.assertIsNone(extract_verification_link("", text))
```

Also add non-timing call-count tests using `unittest.mock.patch`:

- Many identical bare candidates with the same masked context call
  `_score_with_url_evidence` once.
- The same `href` with two different contexts calls validation once,
  `urlsplit` twice total (validation plus evidence), `_url_evidence` once, and
  `_score_with_url_evidence` twice.

Run the tests before changing production code. Expected: the positive repeated
context test fails because the anchor occurrence suppresses stronger nearby
context in the original implementation; the opaque URL test fails because one
URL leaks into the other's nearby text; the call-count tests fail because exact
candidates and per-`href` URL work are repeated. Do not use wall-clock timing in
these tests.

- [ ] **Step 2: Add bounded URL-matching constants**

After the existing encoded-query patterns, add:

```python
_BARE_HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TEXT_CONTEXT_RADIUS = 160
_TRAILING_SENTENCE_PUNCTUATION = ".,!"
_CLOSING_BRACKETS = {")": "(", "]": "[", "}": "{"}
```

This matcher has no nested quantifiers and stops at whitespace, quotes, or markup delimiters.

- [ ] **Step 3: Extend the HTML parser with visible text collection**

Add `visible_text_parts` in `_AnchorParser.__init__()`:

```python
self.visible_text_parts: List[str] = []
self._invisible_tags: List[str] = []
```

Replace `handle_data()` with:

```python
def handle_data(self, data: str) -> None:
    if self._invisible_tags:
        return
    self.visible_text_parts.append(data)
    if self._href is not None:
        self._text_parts.append(data)
```

This preserves nested visible anchor labels while excluding `head`, `script`,
`style`, and `template` text from both anchor and bare-link evidence. Add an
`extract_visible_html_text()` helper around the same parser; its output must be
derived only from `handle_data()` and must never include attributes. Push every
invisible start tag onto `_invisible_tags`; an invisible end tag may pop only
when it matches the stack top. Ignore mismatched closers so malformed markup
cannot lower hidden state. Treat self-closing `head`, `script`, `style`, and
`template` tags as opening tags too, keeping subsequent content hidden until a
matching end tag or EOF.

- [ ] **Step 4: Add conservative bare-URL cleanup and context helpers**

Place these helpers before `_score()`:

```python
def _trim_bare_url_candidate(value: str) -> str:
    trimmed = value.rstrip(_TRAILING_SENTENCE_PUNCTUATION)
    opening_counts = {opening: 0 for opening in _CLOSING_BRACKETS.values()}
    closing_counts = {closing: 0 for closing in _CLOSING_BRACKETS}
    for character in trimmed:
        if character in opening_counts:
            opening_counts[character] += 1
        elif character in closing_counts:
            closing_counts[character] += 1

    end = len(trimmed)
    while end and trimmed[end - 1] in _CLOSING_BRACKETS:
        closing = trimmed[end - 1]
        opening = _CLOSING_BRACKETS[closing]
        if opening_counts[opening] >= closing_counts[closing]:
            break
        closing_counts[closing] -= 1
        end -= 1
    return trimmed if end == len(trimmed) else trimmed[:end]


def _bare_url_candidates(value: str) -> List[_Anchor]:
    matches = list(_BARE_HTTP_URL_PATTERN.finditer(value))
    if not matches:
        return []

    masked_parts: List[str] = []
    previous_end = 0
    for match in matches:
        masked_parts.append(value[previous_end:match.start()])
        masked_parts.append(" " * (match.end() - match.start()))
        previous_end = match.end()
    masked_parts.append(value[previous_end:])
    masked_value = "".join(masked_parts)

    candidates: List[_Anchor] = []
    for match in matches:
        href = _trim_bare_url_candidate(match.group(0))
        if not href:
            continue

        before = masked_value[
            max(0, match.start() - _TEXT_CONTEXT_RADIUS):match.start()
        ]
        after = masked_value[
            match.end():match.end() + _TEXT_CONTEXT_RADIUS
        ]
        candidates.append(_Anchor(href=href, text=f"{before} {after}"))
    return candidates
```

Mask every matched URL span with equal-length spaces before slicing context. Do
not include the current or any neighboring URL in `text`; action terms inside
`token`, `signature`, and other opaque URL values must remain URL evidence only.

- [ ] **Step 5: Separate text scoring from parsed URL evidence**

Add a helper that accepts already-computed URL evidence, and keep `_score()` as
the compatibility wrapper:

```python
def _score_with_url_evidence(
    text: str,
    url_evidence: Tuple[str, ...],
) -> Optional[int]:
    action_text = _count_terms(text, _ACTION_TERMS)
    action_url = _count_terms_in_values(url_evidence, _ACTION_TERMS)
    if not action_text and not action_url:
        return None

    combined = (text, *url_evidence)
    support = _count_terms_in_values(combined, _SUPPORT_TERMS)
    footer = _count_terms_in_values(combined, _FOOTER_TERMS)
    return (
        action_text * _TEXT_ACTION_WEIGHT
        + action_url * _URL_ACTION_WEIGHT
        + support * _SUPPORT_WEIGHT
        - footer * _FOOTER_PENALTY
    )


def _score(anchor: _Anchor) -> Optional[int]:
    parsed = urlsplit(anchor.href)
    return _score_with_url_evidence(anchor.text, _url_evidence(parsed))
```

This preserves `_score()` behavior while allowing `extract_verification_link()`
to reuse cached evidence across occurrences of the same `href`.

- [ ] **Step 6: Update the public extractor while preserving compatibility**

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

    seen_candidates = set()
    validation_by_href = {}
    url_evidence_by_href = {}
    best_href: Optional[str] = None
    best_score: Optional[int] = None
    for candidate in candidates:
        href = candidate.href
        if not href:
            continue

        candidate_key = (href, candidate.text)
        if candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)

        if href not in validation_by_href:
            validation_by_href[href] = _is_absolute_http_url(href)
        if not validation_by_href[href]:
            continue

        if href not in url_evidence_by_href:
            parsed = urlsplit(href)
            url_evidence_by_href[href] = _url_evidence(parsed)

        score = _score_with_url_evidence(
            candidate.text,
            url_evidence_by_href[href],
        )
        if score is not None and (best_score is None or score > best_score):
            best_href = href
            best_score = score

    return best_href
```

Do not trim anchor `href` values. Preserve the parser-provided candidate
exactly for deduplication, validation, scoring, and return. Empty values are
skipped; any whitespace or control character causes validation failure. Reject
empty port markers, hostname empty labels, and literal host backslashes while
continuing to accept ordinary explicit ports. Access `parsed.port` so invalid
and out-of-range ports continue to raise and reject. Determine bracketed
authority from `parsed.netloc.startswith("[")`, require exactly one `[` and one
matching `]`, and accept only valid IPv6 literals (including supported zone
identifiers) or RFC IPvFuture literals inside the brackets. Reject bracketed
DNS names and IPv4 addresses. After `]`, accept only an empty suffix or `:`
followed by a non-empty port validated by `parsed.port`; reject text suffixes
and any additional bracket. For non-bracketed authority, reject all brackets
and colon-containing hostnames while retaining the existing minimal DNS-label
checks.

Skip only exact duplicate `(href, candidate.text)` evidence. Different
occurrences with different labels or nearby context remain independently
scored. Cache absolute-URL validation and parsed URL evidence by `href` for the
duration of one extraction call. The strict `score > best_score` comparison
keeps the earliest occurrence when scores tie.

Keep the existing `RuntimeError` propagation test green: unexpected parser failures must not be converted into a false successful result.

- [ ] **Step 7: Run the full parser suite**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest tests/test_verification_links.py -q
```

Expected: every anchor and bare-link parser test passes, including opaque-token,
all-URL context masking, malformed URL, invisible-content, repeated-href
context, exact-candidate deduplication, per-`href` caching, and exact-href
preservation cases.

- [ ] **Step 8: Check formatting and commit the parser implementation**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

Commit:

```bash
git add cloudmailmanual_app/services/verification_links.py \
  tests/test_verification_links.py
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

### Task 3 Follow-up: Exclude link tokens from code extraction

**Files:**
- Modify: `tests/test_verification_rules.py`
- Modify: `tests/test_verification_links.py`
- Modify: `cloudmailmanual_app/services/verification_links.py`
- Modify: `cloud_mail_client.py`
- Modify: `docs/superpowers/specs/2026-07-29-plain-text-verification-links-design.md`
- Modify: `docs/superpowers/plans/2026-07-29-plain-text-verification-links.md`

- [ ] **Step 1: Add failing client regressions**

Cover a plain-text-only URL with `token=ABC123` and require `code=""`. Add a
second message containing both a real `654321` code and the same synthetic URL
token, requiring the real code and untouched link. Use a visible HTML URL token
to preserve the same link-only contract for HTML bodies.

- [ ] **Step 2: Add the literal masking and visible-text contracts**

Export `mask_http_urls(value: str) -> str` from the verification-link service.
Reuse `_BARE_HTTP_URL_PATTERN`, replace each matched span with equal-length
spaces, return empty strings unchanged, and return `""` for non-string inputs.
The masker handles literal HTTP(S) spans only.

Export `extract_visible_html_text(raw_html: str) -> str` using stdlib
`HTMLParser(convert_charrefs=True)`. Collect only visible `handle_data()` text,
exclude `head`, `script`, `style`, and `template`, and never scan attributes.
Delete raw HTML decoded-span maps, `bisect`/`html.entities.html5` machinery, and
whole-document `html.unescape()` processing.

- [ ] **Step 3: Isolate body code extraction from URL tokens**

Within each message loop iteration, create body values lazily:

```python
code_subject = mask_http_urls(subject)
code_text = mask_http_urls(text)
visible_html = extract_visible_html_text(html)
code_html = mask_http_urls(visible_html)
```

Add a default-compatible `content_is_plain_text=False` argument to
`extract_verification_code()`. Use `True` for `code_text` and `code_html` so a
visible literal such as `<ABC123>` is not removed as markup. Reuse the single
`code_subject` value for both subject passes while retaining the original
subject for the API response. Preserve this exact order: masked-subject
non-digits, masked-subject digits, text non-digits, visible HTML non-digits,
text digits, visible HTML digits. Do not call `extract_visible_html_text()`
when text non-digits already matched. Continue calling
`extract_verification_link(html, text)` with the original bodies.

- [ ] **Step 4: Verify and commit**

Run the focused client tests, `tests/test_verification_rules.py`, and the
combined `tests/test_verification_links.py tests/test_verification_rules.py`
suites. Run `git diff --check`, then commit:

```bash
git commit -m "fix: exclude link tokens from code extraction"
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
- Literal HTTP(S) URLs are masked from the persisted subject and its remaining
  whitespace is normalized, while the API still returns the original subject.
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
- [x] The plan masks every URL span from nearby text evidence, preserving opaque-token false-positive protection across repeated links.
- [x] Repeated `href` occurrences with different contexts remain independent, while exact duplicate `(href, text)` evidence is scored once and collection order breaks ties.
- [x] Absolute-URL validation and parsed URL evidence are cached once per `href` within each extraction call.
- [x] Existing callers remain compatible through the optional
  `content_is_plain_text` argument.
- [x] The route sanitizes subject URLs only at the history persistence boundary;
  database schema, UI, Webmail, network, and decoding behavior remain unchanged.
- [x] The final task verifies the entire pre-existing verification-link feature before merging to `main`.
