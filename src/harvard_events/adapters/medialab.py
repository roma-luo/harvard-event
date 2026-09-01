"""MIT Media Lab.

The probe confirmed there is no RSS (both feed paths 404) but the events index
is plain server-rendered HTML with stable class names, so this is a small,
well-behaved scrape. Detail pages are fetched only for events that pass the
list-level window filter, to keep the request count low.

Appendix B: Member Meeting / Horizons style events are sponsor-only regardless
of what the page says, so they are forced to ``restricted`` in the taxonomy
overrides rather than being special-cased here.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ..core.text import clean, extract_markers, split_series_prefix, truncate
from ..models import Event
from ..taxonomy.mapper import apply_overrides
from .base import Adapter, now_utc, to_eastern

INDEX_URL = "https://www.media.mit.edu/events/"
BASE = "https://www.media.mit.edu"
ADDRESS = "75 Amherst Street, Cambridge, MA 02139"

_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)


def _text(node: Any) -> str:
    return clean(node.get_text(" ", strip=True)) if node else ""


def _combine(day: str, time_text: str) -> datetime | None:
    """"September 3, 2026" + "4:00pm" -> aware datetime."""
    if not day:
        return None
    match = _TIME_RE.search(time_text or "")
    stamp = day
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if match.group(3).lower() == "pm" and hour != 12:
            hour += 12
        elif match.group(3).lower() == "am" and hour == 12:
            hour = 0
        stamp = f"{day} {hour:02d}:{minute:02d}"
    try:
        return to_eastern(dateparser.parse(stamp))
    except (ValueError, TypeError, OverflowError):
        return None


class MediaLabAdapter(Adapter):
    type_name = "medialab"

    def fetch(self, days: int) -> list[Event]:
        if not self.fetcher.allowed(INDEX_URL):
            raise PermissionError(f"robots.txt disallows {INDEX_URL}")
        soup = BeautifulSoup(self.fetcher.get_text(INDEX_URL), "lxml")
        horizon = now_utc() + timedelta(days=days + 1)
        floor = now_utc() - timedelta(days=1)

        out: list[Event] = []
        overrides = self.mapper.spec.get("overrides", [])
        for card in soup.select("div[data-href]"):
            href = card.get("data-href") or ""
            if "/events/" not in href:
                continue
            event = self._from_card(card, href)
            if event is None:
                continue
            if not (floor <= event.start <= horizon):
                continue
            out.append(apply_overrides(event, overrides))
        return out

    def _from_card(self, card: Any, href: str) -> Event | None:
        title_raw = _text(card.select_one(".module-title"))
        if not title_raw:
            return None
        start_day = _text(card.select_one(".event-start-date"))
        end_day = _text(card.select_one(".event-end-date"))
        start_time = _text(card.select_one(".event-start-time"))
        end_time = _text(card.select_one(".event-end-time"))

        start = _combine(start_day, start_time)
        if start is None:
            return None
        end = _combine(end_day or start_day, end_time)
        if end and end <= start:
            end = None

        title, marker = extract_markers(title_raw)
        title, series = split_series_prefix(title)
        excerpt = _text(card.select_one(".module-excerpt"))

        slug = href.strip("/").split("/")[-1]
        url = href if href.startswith("http") else BASE + href

        multi_day = bool(end_day) and end_day != start_day
        kind = self.mapper.kind_from_title(f"{title_raw} {series or ''}", default="lecture")

        event = Event(
            uid=self.make_uid(slug),
            source=self.source_id,
            title=title or title_raw,
            speaker=None,
            series=series,
            start=start,
            end=end,
            all_day=multi_day and not start_time,
            location="MIT Media Lab (E14)",
            address=ADDRESS,
            campus=self.config.campus or "cambridge_mit",
            is_virtual="online" in title_raw.lower() or "virtual" in excerpt.lower(),
            url=url,
            registration_url=None,
            kind=kind,
            access="check",
            units=["MIT Media Lab"],
            topics=[],
            description=truncate(excerpt, 2000),
            raw_facets={
                "slug": slug,
                "eyebrow": _text(card.select_one(".module-eyebrow-type")),
                "start_date_text": start_day,
                "end_date_text": end_day,
                "start_time_text": start_time,
                "end_time_text": end_time,
            },
            fetched_at=now_utc(),
            cancelled_marker=marker,
        )
        if marker in {"CANCELLED", "POSTPONED"}:
            event.status = "CANCELLED"
        return event
