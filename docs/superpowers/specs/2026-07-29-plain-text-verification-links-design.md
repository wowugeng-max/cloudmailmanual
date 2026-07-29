# Plain-Text Verification Link Recognition Design

## Context

The verification-link feature currently extracts candidates only from HTML
`<a href="...">` elements. Some activation emails instead show the complete
verification URL directly in the message body. The URL may contain a long
JWT-like token and additional query parameters, while the surrounding copy
contains language such as "Activate your account".

The existing UI, API response, history behavior, and account-used semantics
already support a returned `verification_url`. This change is limited to
finding that URL reliably.

## Goals

- Recognize absolute HTTP(S) verification URLs in:
  - HTML anchor `href` attributes.
  - Visible HTML body text, including messages with no anchor element.
  - The message's plain-text body.
- Support long, token-bearing URLs without truncating or decoding them.
- Use the existing action vocabulary: `verify`, `confirm`, `activate`, and
  `complete`.
- Allow nearby visible copy to provide action evidence for a generic URL.
- Preserve the existing link-only and code-plus-link API behavior.
- Prevent opaque HTTP(S) URL tokens from becoming verification-code matches
  while preserving real codes elsewhere in the message body.
- Avoid false positives from ordinary navigation, privacy, preference, and
  unsubscribe links.

## Non-Goals

- Opening or requesting a discovered URL.
- Decoding tracking redirects, JWTs, query values, or percent escapes.
- Persisting verification URLs or tokens.
- Reconstructing URLs across whitespace or MIME line breaks.
- Adding Webmail launch, credential filling, or automatic login behavior.
- Making link-recognition keywords configurable in this change.

## Public Interface

Keep the existing service function and add an optional plain-text argument:

```python
def extract_verification_link(
    raw_html: str,
    raw_text: str = "",
) -> Optional[str]:
    ...
```

Existing callers that pass only HTML remain compatible. `CloudMailClient`
passes both the HTML and plain-text message bodies.

The service also exposes visible HTML text extraction:

```python
def extract_visible_html_text(raw_html: str) -> str:
    ...
```

This helper uses stdlib `HTMLParser` with character-reference conversion and
collects only real `handle_data()` output. It excludes `head`, `script`,
`style`, and `template` content and never scans attributes. A self-closing form
of any invisible tag is treated conservatively as an opening tag and keeps
content hidden until a matching end tag or EOF. There is no raw HTML span
mapping or whole-document `html.unescape()` step.

The service also exports a shared body-masking helper:

```python
def mask_http_urls(value: str) -> str:
    ...
```

It replaces every matched HTTP(S) URL span with equal-length spaces so offsets
and surrounding text remain stable. Empty strings are returned unchanged;
non-string inputs return an empty string.

## Candidate Collection

The parser produces candidates from three sources in deterministic order:

1. Anchor `href` values and their visible anchor labels.
2. URL-shaped strings in visible HTML text.
3. URL-shaped strings in the plain-text message body.

The HTML parser ignores `head`, `script`, `style`, and `template` content. It
collects decoded visible text only from `handle_data()` for bare-URL scanning;
attribute values never become visible evidence. Anchor candidates and
bare-text candidates remain separate occurrences even when they have the same
exact URL, because each occurrence may have different visible text or nearby
context. Invisible elements are tracked as a tag stack. A closing invisible
tag exits hidden state only when it matches the current stack top; mismatched
closing tags are ignored so malformed markup cannot expose hidden text or
links.

Bare URLs are recognized with a bounded, linear regular expression beginning
with `http://` or `https://` and ending at whitespace, quotes, or markup
delimiters. Candidate cleanup may remove only common sentence punctuation and
unmatched closing brackets at the end. It must not alter query parameters,
fragments, percent escapes, JWT-like values, or internal punctuation. Closing
brackets are counted in one forward pass and trimmed in one backward pass with
at most one final slice. Trimming stops as soon as the final closing bracket is
balanced, preserving the existing conservative behavior.

Before nearby context is sliced, every literal URL match in plain text or
parser-produced visible HTML text is replaced with equal-length spaces in a
masked copy. This preserves character positions while ensuring neither the
current URL nor any neighboring URL can contribute action terms as visible
text evidence.

HTML character references in visible text are interpreted as the user sees
them, so `&amp;` becomes `&`. Anchor `href` values retain their exact
parser-provided value from validation through return. Empty values are skipped,
but surrounding whitespace and control characters are never trimmed; they make
the complete candidate invalid. No additional URL decoding is performed.

## Validation And Scoring

Every candidate uses the existing absolute-URL validation:

- Scheme must be `http` or `https`.
- Hostname must be present, contain no literal backslash, and have no empty
  interior labels such as `example..test`.
- An authority beginning with `[` must contain exactly one matching bracket
  pair. Its bracketed host must be a valid IPv6 address, including supported
  zone identifiers, or a valid RFC IPvFuture literal. Bracketed DNS names and
  IPv4 addresses are rejected.
- After the unique `]` in a bracketed authority, the remaining netloc must be
  empty or exactly `:` followed by a non-empty port accepted by `parsed.port`.
  Text suffixes and any additional `[` or `]` characters are rejected.
- A non-bracketed authority rejects any `[` or `]` character and any hostname
  containing `:`; ordinary DNS-label validation otherwise remains minimal.
- An explicit empty port marker is rejected. Accessing `parsed.port` continues
  to reject non-numeric and out-of-range ports while ordinary ports remain
  valid.
- Embedded username/password values are rejected.
- Whitespace and control characters anywhere in the original candidate are
  rejected without trimming.
