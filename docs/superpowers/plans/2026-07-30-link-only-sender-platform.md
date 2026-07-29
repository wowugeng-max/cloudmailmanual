# Link-Only Sender Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the sanitized sender as the account platform for link-only verification results while keeping the account unused, and immediately reflect that platform in per-row quick-query UI.

**Architecture:** Reuse the existing verification metadata sanitizer and platform precedence in the `/api/query-code` link-only branch. Return the chosen platform to the browser, then extend the existing row-state helper to append it safely to the rendered platform cell without duplicates or disturbing the verification link.

**Tech Stack:** Python 3, Flask, `unittest`/`pytest`, vanilla JavaScript, Node.js VM-based frontend contract tests

---

## File Structure

- Modify `cloudmailmanual_app/routes.py`: select and persist the sanitized sender-derived platform for link-only query responses.
- Modify `templates/index.html`: identify the account platform cell, append returned platform text without duplication, and pass `mark_platform` through both row-query result paths.
- Modify `tests/test_verification_rules_api.py`: cover sender persistence, explicit override, sanitization fallback, unused state, and absence of query-history writes.
- Modify `tests/test_row_verification_ui.py`: cover the row helper contract, safe platform rendering, duplicate suppression, unused state, and verification-link preservation.

### Task 1: Add Link-Only API Regression Coverage

**Files:**
- Modify: `tests/test_verification_rules_api.py:303-334`
- Modify: `tests/test_verification_rules_api.py:428-467`

- [ ] **Step 1: Change the existing link-only test to require sender platform persistence**

Update the existing test so its final assertions are:

```python
        self.assertEqual(data["mark_platform"], "sender@example.test")
        self.assertFalse(data["saved"])
        self.assertFalse(data["auto_marked_used"])
        save_query.assert_not_called()
        mark_used.assert_called_once_with(
            "a@example.com", used=False, platform="sender@example.test"
        )
```

- [ ] **Step 2: Add explicit-platform and sanitized-sender cases for link-only results**

Add these tests immediately after the existing link-only test:

```python
    def test_link_only_explicit_platform_overrides_sender(self):
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": "",
                "verification_url": "https://example.test/verify?token=redacted",
                "sender": "sender@example.test",
                "subject": "Verify",
                "received_time": "2026-07-29 10:00:00",
            }
            response = self.client.post(
                "/api/query-code",
                json={"email": "a@example.com", "platform": "Manual Platform"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mark_platform"], "Manual Platform")
        self.assertFalse(data["saved"])
        self.assertFalse(data["auto_marked_used"])
        save_query.assert_not_called()
        mark_used.assert_called_once_with(
            "a@example.com", used=False, platform="Manual Platform"
        )

    def test_link_only_missing_platform_uses_sanitized_sender_or_fallback(self):
        href = "https://metadata.example.test/sender?token=SENDER123"
        cases = (
            (f"Mail service {href}", "Mail service"),
            (href, "验证码查询"),
        )
        self.login()

        for sender, expected_platform in cases:
            with self.subTest(sender=sender):
                with (
                    patch.object(routes, "CloudMailClient") as client_class,
                    patch.object(routes, "save_verification_query") as save_query,
                    patch.object(routes, "mark_account_used") as mark_used,
                ):
                    client_class.return_value.query_verification_detail.return_value = {
                        "code": "",
                        "verification_url": "https://example.test/verify?token=redacted",
                        "sender": sender,
                        "subject": "Verify",
                        "received_time": "2026-07-29 10:00:00",
                    }
                    response = self.client.post(
                        "/api/query-code",
                        json={"email": "a@example.com"},
                    )

                data = response.get_json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(data["sender"], sender)
                self.assertEqual(data["mark_platform"], expected_platform)
                self.assertFalse(data["saved"])
                self.assertFalse(data["auto_marked_used"])
                save_query.assert_not_called()
                mark_used.assert_called_once_with(
                    "a@example.com",
                    used=False,
                    platform=expected_platform,
                )
                self.assertNotIn("http", repr(mark_used.call_args))
                self.assertNotIn("token=", repr(mark_used.call_args))

    def test_detail_without_code_or_link_keeps_platform_empty(self):
        self.login()

        with (
            patch.object(routes, "CloudMailClient") as client_class,
            patch.object(routes, "save_verification_query") as save_query,
            patch.object(routes, "mark_account_used") as mark_used,
        ):
            client_class.return_value.query_verification_detail.return_value = {
                "code": "",
                "verification_url": "",
                "sender": "sender@example.test",
                "subject": "No verification data",
                "received_time": "2026-07-29 10:00:00",
            }
            response = self.client.post(
                "/api/query-code", json={"email": "a@example.com"}
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mark_platform"], "")
        self.assertFalse(data["saved"])
        self.assertFalse(data["auto_marked_used"])
        save_query.assert_not_called()
        mark_used.assert_called_once_with(
            "a@example.com", used=False, platform=""
        )
```

