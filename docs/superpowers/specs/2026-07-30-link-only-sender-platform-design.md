# Link-Only Sender Platform Design

## Problem

The query API currently treats a message with a verification link but no code
as a link-only result. It returns the URL, keeps the account unused, skips query
history, and calls `mark_account_used(..., platform="")`. As a result, the
message sender is not appended to the account's platform field.

Code-bearing results already choose the platform in this order:

1. explicit platform supplied by the user;
2. sanitized message sender; or
3. `验证码查询` as a fallback.

The link-only path should use the same platform selection without changing its
unused or no-history semantics.

## Decision

For a valid link-only result:

- sanitize the sender with the existing URL-masking helper;
- select `explicit platform -> sanitized sender -> 验证码查询`;
- call `mark_account_used(email, used=False, platform=selected_platform)`;
- return the selected value as `mark_platform`;
- keep `auto_marked_used=False` and `saved=False`; and
- do not call `save_verification_query()`.

This writes durable platform metadata while preserving the account's `未使用`
status.

## UI Behavior

The top query already reloads account history after a successful response, so
the persisted platform will appear there automatically.

For a per-row quick query, update the existing platform cell in place from the
returned `mark_platform`. The row must remain unused, and the displayed
verification-link action must remain visible. Platform text is assigned through
`textContent`, not HTML interpolation.

If the platform already exists in the comma-separated cell value, do not add a
duplicate.

## Unchanged Behavior

- A result with neither code nor link keeps an empty platform update.
- A code-bearing result remains marked used and saved to query history.
- Verification URLs are never persisted to account or query-history metadata.
- Sender values are sanitized before platform persistence.
- An explicit platform remains authoritative over the sender.

## Testing

- API regression: link-only sender is written with `used=False`, returned as
  `mark_platform`, and no query history is saved.
- API regression: an explicit link-only platform overrides the sender.
- API regression: sender URLs are masked before platform persistence, with the
  existing fallback used when sanitization leaves an empty value.
- UI regression: a row quick query receives `mark_platform`, keeps the row
  unused, updates the platform cell without duplication, and preserves the link.
- Run focused API/UI tests, the complete suite, and a live Buda query against
  the restarted local service.
