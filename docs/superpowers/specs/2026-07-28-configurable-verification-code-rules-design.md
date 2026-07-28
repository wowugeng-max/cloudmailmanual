# Configurable Verification Code Rules

## Goal

Allow verification-code formats to be configured from the existing mail settings tab. Saved changes must apply to the next verification query without restarting the Flask process or changing code.

## Scope

- One global rule set shared by every mail profile.
- Built-in format toggles for common code styles.
- Custom regular expressions for formats not covered by built-ins.
- An in-page tester for validating rules against sample email content.
- Existing installations retain the current extraction behavior by default.

Per-profile rules, rule version history, and sender-specific routing are outside this change.

## Configuration Model

The rule set is stored at the top level of `config.json`, separate from `mail_profiles`:

```json
{
  "verification_code_rules": {
    "enabled_presets": [
      "digits_6",
      "digits_spaced_3_3",
      "alnum_6",
      "alnum_hyphen_3_3",
      "labeled_code"
    ],
    "custom_patterns": [
      {
        "name": "Example",
        "pattern": "verification token\\s*[:：]\\s*([A-Z0-9]{8})"
      }
    ]
  }
}
```

If `verification_code_rules` is absent, the repository returns all default presets and no custom patterns. Saving rules preserves unrelated configuration keys.

## Built-In Presets

The UI exposes checkboxes for these stable preset IDs:

| ID | Example | Purpose |
| --- | --- | --- |
| `digits_6` | `123456` | Six consecutive digits |
| `digits_spaced_3_3` | `331 781` | Two groups of three digits |
| `alnum_6` | `6PN6XW` | Six uppercase letters or digits |
| `alnum_hyphen_3_3` | `ABC-123` | Two groups separated by a hyphen |
| `labeled_code` | `Verification code: 123456` | Code following a recognized label |

Preset definitions remain in Python rather than in `config.json`. The configuration stores only enabled IDs so implementation details can be corrected without migrating user data.

## Custom Pattern Syntax

The editor accepts one rule per line:

```text
Rule name :: regular expression
```

Requirements:

- The separator is the first `::` in the line.
- Both name and expression are required.
- Each expression must compile with Python `re.IGNORECASE`.
- Each expression must contain at least one capturing group.
- The first captured group is the verification code.
- Whitespace is removed from the captured result; punctuation such as hyphens is preserved.
- Empty lines are ignored.
- Duplicate names or expressions are rejected.
- A maximum of 50 custom rules and 500 characters per expression prevents accidental configuration abuse.

Custom patterns run before built-in presets so a newly configured format can override a broader built-in match.

## Extraction Flow

`CloudMailClient.query_verification_detail()` loads the normalized global rule set once at the start of each query. It passes that immutable rule set to every subject, text, and HTML extraction attempt for that query.

The extraction order remains:

1. Subject with numeric-only candidates disabled.
2. Subject with all configured candidates enabled.
3. Plain text and HTML with numeric-only candidates disabled.
4. Plain text and HTML with all configured candidates enabled.

Within each extraction attempt:

1. Strip non-content HTML and normalize whitespace.
2. Limit normalized content to 200,000 characters.
3. Try custom patterns in their configured order.
4. Try enabled built-in presets in their defined order.
5. Reject known non-code sentinel values already excluded by the current implementation.

Reading `config.json` per verification query provides hot loading. No module-level cache or process restart is used.

## Backend Boundaries

Create a focused `verification_rules` repository responsible for:

- Default rule values.
- Reading and normalizing `verification_code_rules`.
- Parsing the custom-pattern textarea representation.
- Compiling and validating custom regular expressions.
- Saving only the global rule section while preserving the rest of `config.json`.

Add authenticated endpoints:

- `GET /api/settings/verification-code-rules`
  Returns enabled presets, available preset metadata, and custom rules.
- `POST /api/settings/verification-code-rules`
  Validates and saves the rule set. Invalid input returns HTTP 400 with a specific message and line number where applicable.
- `POST /api/settings/verification-code-rules/test`
  Validates the submitted unsaved rule set, runs it against sample content, and returns the extracted code or an empty result. Testing does not modify `config.json` or account state.

The existing mail-profile API remains unchanged so an invalid mail profile cannot block saving verification rules.

## User Interface

Add an un-nested settings section below the mail-profile table in the `邮箱配置` tab:

- A compact checkbox group for built-in formats.
- A multiline custom-pattern editor.
- A sample-content textarea.
- `测试规则` and `保存验证码规则` buttons.
- One status area for validation errors, test results, and save confirmation.

Loading the mail settings tab also loads the rule set. Saving updates only the rule controls and does not submit or rerender mail profiles. A successful save message states that the next query will use the new rules.

## Error Handling And Security

- Regex compilation occurs on the backend; browser validation is advisory only.
- Validation errors do not overwrite the last valid configuration.
- The tester has no mailbox, account-status, or query-history side effects.
- Test content is limited to 100,000 characters, and extraction content is limited to 200,000 normalized characters.
- Configuration count and expression-length limits reduce accidental expensive regular expressions; only authenticated administrators can edit rules.
- UI output uses `textContent`; configured names and patterns are never inserted as raw HTML.
- Unknown preset IDs are ignored when reading legacy or manually edited files and rejected when saving through the API.

## Compatibility

- Missing configuration maps to all current built-in formats enabled.
- Existing `CloudMailClient.extract_verification_code(content)` callers continue to work by using default rules when no explicit rule set is supplied.
- The spaced six-digit format `331 781` continues to return `331781`.
- Mail profile configuration, exports, and existing history data are unaffected.

## Testing

Backend tests cover:

- Defaults when the key is absent.
- Saving rules while preserving unrelated config and mail profiles.
- Invalid regex, missing capture group, duplicates, unknown presets, count limits, and expression length limits.
- Custom-rule priority over built-ins.
- Whitespace removal from captured results.
- Disabled presets no longer matching.
- Hot loading by changing config between two queries without recreating the process.
- Test endpoint side-effect isolation.

Frontend tests cover the presence and wiring of preset controls, custom-pattern editor, tester, save action, and error/status output. The full existing suite and JavaScript syntax check remain required.
