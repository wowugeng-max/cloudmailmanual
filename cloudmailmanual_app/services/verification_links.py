from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urlsplit


__all__ = ["extract_verification_link"]


_ACTION_TERMS = ("verify", "confirm", "activate", "complete")
_SUPPORT_TERMS = ("token", "verification", "email")
_FOOTER_TERMS = ("unsubscribe", "privacy", "preferences", "terms")

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
        self._href: Optional[str] = None
        self._text_parts: List[str] = []

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
        if tag.casefold() != "a":
            return
        self._finish_anchor()
        self._href = self._href_from_attrs(attrs)

    def handle_startendtag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        if tag.casefold() != "a":
            return
        self._finish_anchor()
        href = self._href_from_attrs(attrs)
        if href is not None:
            self.anchors.append(_Anchor(href, ""))

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a":
            self._finish_anchor()

    def close(self) -> None:
        super().close()
        self._finish_anchor()


def _is_absolute_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except (TypeError, ValueError):
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _count_terms(value: str, terms: Tuple[str, ...]) -> int:
    return sum(term in value for term in terms)


def _score(anchor: _Anchor) -> Optional[int]:
    text = anchor.text.casefold()
    href = anchor.href.casefold()
    action_text = _count_terms(text, _ACTION_TERMS)
    action_url = _count_terms(href, _ACTION_TERMS)
    if not action_text and not action_url:
        return None

    combined = f"{text} {href}"
    support = _count_terms(combined, _SUPPORT_TERMS)
    footer = _count_terms(combined, _FOOTER_TERMS)
    return (
        action_text * _TEXT_ACTION_WEIGHT
        + action_url * _URL_ACTION_WEIGHT
        + support * _SUPPORT_WEIGHT
        - footer * _FOOTER_PENALTY
    )


def extract_verification_link(raw_html: str) -> Optional[str]:
    if not raw_html:
        return None

    parser = _AnchorParser()
    try:
        parser.feed(raw_html)
        parser.close()
    except Exception:
        return None

    best_href: Optional[str] = None
    best_score: Optional[int] = None
    for anchor in parser.anchors:
        href = anchor.href.strip()
        if not href or not _is_absolute_http_url(href):
            continue

        score = _score(_Anchor(href, anchor.text))
        if score is not None and (best_score is None or score > best_score):
            best_href = href
            best_score = score

    return best_href
