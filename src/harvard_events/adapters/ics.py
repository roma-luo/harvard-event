"""Generic ICS adapter — covers CSAIL and the Loeb Library LibCal feed.

Both feeds carry a stable UID of their own, which is exactly what the plan asks
for: the aggregator's UID is derived from the source UID, never hashed from
title and time.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from icalendar import Calendar

from ..core.text import clean, extract_markers, split_series_prefix, truncate
from ..models import Event
from .base import Adapter, now_utc, to_eastern

_ZOOM_RE = re.compile(r"https?://[\w.-]*zoom\.us/\S+", re.I)
_URL_RE = re.compile(r"https?://\S+")
_SPEAKER_FIELD_RE = re.compile(
    r"Speaker\s*:\s*(.+?)(?=(?:Speaker Affiliation|Host|Abstract|Zoom|Title|$))",
    re.I | re.S,
)
_AFFIL_RE = re.compile(r"Speaker Affiliation\s*:\s*(.+?)(?=(?:Host|Abstract|Zoom|Title|$))", re.I | re.S)


def _as_datetime(value: Any) -> tuple[datetime | None, bool]:
    """icalendar hands back either a date (all-day) or a datetime."""
    if value is None:
        return None, False
    dt = getattr(value, "dt", value)
    if isinstance(dt, datetime):
        return to_eastern(dt), False
    if isinstance(dt, date):
        return to_eastern(datetime(dt.year, dt.month, dt.day)), True
    return None, False


class IcsAdapter(Adapter):
    type_name = "ics"

    def fetch(self, days: int) -> list[Event]:
        url = self.config.url or ""
        if not url:
            raise ValueError(f"source {self.source_id}: `url` is required for type ics")
        text = self.fetcher.get_text(url)
        cal = Calendar.from_ical(text)

        window_start = now_utc() - timedelta(days=1)
        window_end = now_utc() + timedelta(days=days + 1)
        out: list[Event] = []
        for component in cal.walk("VEVENT"):
            event = self._to_event(component)
            if event is None:
                continue
            if not (window_start <= event.start <= window_end):
                continue
            out.append(event)
        return out

    def _to_event(self, component: Any) -> Event | None:
        start, all_day = _as_datetime(component.get("DTSTART"))
        if start is None:
            return None
        end, _ = _as_datetime(component.get("DTEND"))

        raw_uid = str(component.get("UID") or "").strip()
        if not raw_uid:
            # No source UID at all: fall back to the URL, still not a content hash.
            raw_uid = str(component.get("URL") or "") or f"{start.isoformat()}"
        # Keep only the identifying part; the @domain suffix is redundant here.
        source_event_id = raw_uid.split("@")[0] or raw_uid

        title_raw = clean(str(component.get("SUMMARY") or ""))
        title, marker = extract_markers(title_raw)
        title, series = split_series_prefix(title)

        description = clean(str(component.get("DESCRIPTION") or ""))
        location = clean(str(component.get("LOCATION") or "")) or None
        categories = component.get("CATEGORIES")
        cat_values: list[str] = []
        if categories is not None:
            raw_cats = getattr(categories, "cats", None)
            if raw_cats:
                cat_values = [str(c) for c in raw_cats]
            else:
                cat_values = [c.strip() for c in str(categories).split(",") if c.strip()]

        speaker = None
        match = _SPEAKER_FIELD_RE.search(description)
        if match:
            speaker = clean(match.group(1))[:120] or None
            affil = _AFFIL_RE.search(description)
            if speaker and affil:
                speaker = f"{speaker}, {clean(affil.group(1))[:80]}"

        zoom = _ZOOM_RE.search(description) or _ZOOM_RE.search(
            str(component.get("URL") or "")
        )
        is_virtual = bool(zoom) or "online" in (location or "").lower()

        # CSAIL puts the real event page at the end of DESCRIPTION and a Zoom
        # link in URL; prefer a page on the source's own domain.
        page_url = str(component.get("URL") or "")
        options = self.config.options or {}
        home = options.get("event_url_contains")
        if home:
            candidates = [u for u in _URL_RE.findall(description) if home in u]
            if candidates:
                page_url = candidates[-1].rstrip(".,;")
        if not page_url:
            page_url = options.get("fallback_url", self.config.url or "")

        # CATEGORIES are kinds, not access levels: only map access when the
        # taxonomy actually defines access values, else every category would
        # be logged as unmapped noise.
        access = (
            self.mapper.map_access(cat_values, default=options.get("default_access", "check"))
            if self.mapper.has_access_map
            else options.get("default_access", "check")
        )
        # Appendix B: CSAIL keeps "private" events in the public feed; that is a
        # hint to check, not a reason to hide them.
        blob = f"{title_raw} {description}".lower()
        if "private" in cat_values or "private event" in blob:
            if access == "open":
                access = "check"

        event = Event(
            uid=self.make_uid(source_event_id),
            source=self.source_id,
            title=title or title_raw,
            speaker=speaker,
            series=series or (cat_values[0] if cat_values else None),
            start=start,
            end=end,
            all_day=all_day,
            location=location,
            address=options.get("address"),
            campus="online" if is_virtual and not location else self.config.campus,
            is_virtual=is_virtual,
            url=page_url,
            registration_url=options.get("registration_url"),
            kind=(
                self.mapper.map_kind(cat_values)
                if cat_values
                else self.mapper.kind_from_title(f"{title_raw} {series or ''}")
            ),
            access=access,
            units=list(options.get("units", [])),
            topics=cat_values,
            description=truncate(description, 2000),
            raw_facets={
                "categories": cat_values,
                "ics_uid": raw_uid,
                "ics_url": str(component.get("URL") or ""),
                "organizer": str(component.get("ORGANIZER") or ""),
                "status": str(component.get("STATUS") or ""),
            },
            fetched_at=now_utc(),
            cancelled_marker=marker,
        )
        if marker in {"CANCELLED", "POSTPONED"} or str(
            component.get("STATUS") or ""
        ).upper() == "CANCELLED":
            event.status = "CANCELLED"
        return event
