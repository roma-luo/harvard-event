"""The unified event record every adapter must produce."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

KINDS = (
    "lecture",
    "conference",
    "workshop",
    "exhibition",
    "defense",
    "social",
    "career",
    "admin",
    "other",
)

ACCESS_LEVELS = ("open", "check", "restricted")

CAMPUSES = (
    "cambridge_harvard",
    "cambridge_mit",
    "allston",
    "longwood",
    "online",
    "other",
)


@dataclass
class Event:
    uid: str
    source: str
    title: str
    start: datetime
    url: str
    speaker: str | None = None
    series: str | None = None
    end: datetime | None = None
    all_day: bool = False
    location: str | None = None
    address: str | None = None
    campus: str = "other"
    is_virtual: bool = False
    registration_url: str | None = None
    registration_deadline: date | None = None
    kind: str = "other"
    access: str = "check"
    units: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    description: str = ""
    raw_facets: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime | None = None

    # Populated by the pipeline, not by adapters.
    score: float = 0.0
    score_detail: dict[str, float] = field(default_factory=dict)
    status: str = "CONFIRMED"
    sequence: int = 0
    alt_urls: list[str] = field(default_factory=list)
    cancelled_marker: str | None = None

    def content_hash(self) -> str:
        """Hash of the user-visible content, for change detection.

        Deliberately excludes ``fetched_at``, score and sequence: those change
        on every run and would make every event look modified.
        """
        payload = {
            "title": self.title,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "location": self.location,
            "address": self.address,
            "speaker": self.speaker,
            "series": self.series,
            "kind": self.kind,
            "access": self.access,
            "url": self.url,
            "registration_url": self.registration_url,
            "description": (self.description or "")[:400],
            "status": self.status,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key, value in list(d.items()):
            if isinstance(value, datetime):
                d[key] = value.isoformat()
            elif isinstance(value, date):
                d[key] = value.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        """Rebuild an Event from ``to_dict`` output (used by state/seen.json)."""
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in d.items() if k in known}
        for key in ("start", "end", "fetched_at"):
            if isinstance(kwargs.get(key), str):
                kwargs[key] = datetime.fromisoformat(kwargs[key])
        if isinstance(kwargs.get("registration_deadline"), str):
            kwargs["registration_deadline"] = date.fromisoformat(
                kwargs["registration_deadline"]
            )
        return cls(**kwargs)


@dataclass
class SourceHealth:
    """One row of the weekly health report."""

    source_id: str
    ok: bool
    count: int = 0
    error: str | None = None
    unmapped: list[str] = field(default_factory=list)
    filtered_out: int = 0
