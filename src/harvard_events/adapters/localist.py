"""Localist adapter — covers MIT, SEAS, HBS and any future Localist calendar.

Adding another Localist instance is a config change, not code: the facet group
keys differ per instance, so which group carries "type" or "audience" is read
from `config/taxonomy/<source_id>.yml` rather than hard-coded.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

import httpx
from dateutil import parser as dateparser

from ..core.text import clean, extract_markers, split_series_prefix, truncate
from ..models import Event
from .base import Adapter, now_utc, to_eastern

MAX_PAGES = 25
PAGE_SIZE = 100


def _facet_values(raw_filters: dict[str, Any], groups: Iterable[str]) -> list[str]:
    out: list[str] = []
    for group in groups:
        for entry in raw_filters.get(group) or []:
            if isinstance(entry, dict) and entry.get("name"):
                out.append(str(entry["name"]))
            elif isinstance(entry, str):
                out.append(entry)
    return out


def _all_facet_values(raw_filters: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for entries in raw_filters.values():
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("name"):
                    out.append(str(entry["name"]))
    return out


class LocalistAdapter(Adapter):
    type_name = "localist"

    def base_url(self) -> str:
        domain = (self.config.domain or "").strip("/")
        path = (self.config.path or "").strip("/")
        prefix = f"https://{domain}"
        if path:
            prefix = f"{prefix}/{path}"
        return f"{prefix}/api/2/events"

    def _params(self, days: int, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "days": days,
            "pp": PAGE_SIZE,
            "page": page,
            # Collapse repeating events server-side; the per-week cap in
            # core/dedupe.py is the second line of defence.
            "distinct": "true",
        }
        filters = self.config.filters or {}
        # Localist takes repeated keys for multi-value filters.
        if filters.get("event_types"):
            params["type"] = list(filters["event_types"])
        if filters.get("departments"):
            params["department"] = list(filters["departments"])
        if filters.get("group_id"):
            params["group_id"] = filters["group_id"]
        if filters.get("venue_id"):
            params["venue_id"] = filters["venue_id"]
        if filters.get("keywords"):
            params["keyword"] = list(filters["keywords"])
        return params

    def fetch(self, days: int) -> list[Event]:
        events: list[Event] = []
        page = 1
        seen_ids: set[int] = set()
        while page <= MAX_PAGES:
            try:
                resp = self.fetcher.get(self.base_url(), params=self._params(days, page))
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                if page == 1:
                    raise
                # A late page failing should not throw away what we already have.
                break
            wrappers = payload.get("events") or []
            for wrapper in wrappers:
                raw = wrapper.get("event") or {}
                if raw.get("id") in seen_ids:
                    continue
                seen_ids.add(raw.get("id"))
                events.extend(self._to_events(raw, days))
            paging = payload.get("page") or {}
            if page >= int(paging.get("total") or 1):
                break
            page += 1
        return events

    def _to_events(self, raw: dict[str, Any], days: int) -> list[Event]:
        """One Localist event can carry several instances; each becomes an Event."""
        instances = raw.get("event_instances") or []
        if not instances:
            return []
        horizon = now_utc() + timedelta(days=days + 1)
        out: list[Event] = []
        for wrapper in instances:
            inst = wrapper.get("event_instance") or wrapper
            start_raw = inst.get("start")
            if not start_raw:
                continue
            try:
                start = to_eastern(dateparser.parse(start_raw))
            except (ValueError, TypeError):
                continue
            if start > horizon:
                continue
            end = None
            if inst.get("end"):
                try:
                    end = to_eastern(dateparser.parse(inst["end"]))
                except (ValueError, TypeError):
                    end = None
            out.append(self._build(raw, inst, start, end))
        return out

    def _build(
        self,
        raw: dict[str, Any],
        inst: dict[str, Any],
        start: datetime,
        end: datetime | None,
    ) -> Event:
        filters = raw.get("filters") or {}
        title_raw = clean(raw.get("title") or "")
        title, marker = extract_markers(title_raw)
        title, series = split_series_prefix(title)

        series_values = _facet_values(filters, self.mapper.facet_names("series"))
        if series_values:
            series = series_values[0]

        kind_values = _facet_values(filters, self.mapper.facet_names("kind"))
        access_values = _facet_values(filters, self.mapper.facet_names("access"))
        unit_values = _facet_values(filters, self.mapper.facet_names("units"))
        topic_values = _facet_values(filters, self.mapper.facet_names("topics"))

        departments = [
            str(d.get("name")) for d in (raw.get("departments") or []) if d.get("name")
        ]
        units = sorted(set(unit_values) | set(departments))
        topics = sorted(set(topic_values) | {str(k) for k in (raw.get("keywords") or [])})

        experience = (raw.get("experience") or "").lower()
        is_virtual = experience in {"virtual", "hybrid"} or bool(raw.get("stream_url"))

        geo = raw.get("geo") or {}
        address_bits = [
            geo.get("street"),
            geo.get("city"),
            geo.get("state"),
            geo.get("zip"),
        ]
        address = ", ".join(b for b in address_bits if b) or None

        location_bits = [raw.get("location_name") or raw.get("location")]
        if raw.get("room_number"):
            location_bits.append(f"Room {raw['room_number']}")
        location = ", ".join(clean(b) for b in location_bits if b) or None

        description = clean(raw.get("description_text") or raw.get("description") or "")

        # Localist marks non-public events with `private`; appendix B says treat
        # that as "check with the organiser", not as a hard exclusion.
        access = self.mapper.map_access(access_values)
        if raw.get("private") and access == "open":
            access = "check"

        campus_default = self.config.campus or "other"
        campus = "online" if experience == "virtual" else campus_default

        event = Event(
            uid=self.make_uid(raw.get("id")),
            source=self.source_id,
            title=title or title_raw,
            speaker=None,
            series=series,
            start=start,
            end=end,
            all_day=bool(inst.get("all_day")),
            location=location,
            address=address,
            campus=campus,
            is_virtual=is_virtual,
            url=raw.get("localist_url") or raw.get("url") or "",
            registration_url=raw.get("ticket_url") or None,
            registration_deadline=None,
            kind=self.mapper.map_kind(kind_values),
            access=access,
            units=units,
            topics=topics,
            description=truncate(description, 2000),
            raw_facets={
                "filters": filters,
                "departments": departments,
                "keywords": raw.get("keywords") or [],
                "experience": raw.get("experience"),
                "private": raw.get("private"),
                "recurring": raw.get("recurring"),
                "all_facet_values": _all_facet_values(filters),
                "free": raw.get("free"),
                "has_register": raw.get("has_register"),
            },
            fetched_at=now_utc(),
            cancelled_marker=marker,
        )
        if marker in {"CANCELLED", "POSTPONED"}:
            event.status = "CANCELLED"
        return event


def discover(fetcher, domain: str, path: str | None = None) -> dict[str, Any]:
    """Pull the full vocabulary of one Localist instance.

    Walks a wide date window and collects every facet group and value that
    actually appears, which is the honest version of "read the filter panel".
    """
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    prefix = f"https://{domain}"
    if path:
        prefix = f"{prefix}/{path.strip('/')}"
    url = f"{prefix}/api/2/events"

    facets: dict[str, set[str]] = {}
    departments: set[str] = set()
    venues: dict[str, str] = {}
    keywords: set[str] = set()
    total_events = 0

    page = 1
    while page <= MAX_PAGES:
        resp = fetcher.get(url, params={"days": 365, "pp": PAGE_SIZE, "page": page})
        resp.raise_for_status()
        payload = resp.json()
        wrappers = payload.get("events") or []
        for wrapper in wrappers:
            raw = wrapper.get("event") or {}
            total_events += 1
            for group, entries in (raw.get("filters") or {}).items():
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict) and entry.get("name"):
                            facets.setdefault(group, set()).add(str(entry["name"]))
            for dept in raw.get("departments") or []:
                if dept.get("name"):
                    departments.add(str(dept["name"]))
            if raw.get("location_name"):
                venues[str(raw["location_name"])] = str(raw.get("venue_id") or "")
            for kw in raw.get("keywords") or []:
                keywords.add(str(kw))
        paging = payload.get("page") or {}
        if page >= int(paging.get("total") or 1):
            break
        page += 1

    return {
        "domain": domain,
        "path": path,
        "events_scanned": total_events,
        "facets": {g: sorted(v) for g, v in sorted(facets.items())},
        "departments": sorted(departments),
        "venues": dict(sorted(venues.items())),
        "keywords": sorted(keywords),
    }
