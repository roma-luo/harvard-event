"""Layer 1: translate each source's own vocabulary into the unified fields.

Anything the mapping file does not cover is recorded in ``logs/unmapped.log``
and surfaced in the weekly health section. Silently falling back to ``other``
would let a newly-added category disappear without anyone noticing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from ..config import load_taxonomy
from ..models import ACCESS_LEVELS, KINDS, Event
from ..paths import LOGS_DIR, UNMAPPED_LOG

# access is deliberately ranked: the most restrictive value seen wins.
_ACCESS_RANK = {"open": 0, "check": 1, "restricted": 2}
# kind is ranked the other way: the most specific value seen wins.
_KIND_PRIORITY = [
    "exhibition",
    "defense",
    "conference",
    "workshop",
    "showcase",
    "lecture",
    "career",
    "social",
    "admin",
    "other",
]


class UnmappedRecorder:
    """Collects `(source, facet, value)` triples seen during one run."""

    def __init__(self) -> None:
        self.items: set[tuple[str, str, str]] = set()

    def add(self, source_id: str, facet: str, value: str) -> None:
        self.items.add((source_id, facet, value))

    def for_source(self, source_id: str) -> list[str]:
        return sorted(
            f"{facet}: {value}"
            for src, facet, value in self.items
            if src == source_id
        )

    def flush(self) -> None:
        if not self.items:
            return
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with UNMAPPED_LOG.open("a", encoding="utf-8") as fh:
            for src, facet, value in sorted(self.items):
                fh.write(f"{stamp}\t{src}\t{facet}\t{value}\n")


class Mapper:
    """Applies one source's `config/taxonomy/<source_id>.yml`."""

    def __init__(
        self,
        taxonomy_id: str,
        recorder: UnmappedRecorder | None = None,
        *,
        report_as: str | None = None,
    ):
        self.taxonomy_id = taxonomy_id
        # Unmapped values are reported against the source, not the shared file.
        self.source_id = report_as or taxonomy_id
        self.spec = load_taxonomy(taxonomy_id)
        self.recorder = recorder or UnmappedRecorder()
        self._kind = self._lower_keys(self.spec.get("kind", {}))
        self._access = self._lower_keys(self.spec.get("access", {}))
        self._campus = self._lower_keys(self.spec.get("campus", {}))
        # Which facet group feeds which unified field, per source.
        self._facets: dict[str, list[str]] = self.spec.get("facets", {})
        self._ignore = {v.lower() for v in self.spec.get("ignore", [])}
        # Fallback for sources with no type facet at all (plain ICS feeds).
        self._title_kind: list[tuple[re.Pattern[str], str]] = [
            (re.compile(rule["pattern"], re.IGNORECASE), rule["kind"])
            for rule in self.spec.get("kind_from_title", [])
        ]

    @staticmethod
    def _lower_keys(mapping: dict[str, Any]) -> dict[str, str]:
        return {str(k).strip().lower(): str(v) for k, v in (mapping or {}).items()}

    def facet_names(self, field: str) -> list[str]:
        """Facet group keys that carry `field` for this source."""
        return self._facets.get(field, [])

    @property
    def has_access_map(self) -> bool:
        """False when the taxonomy defines no access mapping at all.

        Callers should skip ``map_access`` in that case: feeding values through
        an empty map would log every value as unmapped noise.
        """
        return bool(self._access)

    def map_kind(self, values: Iterable[str]) -> str:
        found: list[str] = []
        for value in values:
            if not value:
                continue
            key = value.strip().lower()
            if key in self._ignore:
                continue
            mapped = self._kind.get(key)
            if mapped is None:
                self.recorder.add(self.source_id, "kind", value)
                continue
            found.append(mapped)
        for candidate in _KIND_PRIORITY:
            if candidate in found:
                return candidate if candidate in KINDS else "other"
        return "other"

    def kind_from_title(self, title: str, default: str = "other") -> str:
        """Type guess for feeds that carry no structured type at all.

        Only reached when the source has no type facet, so it never masks a
        genuinely unmapped facet value.
        """
        for pattern, kind in self._title_kind:
            if pattern.search(title):
                return kind
        return default

    def map_access(self, values: Iterable[str], *, default: str = "check") -> str:
        seen: list[str] = []
        for value in values:
            if not value:
                continue
            key = value.strip().lower()
            if key in self._ignore:
                continue
            mapped = self._access.get(key)
            if mapped is None:
                self.recorder.add(self.source_id, "access", value)
                continue
            if mapped in ACCESS_LEVELS:
                seen.append(mapped)
        if not seen:
            return default
        # Anything explicitly open outranks a vaguer "check" on the same event;
        # an explicit restriction outranks everything.
        if "restricted" in seen:
            return "restricted"
        if "open" in seen:
            return "open"
        return "check"

    def map_campus(self, value: str | None, default: str) -> str:
        if not value:
            return default
        return self._campus.get(value.strip().lower(), default)


def apply_overrides(event: Event, overrides: list[dict[str, Any]]) -> Event:
    """Source-level rules from `config/taxonomy/<id>.yml` under `overrides`.

    Used for the appendix-B special cases, e.g. Media Lab Member Meetings are
    sponsor-only regardless of what the site says.
    """
    haystack = " ".join(
        filter(None, [event.title, event.series or "", event.description[:300]])
    ).lower()
    for rule in overrides or []:
        needles = [str(n).lower() for n in rule.get("title_contains", [])]
        if needles and not any(n in haystack for n in needles):
            continue
        if "access" in rule:
            event.access = rule["access"]
        if "kind" in rule:
            event.kind = rule["kind"]
        if "topics" in rule:
            event.topics = sorted(set(event.topics) | set(rule["topics"]))
    return event
