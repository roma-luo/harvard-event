"""Harvard GSD — WordPress REST API.

The probe found `wp-json/wp/v2/gsd-events` and `gsd-exhibitions`, so this is a
structured API rather than a scrape. The one thing WordPress does not expose as
a field is the start time: it lives in the rendered content as
``<time datetime="2026-10-01T12:00:00-04:00">``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable

import httpx
from dateutil import parser as dateparser

from ..core.text import clean, extract_markers, split_series_prefix, truncate
from ..models import Event
from .base import Adapter, now_utc, to_eastern

_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"[^>]*>(.*?)</time>', re.I | re.S)
_META_PAIR_RE = re.compile(r"<dt[^>]*>(.*?)</dt>\s*((?:<dd[^>]*>.*?</dd>\s*)+)", re.I | re.S)
_DD_RE = re.compile(r"<dd[^>]*>(.*?)</dd>", re.I | re.S)
_HREF_RE = re.compile(r'href="([^"]+)"', re.I)
_SLUG_RE = re.compile(r"[a-z0-9-]+")
# "12 – 1:30 p.m. EDT" — the end time, which the <time> tag does not carry.
_END_TIME_RE = re.compile(
    r"[–—-]\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", re.I
)


def _meta_map(content_html: str) -> dict[str, list[str]]:
    """The hero-banner definition list: Event Location, Date & Time, Host, ..."""
    out: dict[str, list[str]] = {}
    for match in _META_PAIR_RE.finditer(content_html):
        label = clean(match.group(1)).rstrip(":").lower()
        values = [clean(dd) for dd in _DD_RE.findall(match.group(2))]
        out.setdefault(label, []).extend(v for v in values if v)
    return out


def _slugs(class_list: Iterable[str], prefix: str) -> list[str]:
    out = []
    for entry in class_list or []:
        if entry.startswith(prefix):
            out.append(entry[len(prefix):].replace("-", " ").strip())
    return out


class GsdAdapter(Adapter):
    """Reads both `gsd-events` and `gsd-exhibitions`."""

    type_name = "gsd"

    BASE = "https://www.gsd.harvard.edu/wp-json/wp/v2"
    ADDRESS = "48 Quincy Street, Cambridge, MA 02138"

    def fetch(self, days: int) -> list[Event]:
        horizon = now_utc() + timedelta(days=days + 1)
        floor = now_utc() - timedelta(days=1)
        events: list[Event] = []
        for post_type, kind_default in (("gsd-events", "lecture"), ("gsd-exhibitions", "exhibition")):
            for post in self._paged(post_type):
                event = self._to_event(post, kind_default)
                if event is None:
                    continue
                if event.kind == "exhibition":
                    # An exhibition that is currently running still counts even
                    # though it started before the window.
                    if event.end and event.end < floor:
                        continue
                    if event.start > horizon:
                        continue
                elif not (floor <= event.start <= horizon):
                    continue
                events.append(event)
        return events

    def _paged(self, post_type: str, per_page: int = 50, max_pages: int = 6):
        for page in range(1, max_pages + 1):
            try:
                resp = self.fetcher.get(
                    f"{self.BASE}/{post_type}",
                    params={"per_page": per_page, "page": page, "orderby": "date", "order": "desc"},
                )
                if resp.status_code == 400:
                    # WordPress returns 400 once you page past the end.
                    return
                resp.raise_for_status()
                batch = resp.json()
            except (httpx.HTTPError, ValueError):
                if page == 1:
                    raise
                return
            if not batch:
                return
            yield from batch
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if page >= total_pages:
                return

    def _to_event(self, post: dict[str, Any], kind_default: str) -> Event | None:
        content = (post.get("content") or {}).get("rendered") or ""
        times = _TIME_RE.findall(content)
        if not times:
            return None
        try:
            start = to_eastern(dateparser.parse(times[0][0]))
        except (ValueError, TypeError):
            return None

        end: datetime | None = None
        if len(times) > 1:
            try:
                candidate = to_eastern(dateparser.parse(times[1][0]))
                if candidate > start:
                    end = candidate
            except (ValueError, TypeError):
                end = None
        if end is None:
            end = self._end_from_label(start, clean(times[0][1]))

        meta = _meta_map(content)
        class_list = post.get("class_list") or []

        title_raw = clean((post.get("title") or {}).get("rendered") or "")
        title, marker = extract_markers(title_raw)
        # GSD wraps the series in <span class="event-title-name"> inside the
        # title, which `clean` flattens into a prefix; split it back out.
        title, series = split_series_prefix(title)
        series_slugs = _slugs(class_list, "event_series-") or _slugs(
            class_list, "public_lecture_series-"
        )
        if not series and series_slugs:
            series = series_slugs[0]

        kinds = _slugs(class_list, "event_type-")
        kind = self.mapper.map_kind(kinds) if kinds else kind_default
        if kind == "other":
            kind = kind_default

        location = None
        for label in ("event location", "location", "venue"):
            if meta.get(label):
                location = meta[label][0]
                break

        registration_url = None
        for match in _META_PAIR_RE.finditer(content):
            if "event link" in clean(match.group(1)).lower():
                hrefs = _HREF_RE.findall(match.group(2))
                if hrefs:
                    registration_url = hrefs[0]
                break

        speaker = None
        for label in ("lecturer", "speaker", "speakers", "presenter"):
            if meta.get(label):
                speaker = ", ".join(meta[label])[:160]
                break

        # GSD writes access in plain English in the meta block.
        blob = " ".join(v for vals in meta.values() for v in vals).lower()
        if "open to the public" in blob or "free and open" in blob:
            access = "open"
        elif "harvard id" in blob or "gsd community" in blob or "hu id" in blob:
            access = "check"
        elif "invitation" in blob or "invite only" in blob:
            access = "restricted"
        else:
            access = "open" if post.get("is_public_program") else "check"

        description = clean((post.get("excerpt") or {}).get("rendered") or "")
        if not description:
            description = clean((post.get("yoast_head_json") or {}).get("description") or "")

        event = Event(
            uid=self.make_uid(post.get("id") or post.get("slug")),
            source=self.source_id,
            title=title or title_raw,
            speaker=speaker,
            series=series,
            start=start,
            end=end,
            all_day=False,
            location=location,
            address=self.ADDRESS,
            campus=self.config.campus or "cambridge_harvard",
            is_virtual="online" in blob or "zoom" in blob,
            url=post.get("link") or "",
            registration_url=registration_url,
            kind=kind,
            access=access,
            units=_slugs(class_list, "department-") or ["GSD"],
            topics=sorted(set(_slugs(class_list, "event_series-") + _slugs(class_list, "department-"))),
            description=truncate(description, 2000),
            raw_facets={
                "class_list": class_list,
                "meta": meta,
                "is_public_program": post.get("is_public_program"),
                "post_type": post.get("type"),
                "time_labels": [clean(t[1]) for t in times[:2]],
            },
            fetched_at=now_utc(),
            cancelled_marker=marker,
        )
        if marker in {"CANCELLED", "POSTPONED"}:
            event.status = "CANCELLED"
        return event

    @staticmethod
    def _end_from_label(start: datetime, label: str) -> datetime | None:
        """Recover the end time from "Oct. 1, 2026 12 – 1:30 p.m. EDT"."""
        match = _END_TIME_RE.search(label)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3).replace(".", "").lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        end = start.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if end <= start:
            end += timedelta(days=1)
        if end - start > timedelta(hours=12):
            return None
        return end
