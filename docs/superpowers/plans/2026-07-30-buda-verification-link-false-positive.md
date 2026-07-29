# Buda Verification Link False Positive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent ordinary six-letter uppercase words from preempting a valid verification link in an older mailbox message.

**Architecture:** Keep the existing newest-first message scan and verification-link parser. Narrow only the built-in `alnum_6` preset so it requires at least one uppercase ASCII letter and one digit, then prove the Buda two-message sequence reaches the older link.

**Tech Stack:** Python 3.9, `unittest`/`pytest`, stdlib `re`, existing Cloud Mail client and verification-link service.

---

### Task 1: Add Regression Coverage

**Files:**
- Modify: `tests/test_verification_rules.py:498`
- Modify: `tests/test_verification_rules.py:1236`

- [ ] **Step 1: Add a focused preset rejection test**

Add this test beside the existing `alnum_6` extraction tests:

```python
def test_alnum_preset_rejects_plain_uppercase_word(self):
    rules = {"enabled_presets": ["alnum_6"], "custom_patterns": []}

    self.assertIsNone(
        CloudMailClient.extract_verification_code(
            "WHAT YOUR AGENTS CAN DO",
            rules=rules,
        )
    )
```

- [ ] **Step 2: Add the Buda message-order regression test**

Add this test beside the existing multi-message query tests:

```python
def test_query_skips_newer_welcome_word_and_returns_older_buda_link(self):
    href = (
        "https://tracking.example.test/L0/"
        "https:%2F%2Fbuda.im%2Fapi%2Fauth%2Fverify-email%3Ftoken=redacted"
    )
    client = CloudMailClient.__new__(CloudMailClient)
    client._email_list = lambda **_: [
        {
            "content": "<h2>WHAT YOUR AGENTS CAN DO</h2>",
            "sendEmail": "noreply@budaapps.com",
            "subject": "Welcome to Buda AI: Agents as Company.",
            "createTime": "2026-07-29 20:41:29",
        },
        {
            "content": f'<a href="{href}">Verify Email Address</a>',
            "sendEmail": "noreply@budaapps.com",
            "subject": "Verify your email for Buda",
            "createTime": "2026-07-29 20:38:18",
        },
    ]

    self.assertEqual(
        client.query_verification_detail("a@example.com"),
        {
            "code": "",
            "verification_url": href,
            "sender": "noreply@budaapps.com",
            "subject": "Verify your email for Buda",
            "received_time": "2026-07-29 20:38:18",
        },
    )
```

- [ ] **Step 3: Run both tests and verify RED**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest -q \
  tests/test_verification_rules.py::ConfigurableExtractionTest::test_alnum_preset_rejects_plain_uppercase_word \
  tests/test_verification_rules.py::ConfigurableExtractionTest::test_query_skips_newer_welcome_word_and_returns_older_buda_link
```

Expected: both tests fail because `AGENTS` is returned as the code from the newer welcome message.

### Task 2: Tighten The Mixed Alphanumeric Preset

**Files:**
- Modify: `cloud_mail_client.py:32-34`
- Modify: `cloud_mail_client.py:239-242`
- Test: `tests/test_verification_rules.py`

- [ ] **Step 1: Require both a letter and a digit in the preset regex**

Replace the `alnum_6` pattern with:

```python
"alnum_6": [
    r"(?<![A-Z0-9])((?=[A-Z0-9]{0,5}[A-Z])(?=[A-Z0-9]{0,5}\d)(?=[A-Z0-9]{6}(?![A-Z0-9]))[A-Z0-9]{6})(?![A-Z0-9])"
],
```

- [ ] **Step 2: Keep defensive post-validation consistent**

Replace the `alnum_6` post-validation expression with:

```python
if preset_id == "alnum_6" and not re.fullmatch(
    r"(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{6}", code
):
    continue
```

- [ ] **Step 3: Run the focused tests and verify GREEN**

Run the same two-test command from Task 1.

Expected: `2 passed`.

- [ ] **Step 4: Run verification-specific regression suites**

Run:

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest -q \
  tests/test_verification_rules.py \
  tests/test_verification_code_extraction.py \
  tests/test_verification_links.py \
  tests/test_verification_rules_api.py \
  tests/test_row_verification_ui.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the implementation**

```bash
git add cloud_mail_client.py tests/test_verification_rules.py
git commit -m "fix: skip plain words when finding verification codes"
```

### Task 3: Full And Live Verification

**Files:**
- Verify: `cloud_mail_client.py`
- Verify: `templates/index.html`

- [ ] **Step 1: Run the complete test suite**

```bash
/Users/ruiyaosong/cloudmailmanual/.venv-mac/bin/python -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Check the embedded browser script syntax and diff**

```bash
perl -0777 -ne '@m=/<script>(.*?)<\/script>/sg; print $m[-1]' templates/index.html | node --check -
git diff --check origin/main...HEAD
```

Expected: both commands exit 0 with no output.

- [ ] **Step 3: Query the reported mailbox without exposing its token**

Run a short Python check that calls `CloudMailClient().query_verification_detail()` for the reported address and asserts:

```python
assert detail is not None
assert detail["code"] == ""
assert detail["verification_url"].startswith(("http://", "https://"))
assert detail["subject"] == "Verify your email for Buda"
```

Print only the subject and parsed hostname; never print the full URL or token.

- [ ] **Step 4: Request final code review**

Review `origin/main...HEAD`, focusing on regressions to mixed alphanumeric codes and the newest-first message contract. Resolve all Critical or Important findings before integration.

- [ ] **Step 5: Integrate and push**

Fast-forward `main`, rerun the complete suite on merged `main`, push normally to `origin/main`, and confirm the remote SHA. Do not modify the unrelated untracked `.DS_Store`.

- [ ] **Step 6: Restart the local service if it is running**

Use the existing macOS stop/start scripts so the running process loads the new code, then confirm the configured port responds. Do not change mailbox configuration.