- Relative, `javascript:`, `data:`, and malformed URLs are rejected.

The existing score remains the basis for selection:

- Action terms in visible anchor text or nearby body text have the strongest
  weight.
- Action terms in the URL path, non-opaque parameter names, or explicit action
  parameter values provide URL evidence.
- Support terms such as `token`, `verification`, and `email` add confidence but
  cannot qualify a candidate by themselves.
- Footer terms reduce a candidate's score.

For a bare URL, the candidate's text evidence includes at most 160 visible
characters before and after the URL in the same HTML or plain-text body. This
allows copy such as "Activate your account" to qualify a generic token URL
without treating every token-bearing URL as a verification action.

Occurrences with the same `href` but different visible text or nearby context
are validated and scored independently. Exact duplicate `(href, text)`
candidates are skipped. Within one extraction call, absolute-URL validation and
parsed URL evidence are cached by `href`, so repeated contexts reuse URL work
without sharing their text score.

The highest-scoring candidate wins, including when multiple occurrences have
the same `href`. Ties retain the first candidate in the collection order
defined above. A URL containing `verify-email` in its path qualifies even when
its visible label is the URL itself.

## Client Integration

For each message, `CloudMailClient.query_verification_detail()` masks plain
subject and plain text directly and parses HTML into decoded visible text
before masking:

```python
code_subject = mask_http_urls(subject)
code_text = mask_http_urls(text)
visible_html = extract_visible_html_text(html)
code_html = mask_http_urls(visible_html)
```

`CloudMailClient.extract_verification_code()` adds a default-compatible
`content_is_plain_text=False` parameter. Existing callers retain the original
HTML-cleaning behavior; parser-produced HTML text and the message's plain-text
body pass `content_is_plain_text=True`, so visible literals such as
`<ABC123>` are not mistaken for tags and removed.

The masked subject is computed once and reused for both subject passes, while
the original subject is retained for the API response. Body extraction stays
lazy and keeps this exact order: masked-subject non-digits, masked-subject
digits, plain-text non-digits, visible-HTML non-digits, plain-text digits,
visible-HTML digits. Visible HTML is not parsed when the plain-text non-digit
pass succeeds. This prevents values such as `token=ABC123` inside an HTTP(S)
URL from winning as an OTP while preserving a real code such as `654321`
outside the URL.

Link extraction continues to receive the original, untouched bodies:

```python
verification_url = extract_verification_link(html, text) or ""
```

Code extraction order remains unchanged. A link-only message still returns an
empty `code`, is not saved to verification history, and leaves the account
unused. A code-plus-link message still saves code metadata and marks the
account used. Before history persistence, literal HTTP(S) URLs in the subject
are replaced with spaces and whitespace is normalized; the API response still
returns the original subject.

No database schema or UI contract changes are required.

## Security And Privacy

- Never request, resolve, follow, log, or persist a candidate URL.
- Never decode redirect targets or opaque token values.
- Keep token-bearing URLs out of exception messages and test output.
- Use synthetic redacted tokens in tests rather than real mailbox links.
- Continue assigning returned links only through the UI anchor's `href`
  property with `target="_blank"` and `rel="noopener noreferrer"`.

## Error Handling

Malformed HTML, malformed URLs, invalid ports, and non-string inputs are
ignored without aborting the mailbox query. Expected parser input errors return
no link and do not affect verification-code extraction; unexpected runtime or
programming errors continue to propagate so defects are not silently hidden.

## Test Strategy

Add focused service and client tests for:

- A visible HTML bare URL matching the activation-email format, with a long
  synthetic token and callback query parameter.
- A plain-text-only verification URL.
- An anchor whose visible label is the full URL.
- A generic token URL qualified by nearby "activate" or "confirm" copy.
- The same `href` in multiple occurrences, with the strongest occurrence
  context determining whether it qualifies.
- Repeated opaque URLs not becoming action text for one another.
- Exact duplicate candidate evidence being scored once, with validation and
  parsed URL evidence cached once per `href`.
- Multiple candidates where the strongest action link wins.
- URLs in `script`, `style`, and `template` content being ignored.
- Ordinary, footer, token-only, relative, credential-bearing, malformed, and
  non-HTTP(S) candidates being rejected.
- Exact preservation of the selected URL and absence of network calls.
- `CloudMailClient` passing both body representations while preserving
  link-only and code-plus-link behavior.
- Plain-text and visible-HTML URL tokens not being returned as verification
  codes.
- A real verification code outside a URL remaining extractable when the same
  body also contains an opaque alphanumeric URL token.
- An entity-encoded visible `<ABC123>` code remaining extractable beside an
  entity-encoded verification URL.
- Attribute values and `head`, `script`, `style`, and `template` content,
  including encoded closing-tag text, never leaking hidden codes.
- Nested and mismatched invisible closing tags never exposing hidden text,
  anchor candidates, or verification codes.
- Anchor `href` values with encoded newlines, tabs, or surrounding spaces being
  rejected without normalization, while empty hrefs are skipped.
- Empty ports, consecutive hostname dots, literal host backslashes, and
  out-of-range ports being rejected while IPv6 and ordinary ports remain valid.
- Bracketed IPv6 authorities with `]evil` or additional `]` suffixes being
  rejected while no-port and valid-port forms remain accepted.
- A patch-based contract proving visible HTML parsing is deferred when the
  plain-text non-digit pass succeeds.

Run the focused parser/client suites, the complete Python suite, JavaScript UI
checks, and the existing token-persistence scan before merging to `main`.
