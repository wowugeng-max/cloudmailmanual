from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import SplitResult, urlsplit


__all__ = [
    "extract_verification_link",
    "extract_visible_html_text",
    "mask_http_urls",
]


_ACTION_TERMS = ("verify", "confirm", "activate", "complete")
_SUPPORT_TERMS = ("token", "verification", "email")
_FOOTER_TERMS = ("unsubscribe", "privacy", "preferences", "terms")
_INVISIBLE_TAGS = {"head", "script", "style", "template"}
_ACTION_VALUE_KEYS = {
    "action",
    "mode",
    "step",
    "operation",
    "intent",
    "type",
}
_OPAQUE_VALUE_KEYS = {
    "token",
    "signature",
    "sig",
    "code",
    "key",
    "hash",
    "state",
    "auth",
}

_PERCENT_ESCAPE_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
_ENCODED_QUERY_MARKER_PATTERN = re.compile(r"%3F", re.IGNORECASE)
_BARE_HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TEXT_CONTEXT_RADIUS = 160
_TRAILING_SENTENCE_PUNCTUATION = ".,!"
_CLOSING_BRACKETS = {")": "(", "]": "[", "}": "{"}

_TERM_PATTERNS = {
    term: re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
    )
    for term in (*_ACTION_TERMS, *_SUPPORT_TERMS, *_FOOTER_TERMS)
}

_TEXT_ACTION_WEIGHT = 100
_URL_ACTION_WEIGHT = 10
_SUPPORT_WEIGHT = 1
_FOOTER_PENALTY = 2


@dataclass(frozen=True)
class _Anchor:
    href: str
    text: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[_Anchor] = []
        self.visible_text_parts: List[str] = []
        self._href: Optional[str] = None
        self._text_parts: List[str] = []
        self._invisible_tags: List[str] = []

    def _finish_anchor(self) -> None:
        if self._href is not None:
            self.anchors.append(_Anchor(self._href, "".join(self._text_parts)))
        self._href = None
        self._text_parts = []

    @staticmethod
    def _href_from_attrs(
        attrs: List[Tuple[str, Optional[str]]],
    ) -> Optional[str]:
        for name, value in attrs:
            if name.casefold() == "href":
                return value
        return None

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in _INVISIBLE_TAGS:
            self._invisible_tags.append(normalized_tag)
            return
        if self._invisible_tags or normalized_tag != "a":
            return
        self._finish_anchor()
        self._href = self._href_from_attrs(attrs)

    def handle_startendtag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in _INVISIBLE_TAGS or self._invisible_tags:
            return
        if normalized_tag != "a":
            return
        self._finish_anchor()
        href = self._href_from_attrs(attrs)
        if href is not None:
            self.anchors.append(_Anchor(href, ""))

    def handle_data(self, data: str) -> None:
        if self._invisible_tags:
            return
        self.visible_text_parts.append(data)
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in _INVISIBLE_TAGS:
            if self._invisible_tags and self._invisible_tags[-1] == normalized_tag:
                self._invisible_tags.pop()
            return
        if not self._invisible_tags and normalized_tag == "a":
            self._finish_anchor()

    def close(self) -> None:
        super().close()
        self._finish_anchor()


def _parse_html(raw_html: str) -> _AnchorParser:
    parser = _AnchorParser()
    parser.feed(raw_html)
    parser.close()
    return parser


def extract_visible_html_text(raw_html: str) -> str:
    if not isinstance(raw_html, str) or not raw_html:
        return ""

    try:
        parser = _parse_html(raw_html)
    except (TypeError, ValueError):
        return ""
    return " ".join(parser.visible_text_parts)


def _has_forbidden_url_characters(value: str) -> bool:
    return any(
        character.isspace()
        or ord(character) < 0x20
        or ord(character) == 0x7F
        for character in value
    )


