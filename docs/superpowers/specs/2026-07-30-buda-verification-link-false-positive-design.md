# Buda Verification Link False Positive Design

## Problem

The mailbox API returns messages newest first. For the reported Buda account,
the welcome message arrived three minutes after the verification message. Its
visible HTML contains the heading `WHAT YOUR AGENTS CAN DO`.

The built-in `alnum_6` preset currently accepts any six-character uppercase
ASCII word because it only requires a letter. It therefore extracts `AGENTS`
as a code and returns the welcome message before the scanner reaches the older
message containing the valid `Verify Email Address` link.

The verification-link parser itself already recognizes the Buda tracking URL.

## Decision

Tighten only the built-in `alnum_6` preset so a match must contain:

- exactly six ASCII uppercase letters or digits;
- at least one ASCII letter; and
- at least one ASCII digit.

Examples accepted by the preset include `ABC123`, `6PN6XW`, and `CODE99`.
Ordinary uppercase words such as `AGENTS` and `VERIFY` are rejected.

Explicitly labelled all-letter codes remain supportable through the existing
`labeled_code` preset, and unusual formats remain supportable through custom
rules in the UI.

## Scope

- Update the `alnum_6` regular expression and its defensive post-validation in
  `cloud_mail_client.py`.
- Add a focused extraction test proving `AGENTS` is rejected while mixed codes
  still work.
- Add an integration regression test with a newer Buda-style welcome message
  followed by an older verification-link message.
- Do not change link scoring, API response shapes, persistence, or UI layout.

## Data Flow

1. Query messages newest first, as today.
2. Scan the welcome message. `AGENTS` no longer qualifies as `alnum_6`, so the
   message produces neither a code nor a verification link and is skipped.
3. Scan the older verification message.
4. Return its existing, validated HTTP(S) verification URL.

## Error And Compatibility Behavior

- Existing six-digit, spaced-digit, hyphenated, labelled, and custom patterns
  are unchanged.
- Existing mixed six-character codes continue to match.
- A user who needs an unlabelled all-letter six-character code can add an
  explicit custom pattern instead of enabling broad ordinary-word matching.
- No remote verification URL is opened or requested by the backend.

## Testing

- RED: `alnum_6` rejects `AGENTS` and the two-message Buda regression currently
  returns the wrong result.
- GREEN: both focused tests pass after tightening the preset.
- Run the verification rules/link suites and then the complete test suite.
- Query the reported mailbox and confirm the returned detail contains no code
  and contains the Buda verification URL.