- [ ] **Step 3: Run the focused API tests and verify RED**

Run:

```bash
pytest -q tests/test_verification_rules_api.py -k "link_only"
```

Expected: the link-only tests fail because the response still returns an empty `mark_platform` and `mark_account_used()` still receives `platform=""`.

- [ ] **Step 4: Commit the failing API tests**

```bash
git add tests/test_verification_rules_api.py
git commit -m "test: cover link-only sender platform"
```

### Task 2: Persist the Link-Only Sender Platform

**Files:**
- Modify: `cloudmailmanual_app/routes.py:315-356`
- Test: `tests/test_verification_rules_api.py`

- [ ] **Step 1: Sanitize and select the platform before branching on code presence**

After `normalized_detail` is built, sanitize the sender once and select a platform only when a verification link is present:

```python
            history_sender = _sanitize_verification_metadata(
                normalized_detail["sender"]
            )

            if not normalized_detail["code"]:
                link_platform = ""
                if normalized_detail["verification_url"]:
                    link_platform = platform or history_sender or "验证码查询"
                mark_account_used(email, used=False, platform=link_platform)

                return jsonify({
                    "ok": True,
                    "email": email,
                    "saved": False,
                    "auto_marked_used": False,
                    "mark_platform": link_platform,
                    **normalized_detail,
                })
```

Remove the now-duplicated `history_sender` assignment from the code-bearing branch, but keep its existing platform selection immediately before `mark_account_used()`:

```python
            auto_platform = platform or history_sender or "验证码查询"
            mark_account_used(email, used=True, platform=auto_platform)
```

Leave the no-message branch unchanged so it continues to return and persist an empty platform.

- [ ] **Step 2: Run the focused API tests and verify GREEN**

Run:

```bash
pytest -q tests/test_verification_rules_api.py -k "link_only or missing_platform_uses_sanitized_sender"
```

Expected: all selected tests pass, including existing code-bearing platform precedence tests.

- [ ] **Step 3: Run the complete API test module**

Run:

```bash
pytest -q tests/test_verification_rules_api.py
```

Expected: the module passes with zero failures.

- [ ] **Step 4: Commit the backend implementation**

```bash
git add cloudmailmanual_app/routes.py
git commit -m "fix: persist sender for link-only queries"
```

### Task 3: Add Row Platform UI Regression Coverage

**Files:**
- Modify: `tests/test_row_verification_ui.py:28-37`
- Modify: `tests/test_row_verification_ui.py:369-393`
- Modify: `tests/test_row_verification_ui.py:550-601`

- [ ] **Step 1: Require the renderer and row-query calls to expose platform metadata**

Update the static contract test assertions to require:

```python
        self.assertIn("updateHistoryRowUsage(row, email, true, data.mark_platform)", html)
        self.assertIn("updateHistoryRowUsage(row, email, false, data.mark_platform)", html)
        self.assertIn('data-role="account-platform"', html)
```

Keep the existing assertions for `currentInUseEmail` state transitions.

- [ ] **Step 2: Exercise the real row helper instead of replacing it in the Node harness**

Store the real helper and stop overriding it:

```javascript
context.__realLoadQueryHistory = vm.runInContext('loadQueryHistory', context);
context.__realUpdateHistoryRowUsage = vm.runInContext('updateHistoryRowUsage', context);
context.__onHistoryLoad = () => {};
vm.runInContext(`
  bindCopyHandlers = () => {};
  loadHistory = () => {};
  loadQueryHistory = (...args) => __onHistoryLoad(...args);
  resolveHistoryProfileId = () => 'profile-1';
