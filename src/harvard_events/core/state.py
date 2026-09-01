"""``state/seen.json`` — change detection and disappearance handling.

Each entry maps ``uid -> {content_hash, last_seen, sequence, calendar, event}``.
The full event dict is stored so an event that vanishes from its source while
still in the future can be re-emitted as ``STATUS:CANCELLED`` — that is how
Outlook learns to remove it rather than keep a ghost.

Rules:
* content changed  -> ``sequence`` + 1, which lands in the ICS ``SEQUENCE``
  field, so Outlook updates the entry instead of adding a duplicate
* disappeared but starts in the future -> re-emitted as CANCELLED, in the
  calendar it was last published to
* ended more than 30 days ago -> purged from the state file
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..models import Event
from ..paths import SEEN_FILE

PURGE_AFTER_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SeenState:
    def __init__(self, path: Path = SEEN_FILE):
        self.path = path
        self.entries: dict[str, dict] = {}
        if path.exists():
            try:
                self.entries = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.entries = {}

    def update(self, event: Event, *, calendar: str | None = None) -> None:
        """Record one fetched event, bumping ``sequence`` if content changed."""
        content_hash = event.content_hash()
        entry = self.entries.get(event.uid)
        if entry is None:
            event.sequence = 0
        else:
            event.sequence = int(entry.get("sequence", 0))
            if entry.get("content_hash") != content_hash:
                event.sequence += 1
        self.entries[event.uid] = {
            "content_hash": content_hash,
            "last_seen": _now().isoformat(timespec="seconds"),
            "sequence": event.sequence,
            "calendar": calendar
            or (entry or {}).get("calendar")
            or event.score_detail.get("calendar"),
            "event": event.to_dict(),
        }

    def set_calendar(self, uid: str, calendar: str) -> None:
        entry = self.entries.get(uid)
        if entry is not None:
            entry["calendar"] = calendar

    def ghosts(self, seen_uids: set[str]) -> list[tuple[Event, str]]:
        """Future events missing from this run, re-emitted as CANCELLED.

        Returns ``(event, calendar)`` pairs so the caller can route each ghost
        back to the calendar it was last published in.
        """
        now = _now()
        out: list[tuple[Event, str]] = []
        for uid, entry in self.entries.items():
            if uid in seen_uids:
                continue
            raw = entry.get("event")
            if not raw:
                continue
            try:
                event = Event.from_dict(raw)
            except (TypeError, ValueError):
                continue
            if event.start is None or event.start <= now:
                continue
            event.status = "CANCELLED"
            event.sequence = int(entry.get("sequence", 0))
            if not entry.get("ghost"):
                event.sequence += 1
                entry["ghost"] = True
                entry["sequence"] = event.sequence
                entry["content_hash"] = event.content_hash()
                entry["event"] = event.to_dict()
            out.append((event, entry.get("calendar") or "all"))
        return out

    def purge(self) -> int:
        """Drop entries whose event ended over 30 days ago."""
        cutoff = _now() - timedelta(days=PURGE_AFTER_DAYS)
        doomed = []
        for uid, entry in self.entries.items():
            raw = entry.get("event") or {}
            start_raw = raw.get("start")
            if not start_raw:
                doomed.append(uid)
                continue
            try:
                start = datetime.fromisoformat(start_raw)
            except ValueError:
                doomed.append(uid)
                continue
            if start < cutoff:
                doomed.append(uid)
        for uid in doomed:
            del self.entries[uid]
        return len(doomed)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.entries, indent=1, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def seen_uids(self, events: Iterable[Event]) -> set[str]:
        return {e.uid for e in events}
