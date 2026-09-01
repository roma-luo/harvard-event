"""Text normalization shared by keyword matching and cross-source dedup.

Every quirk handled here is one the plan calls out explicitly: HTML entities,
full-width punctuation, series prefixes glued to titles, all-caps titles, and
CANCELLED / POSTPONED markers.
"""

from __future__ import annotations

import html
import re
import unicodedata

# Series prefixes are separated from the real title by one of these.
_SPLIT_RE = re.compile(r"\s*(?:\|| -- | — | – |:)\s*")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

CANCEL_MARKERS = {
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "POSTPONED": "POSTPONED",
    "RESCHEDULED": "RESCHEDULED",
}
_MARKER_RE = re.compile(
    r"\b(" + "|".join(CANCEL_MARKERS) + r")\b[\s:：\-–—\*\[\]\(\)]*",
    re.IGNORECASE,
)

# Words that make a leading fragment a series name rather than a real title.
_SERIES_HINTS = re.compile(
    r"\b(series|seminar|colloquium|colloquia|lecture|lectures|talks?|"
    r"symposium|workshop|program|forum|conference|meeting|hours|"
    r"session|club|group|round ?table)\b",
    re.IGNORECASE,
)


def strip_html(value: str | None) -> str:
    """Tags out, entities unescaped, whitespace collapsed."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    # Unescape twice: some sources double-encode (&amp;#x27;).
    text = html.unescape(html.unescape(text))
    text = text.replace("\xa0", " ").replace("​", "")
    return _WS_RE.sub(" ", text).strip()


def normalize_unicode(value: str) -> str:
    """NFKC folds full-width punctuation and ligatures to ASCII-ish forms."""
    return unicodedata.normalize("NFKC", value)


def clean(value: str | None) -> str:
    """The standard cleanup applied to every string coming off an adapter."""
    return normalize_unicode(strip_html(value))


def extract_markers(title: str) -> tuple[str, str | None]:
    """Pull CANCELLED / POSTPONED / RESCHEDULED off a title.

    Returns ``(title_without_marker, marker or None)``.
    """
    found: str | None = None
    for match in _MARKER_RE.finditer(title):
        found = CANCEL_MARKERS[match.group(1).upper()]
        break
    if found is None:
        return title, None
    cleaned = _MARKER_RE.sub(" ", title)
    return _WS_RE.sub(" ", cleaned).strip(" -–—:|"), found


def split_series_prefix(title: str) -> tuple[str, str | None]:
    """Split ``"CSAIL Seminar Series | Real Title"`` into title and series.

    Only splits when the leading fragment actually looks like a series name and
    the remainder is substantial; otherwise a normal title with a colon (for
    example ``"Dataset Distillation: Fundamentals"``) would be mangled.
    """
    parts = _SPLIT_RE.split(title, maxsplit=1)
    if len(parts) != 2:
        return title, None
    head, tail = parts[0].strip(), parts[1].strip()
    if not head or not tail:
        return title, None
    if len(tail) < 8:
        return title, None
    if not _SERIES_HINTS.search(head):
        return title, None
    if len(head.split()) > 9:
        return title, None
    return tail, head


def is_all_caps(value: str) -> bool:
    """True when the string carries no meaningful case information.

    Acronym rules are case-sensitive, so an all-caps title must fall back to a
    case-insensitive match or every acronym would fire.
    """
    letters = [c for c in value if c.isalpha()]
    if len(letters) < 6:
        return False
    return sum(c.isupper() for c in letters) / len(letters) > 0.85


def normalize_for_match(value: str) -> str:
    """Fold hyphens and stray whitespace so term variants collapse to one form."""
    text = normalize_unicode(value)
    text = text.replace("‐", "-").replace("‑", "-")
    text = re.sub(r"[-‐‑–—_/]+", " ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    """The dedup key: lowercase, series prefix gone, punctuation gone."""
    text = clean(title)
    text, _ = extract_markers(text)
    text, _ = split_series_prefix(text)
    text = normalize_for_match(text).lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


_SPEAKER_RE = re.compile(
    r"\b(?:speaker|presenter|lecturer|with|featuring)\s*:?\s*"
    r"([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,3})"
)


def guess_speaker(*texts: str | None) -> str | None:
    """Best-effort speaker extraction for sources with no speaker field."""
    for text in texts:
        if not text:
            continue
        match = _SPEAKER_RE.search(clean(text))
        if match:
            name = match.group(1).strip(" .,;")
            if 1 < len(name.split()) <= 4:
                return name
    return None


def truncate(value: str, limit: int) -> str:
    text = clean(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