def _has_valid_host_shape(
    parsed: SplitResult,
    hostname: str,
    port: Optional[int],
) -> bool:
    if parsed.netloc.endswith(":") or "\\" in parsed.netloc:
        return False
    if ":" in hostname:
        if not parsed.netloc.startswith("["):
            return False
        closing_bracket = parsed.netloc.find("]")
        suffix = parsed.netloc[closing_bracket + 1:]
        return not suffix or (
            suffix.startswith(":")
            and len(suffix) > 1
            and port is not None
        )

    labels = hostname.split(".")
    if labels and not labels[-1]:
        labels = labels[:-1]
    return bool(labels) and all(labels)


def _is_absolute_http_url(value: str) -> bool:
    if not isinstance(value, str) or not value or _has_forbidden_url_characters(value):
        return False

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except (TypeError, ValueError):
        return False

    return (
        parsed.scheme.casefold() in {"http", "https"}
        and bool(parsed.netloc)
        and bool(hostname)
        and bool(hostname.strip("."))
        and _has_valid_host_shape(parsed, hostname, port)
        and username is None
        and password is None
    )


def _count_terms(value: str, terms: Tuple[str, ...]) -> int:
    normalized_value = value.casefold()
    return sum(
        _TERM_PATTERNS[term].search(normalized_value) is not None
        for term in terms
    )


def _count_terms_in_values(values: Tuple[str, ...], terms: Tuple[str, ...]) -> int:
    return sum(
        any(_TERM_PATTERNS[term].search(value.casefold()) for value in values)
        for term in terms
    )


def _parameter_evidence(raw_value: str) -> Tuple[str, ...]:
    evidence: List[str] = []
    for field in raw_value.split("&"):
        name, separator, value = field.partition("=")
        evidence.append(name)
        if separator:
            normalized_name = name.casefold()
            if normalized_name in _OPAQUE_VALUE_KEYS:
                continue
            if normalized_name in _ACTION_VALUE_KEYS:
                evidence.append(value)
    return tuple(evidence)


def _url_evidence(parsed: SplitResult) -> Tuple[str, ...]:
    path = parsed.path
    encoded_query_marker = _ENCODED_QUERY_MARKER_PATTERN.search(path)
    if encoded_query_marker:
        path = path[: encoded_query_marker.start()]
    path = _PERCENT_ESCAPE_PATTERN.sub(" ", path)

    return (
        path,
        *_parameter_evidence(parsed.query),
        *_parameter_evidence(parsed.fragment),
    )


def _trim_bare_url_candidate(value: str) -> str:
    trimmed = value.rstrip(_TRAILING_SENTENCE_PUNCTUATION)
    while trimmed and trimmed[-1] in _CLOSING_BRACKETS:
        closing = trimmed[-1]
        opening = _CLOSING_BRACKETS[closing]
        if trimmed.count(opening) >= trimmed.count(closing):
            break
        trimmed = trimmed[:-1]
    return trimmed


def _literal_http_url_spans(value: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    for match in _BARE_HTTP_URL_PATTERN.finditer(value):
        href = _trim_bare_url_candidate(match.group(0))
        if href:
            spans.append((match.start(), match.start() + len(href)))
    return spans


def mask_http_urls(value: str) -> str:
    if not isinstance(value, str):
        return ""
    if not value:
        return value

    spans = _literal_http_url_spans(value)
    if not spans:
        return value

    masked_parts: List[str] = []
    previous_end = 0
    for start, end in spans:
        masked_parts.append(value[previous_end:start])
        masked_parts.append(" " * (end - start))
        previous_end = end
    masked_parts.append(value[previous_end:])
    return "".join(masked_parts)


def _bare_url_candidates(value: str) -> List[_Anchor]:
    matches = list(_BARE_HTTP_URL_PATTERN.finditer(value))
    if not matches:
        return []

    masked_value = mask_http_urls(value)

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


def extract_verification_link(
    raw_html: str,
    raw_text: str = "",
) -> Optional[str]:
    if not isinstance(raw_html, str) or not isinstance(raw_text, str):
        return None
    if not raw_html and not raw_text:
        return None

    if raw_html:
        try:
            parser = _parse_html(raw_html)
        except (TypeError, ValueError):
            return None
    else:
        parser = _AnchorParser()

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
