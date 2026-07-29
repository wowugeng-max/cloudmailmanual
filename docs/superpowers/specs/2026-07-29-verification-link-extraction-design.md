# Verification Link Extraction

## Goal

Support verification emails that contain an action link instead of a numeric
verification code. The existing code-based extraction behavior remains
unchanged, while the query result can expose a safe, user-clickable link.

## Observed Format

The tested message uses an HTML anchor similar to:

```html
<a href="https://tracking.example/L0/https:%2F%2Fservice.example%2Fapi%2Fverify-email%3Ftoken%3Dredacted/...">
  Verify Email Address
</a>
```

The visible text identifies the action, and the `href` is an AWS-style tracking
URL containing an encoded verification endpoint. The application must retain
the original `href`; it must not follow the link or replace it with a decoded
destination.

## Scope

- Extract verification links from HTML anchor elements.
- Return the original absolute `http`/`https` URL in verification query data.
- Support link-only messages and messages that contain both a code and a link.
- Show a link action in the top-level query result and each row's shortcut result.
- Keep verification URLs out of SQLite query history because they contain
  expiring, account-bound tokens.

Out of scope:

- Automatically opening or requesting the verification URL.
- Decoding, rewriting, or unwrapping tracking URLs.
- Adding configurable link rules to the existing code-format settings.
- Persisting verification URLs or adding a database migration.

## Approaches Considered

1. **Parse HTML anchors alongside code extraction (recommended).** Use the
   standard-library `HTMLParser` to collect anchor text and `href` values before
   HTML is stripped. This is focused, dependency-free, and preserves the exact
   link supplied by the mail provider.
2. **Add a configurable link-pattern editor.** This would support arbitrary
   providers but adds a second rule system before the current format editor has
   demonstrated a need for it.
3. **Treat the URL as the `code` field.** This minimizes API changes but makes
   code-specific validation, history, and UI semantics incorrect.

The first approach is selected because the provider format is structurally
identifiable and the required behavior is retrieval, not arbitrary matching.

## Link Identification

Create a focused extractor that receives raw HTML and returns the strongest
verification-link candidate, breaking ties by document order. A candidate is
strong when its anchor text or URL contains a verification action term such as
`verify`,
`confirm`, `activate`, or `complete`, with `token` treated as supporting
evidence. Footer/logo/unsubscribe links must not win merely because they are
anchors.

The extractor will:

1. Collect anchor text and raw `href` values with `HTMLParser`.
2. Trim whitespace and ignore empty links.
3. Accept only absolute `http` and `https` URLs.
4. Score action text and URL/path/query terms, preferring an action-labeled
   anchor over generic branding links.
5. Return the original `href` without network access or URL rewriting.

Malformed HTML should be tolerated. Invalid schemes such as `javascript:`,
`data:`, `mailto:`, and relative URLs are ignored.

## Query Data Flow

`CloudMailClient.query_verification_detail()` will inspect the raw HTML for a
link in the same email row used for code extraction. The returned detail keeps
the existing fields and adds:

```json
{
  "code": "",
  "verification_url": "https://tracking.example/...",
  "sender": "...",
  "subject": "...",
  "received_time": "..."
}
```

When both values exist, the numeric/code result keeps its current priority and
the link is included as an additional action. When only a link exists, the
query is considered a successful discovery but the server must not mark the
account as used: the user has not clicked the link yet. Link-only results are
not written to verification history.

The `/api/query-code` response adds `verification_url` with an empty string as
the backward-compatible default. Existing clients that ignore the field keep
working.

## User Interface

The existing top query result and row-level shortcut result will render a
button labeled `打开验证链接` when `verification_url` is present. The button:

- opens the original URL in a new tab/window only after the user clicks it;
- uses `target="_blank"`, `rel="noopener noreferrer"`, and a safe DOM property
  assignment rather than interpolating the URL into raw HTML;
- does not display the token-bearing URL as ordinary visible text.

Code results continue to use the current code display and history behavior.

## Error Handling And Security

- Link extraction failure is treated as “no link” and does not break code
  extraction.
- Only `http` and `https` links are exposed to the UI.
- The server never requests, resolves, or validates the remote link.
- Verification URLs are not logged, persisted, or copied into history records.
- Literal HTTP(S) URLs embedded in saved sender, subject, or received-time
  metadata are masked and remaining whitespace is normalized; the API response
  retains the original values for display. Automatic platform selection uses
  the sanitized sender and falls back to `验证码查询` when empty.
- The frontend treats the URL as an attribute value and keeps user-visible
  labels static to prevent HTML injection.
- A link-only result does not trigger account-used state changes.

## Testing

Backend tests will cover:

- extraction of an action-labeled link from HTML;
- extraction from an encoded tracking URL while preserving the original URL;
- rejection of footer, relative, `mailto:`, `javascript:`, and `data:` links;
- malformed HTML and missing `href` handling;
- link-only and code-plus-link query details;
- API response compatibility and no history/used-state side effects for a
  link-only result.

Frontend tests will cover:

- top-level link action rendering;
- row shortcut link action rendering;
- safe target/rel attributes and absence of raw URL interpolation;
- no link button when the response has no `verification_url`.

Browser QA will use a temporary test mailbox message with a redacted token and
will inspect the link without clicking it.