`, context);
```

Extend `makeQuickSurface()` with status, platform, and action elements that satisfy `updateHistoryRowUsage()`:

```javascript
  const statusCell = makeElement('td');
  const platformCell = makeElement('td');
  const actionCell = makeElement('td');
  const actionButton = makeElement('button');
  statusCell.textContent = '未使用';
  statusCell.dataset.copy = '未使用';
  platformCell.textContent = 'Existing Platform';
  platformCell.dataset.copy = 'Existing Platform';
  actionCell.className = 'history-action-col';
  actionCell.appendChild(actionButton);
  row.setQuerySelector('[data-role="account-status"]', statusCell);
  row.setQuerySelector('[data-role="account-platform"]', platformCell);
  row.setQuerySelector('.history-action-col button', actionButton);
```

Add the returned elements to the surface object:

```javascript
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
```

Add a map-backed exact-selector override to `makeElement()` alongside its existing closest-element map:

```javascript
  const attributes = {};
  const closestElements = {};
  const querySelectorElements = {};
```

Replace its current `querySelector()` with:

```javascript
    querySelector(selector) {
      return querySelectorElements[selector] || findDescendants(this, selector)[0] || null;
    },
    setQuerySelector(selector, target) {
      querySelectorElements[selector] = target;
    },
```

Make the attribute mock mirror browser `dataset` behavior so `data-copy` assertions observe `setAttribute()` updates:

```javascript
      if (normalizedName.startsWith('data-')) {
        const datasetName = normalizedName
          .slice(5)
          .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        this.dataset[datasetName] = normalizedValue;
      }
```

Place this inside `setAttribute()` after writing `attributes[normalizedName]`.

- [ ] **Step 3: Assert link-only platform display, duplicate suppression, unused state, and link preservation**

Replace the `usageUpdates` spy assertions with real DOM-state assertions:

```javascript
  const quickSurface = makeQuickSurface();
  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
    mark_platform: 'sender@example.com',
  });
  assertAnchor(quickSurface.linkResult, 'quick link-only');
  assert.strictEqual(quickSurface.codeResult.textContent, '仅发现验证链接');
  assert.strictEqual(quickSurface.statusCell.textContent, '未使用');
  assert.strictEqual(quickSurface.platformCell.textContent, 'Existing Platform, sender@example.com');
  assert.strictEqual(quickSurface.platformCell.dataset.copy, 'Existing Platform, sender@example.com');

  await runQuickQuery(quickSurface, {
    ok: true,
    code: '',
    verification_url: safeUrl,
    mark_platform: 'sender@example.com',
  });
  assertAnchor(quickSurface.linkResult, 'quick duplicate platform');
  assert.strictEqual(quickSurface.platformCell.textContent, 'Existing Platform, sender@example.com');
```

For the code-bearing quick-query case, include `mark_platform: 'Code Platform'` and assert:

```javascript
  assert.strictEqual(quickCodeAndLink.statusCell.textContent, '正在使用');
  assert.strictEqual(quickCodeAndLink.platformCell.textContent, 'Existing Platform, Code Platform');
  assert.strictEqual(quickHistoryLoads, 1);
```

- [ ] **Step 4: Run the frontend contract test and verify RED**

Run:

```bash
pytest -q tests/test_row_verification_ui.py
```

Expected: static assertions and/or Node runtime assertions fail because `mark_platform` is not passed and the platform cell is not updated.

- [ ] **Step 5: Commit the failing UI tests**

```bash
git add tests/test_row_verification_ui.py
git commit -m "test: cover row platform updates"
```

### Task 4: Update the Row Platform In Place

**Files:**
- Modify: `templates/index.html:1293-1317`
- Modify: `templates/index.html:1357-1367`
- Modify: `templates/index.html:1444-1445`
- Test: `tests/test_row_verification_ui.py`

- [ ] **Step 1: Extend the row-state helper with duplicate-safe platform appending**

Change the helper signature and add the platform update after the status cell update:

