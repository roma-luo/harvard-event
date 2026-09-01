"""Harvard Art Museums.

The probe found the whole calendar embedded in the page as
``var initialEvents = [].concat([...])`` — a complete JSON payload with ids,
dates and types. That is far better than scraping cards, so this adapter reads
the payload directly.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from dateutil import parser as dateparser

from ..core.text import clean, extract_markers, split_series_prefix, truncate
from ..models import Event
from .base import Adapter, now_utc, to_eastern

CALENDAR_URL = "https://harvardartmuseums.org/calendar"
EXHIBITIONS_URL = "https://harvardartmuseums.org/exhibitions"
ADDRESS = "32 Quincy Street, Cambridge, MA 02138"


def extract_initial_events(html: str) -> list[dict[str, Any]]:
    """Pull every JSON array out of the `initialEvents` concat expression."""
    marker = html.find("var initialEvents")
    if marker == -1:
        return []
    open_paren = html.find(".concat(", marker)
    if open_paren == -1:
        return []
    cursor = open_paren + len(".concat(") - 1
    depth = 0
    end = None
    for i in range(cursor, len(html)):
        if html[i] == "(":
            depth += 1
        elif html[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        return []
    body = html[cursor + 1 : end]

    out: list[dict[str, Any]] = []
    depth = 0
    start = None
    for i, char in enumerate(body):
        if char == "[":
            if depth == 0:
                start = i
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    parsed = json.loads(body[start : i + 1])
                except json.JSONDecodeError:
                    parsed = []
                if isinstance(parsed, list):
                    out.extend(p for p in parsed if isinstance(p, dict))
    return out


class ArtMuseumsAdapter(Adapter):
    type_name = "artmuseums"

    def fetch(self, days: int) -> list[Event]:
        html = self.fetcher.get_text(CALENDAR_URL)
        raw_events = extract_initial_events(html)
        horizon = now_utc() + timedelta(days=days + 1)
        floor = now_utc() - timedelta(days=1)

        out: list[Event] = []
        for raw in raw_events:
            if raw.get("enabled") is False:
                continue
            event = self._to_event(raw)
            if event is None:
                continue
            if event.kind == "exhibition":
                if event.end and event.end < floor:
                    continue
                if event.start > horizon:
                    continue
            elif not (floor <= event.start <= horizon):
                continue
            out.append(event)
        out.extend(self._fetch_exhibitions(horizon))
        return out

    def _fetch_exhibitions(self, horizon) -> list[Event]:
        """The /exhibitions listing: current and upcoming runs with date ranges.

        The calendar payload rarely carries exhibition entries, so without this
        the weekly email's exhibition section would almost always be empty.
        Rows carry a status word; "Past" ones are skipped.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(self.fetcher.get_text(EXHIBITIONS_URL), "lxml")
        out: list[Event] = []
        for row in soup.select("article:has(span.exhibition-row__type)"):
            status = clean(row.select_one("span.exhibition-row__type").get_text())
            if status.lower() == "past":
                continue
            title_el = row.select_one("h2.exhibition-row__title")
            link_el = row.select_one("a[href*='/exhibitions/']")
            time_el = row.select_one("p.exhibition-row__meta time")
            if not (title_el and link_el and time_el):
                continue
            dates = re.findall(
                r"[A-Z][a-z]+ \d{1,2}, \d{4}", clean(time_el.get_text())
            )
            if not dates:
                continue
            try:
                start = to_eastern(dateparser.parse(dates[0]))
                end = (
                    to_eastern(dateparser.parse(dates[1])).replace(hour=23, minute=59)
                    if len(dates) > 1
                    else None
                )
            except (ValueError, TypeError):
                continue
            if status.lower() == "upcoming" and start > horizon:
                continue
            href = link_el.get("href") or ""
            match = re.search(r"/exhibitions/(\d+)/", href)
            url = href if href.startswith("http") else f"https://harvardartmuseums.org{href}"
            meta = row.select_one("p.exhibition-row__meta")
            venue = ""
            if meta:
                bits = [clean(b) for b in meta.stripped_strings]
                venue = bits[1] if len(bits) > 1 else ""
            desc_el = row.select_one("a p:last-of-type")
            out.append(
                Event(
                    uid=self.make_uid(match.group(1) if match else url),
                    source=self.source_id,
                    title=clean(title_el.get_text()),
                    start=start,
                    end=end,
                    all_day=True,
                    location=venue or "Harvard Art Museums",
                    address=ADDRESS,
                    campus=self.config.campus or "cambridge_harvard",
                    url=url,
                    kind="exhibition",
                    access="open",
                    units=["Harvard Art Museums"],
                    topics=["Exhibition"],
                    description=truncate(
                        clean(desc_el.get_text()) if desc_el else "", 2000
                    ),
                    raw_facets={"event_type": "Exhibition", "status": status},
                    fetched_at=now_utc(),
                )
            )
        return out

    def _to_event(self, raw: dict[str, Any]) -> Event | None:
        start_raw = raw.get("date")
        if not start_raw:
            return None
        try:
            start = to_eastern(dateparser.parse(start_raw))
        except (ValueError, TypeError):
            return None
        # The payload's seconds are an artefact of the CMS; the human-facing
        # start_time string is authoritative to the minute.
        start = start.replace(second=0, microsecond=0)

        end = None
        if raw.get("end_date"):
            try:
                candidate = to_eastern(dateparser.parse(raw["end_date"])).replace(
                    second=0, microsecond=0
                )
                if candidate > start:
                    end = candidate
            except (ValueError, TypeError):
                end = None

        title_raw = clean(raw.get("title") or raw.get("status_title") or "")
        title, marker = extract_markers(title_raw)
        title, series = split_series_prefix(title)

        event_type = clean(raw.get("event_type") or "")
        kind = self.mapper.map_kind([event_type]) if event_type else "other"
        # A multi-day entry with no distinct times is an exhibition run.
        if end and (end - start) > timedelta(days=2) and kind in {"other", "exhibition"}:
            kind = "exhibition"

        description = clean(raw.get("summary") or "") or clean(raw.get("description") or "")

        info_bits = " ".join(
            f"{clean(str(i.get('label')))} {clean(str(i.get('value')))}"
            for i in (raw.get("info") or [])
            if isinstance(i, dict)
        )
        blob = f"{description} {info_bits} {clean(raw.get('description') or '')}".lower()
        if "free event" in blob or "free and open" in blob or "no charge" in blob:
            access = "open"
        elif "members only" in blob or "invitation" in blob:
            access = "restricted"
        elif "registration required" in blob or "space is limited" in blob:
            access = "check"
        else:
            access = "open"

        is_virtual = "online" in title.lower() or "zoom" in blob or "virtual" in blob

        slug = raw.get("slug") or raw.get("id")
        url = raw.get("event_link") or f"{CALENDAR_URL}/{slug}"

        event = Event(
            uid=self.make_uid(raw.get("id") or slug),
            source=self.source_id,
            title=title or title_raw,
            speaker=None,
            series=series,
            start=start,
            end=end,
            all_day=kind == "exhibition",
            location=clean(raw.get("room") or "") or "Harvard Art Museums",
            address=", ".join(
                filter(
                    None,
                    [
                        clean(raw.get("address") or "") or "32 Quincy Street",
                        clean(raw.get("city") or "") or "Cambridge",
                        clean(raw.get("state") or "") or "MA",
                    ],
                )
            )
            or ADDRESS,
            campus=self.config.campus or "cambridge_harvard",
            is_virtual=is_virtual,
            url=url,
            registration_url=raw.get("outbound_link") or raw.get("shopify_url") or None,
            kind=kind,
            access=access,
            units=["Harvard Art Museums"],
            topics=[event_type] if event_type else [],
            description=truncate(description, 2000),
            raw_facets={
                "event_type": event_type,
                "type": raw.get("type"),
                "participation": raw.get("participation"),
                "start_time": raw.get("start_time"),
                "exhibition_id": raw.get("exhibition_id"),
                "info": raw.get("info") or [],
            },
            fetched_at=now_utc(),
            cancelled_marker=marker,
        )
        if marker in {"CANCELLED", "POSTPONED"}:
            event.status = "CANCELLED"
        return event