```javascript
function updateHistoryRowUsage(row, email, used, platform = '') {
  if (used) {
    currentInUseEmail = email;
  } else if (currentInUseEmail && currentInUseEmail.toLowerCase() === String(email).toLowerCase()) {
    currentInUseEmail = '';
  }

  if (!row) return;
  row.classList.toggle('in-use-row', used);

  const statusText = used ? '正在使用' : '未使用';
  const statusCell = row.querySelector('[data-role="account-status"]');
  if (statusCell) {
    statusCell.textContent = statusText;
    statusCell.setAttribute('data-copy', statusText);
  }

  const normalizedPlatform = String(platform || '').trim();
  const platformCell = row.querySelector('[data-role="account-platform"]');
  if (platformCell && normalizedPlatform) {
    const platforms = String(platformCell.textContent || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    if (!platforms.includes(normalizedPlatform)) {
      platforms.push(normalizedPlatform);
    }
    const platformText = platforms.join(', ');
    platformCell.textContent = platformText;
    platformCell.setAttribute('data-copy', platformText);
  }

  const actionButton = row.querySelector('.history-action-col button');
  if (actionButton) {
    actionButton.dataset.email = email;
    actionButton.dataset.used = used ? '1' : '0';
    actionButton.className = used ? 'btn-secondary' : 'btn-warning';
    actionButton.textContent = used ? '改为未使用' : '标记正在使用';
  }
}
```

- [ ] **Step 2: Pass the returned platform through both quick-query paths**

Update the calls in `quickQueryCode()`:

```javascript
      updateHistoryRowUsage(row, email, true, data.mark_platform);
```

and:

```javascript
      updateHistoryRowUsage(row, email, false, data.mark_platform);
```

- [ ] **Step 3: Mark the rendered platform cell for safe lookup**

Change the platform table cell to:

```html
        <td class="history-platform-col" data-role="account-platform" data-copy="${platforms}">${platforms}</td>
```

- [ ] **Step 4: Run the frontend contract test and verify GREEN**

Run:

```bash
pytest -q tests/test_row_verification_ui.py
```

Expected: the frontend contract module passes with zero failures.

- [ ] **Step 5: Commit the frontend implementation**

```bash
git add templates/index.html
git commit -m "fix: show queried sender in account row"
```

### Task 5: Verify, Integrate, and Push

**Files:**
- Verify: `cloudmailmanual_app/routes.py`
- Verify: `templates/index.html`
- Verify: `tests/test_verification_rules_api.py`
- Verify: `tests/test_row_verification_ui.py`

- [ ] **Step 1: Run all focused regressions together**

Run:

```bash
pytest -q tests/test_verification_rules_api.py tests/test_row_verification_ui.py
```

Expected: both modules pass with zero failures.

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
pytest -q
```

Expected: at least 170 tests pass with zero failures.

- [ ] **Step 3: Review the final diff and confirm scope**

Run:

```bash
git diff main...HEAD -- cloudmailmanual_app/routes.py templates/index.html tests/test_verification_rules_api.py tests/test_row_verification_ui.py
```

Expected: only the approved link-only sender-platform behavior, its UI synchronization, and regression tests are present.

- [ ] **Step 4: Fast-forward the local `main` branch**

```bash
git switch main
git merge --ff-only codex/link-only-platform
```

Expected: `main` advances without a merge commit.

- [ ] **Step 5: Re-run the complete test suite on `main`**

Run:

```bash
pytest -q
```

Expected: at least 170 tests pass with zero failures on the branch that will be pushed.

- [ ] **Step 6: Push `main` to the requested GitHub repository**

Run:

```bash
git push https://github.com/wowugeng-max/cloudmailmanual.git main:main
```

Expected: GitHub accepts the update to `main`.

- [ ] **Step 7: Restart the persistent macOS service**

Run:

```bash
open /Users/ruiyaosong/cloudmailmanual/run_web_mac.command
```

Expected: the application becomes available at `http://127.0.0.1:8080`.

- [ ] **Step 8: Verify the live link-only behavior without exposing the verification token**

Query `/api/query-code` through the authenticated local application using `logan_u_gonzales.258@edu.edge.mailyplus.com`, then verify:

```text
ok=true
code is empty
verification_url is present
mark_platform=noreply@budaapps.com
saved=false
auto_marked_used=false
```

Inspect the account record and verify:

```text
used=0
platforms contains noreply@budaapps.com exactly once
```

Do not print the full verification URL or its token in command output or the final report.
