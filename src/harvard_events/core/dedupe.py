"""Dedup, in the two layers the plan calls for.

1. Same source system, same ``uid``: the MIT department channel and the E14
   building channel are one Localist instance with one event id, so this layer
   removes the overlap for free.
2. Cross-source: same normalized title and start times within a 15-minute
   window are the same event; the higher-priority source survives and both
   URLs are kept.

Plus the recurring-event weekly cap, so a standing weekly seminar cannot fill
every slot of the calendar with copies of itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from ..models import Event
from .text import normalize_title

WINDOW_SECONDS = 15 * 60


def dedupe(events: list[Event], priority_of: Callable[[str], int]) -> list[Event]:
    """Apply both dedup layers. ``priority_of`` maps a source id to its rank."""
    by_uid: dict[str, Event] = {}
    for event in events:
        by_uid.setdefault(event.uid, event)

    by_title: dict[str, list[Event]] = defaultdict(list)
    for event in by_uid.values():
        by_title[normalize_title(event.title)].append(event)

    merged: list[Event] = []
    for group in by_title.values():
        group.sort(key=lambda e: e.start)
        clusters: list[list[Event]] = []
        for event in group:
            if clusters and (
                event.start - clusters[-1][-1].start
            ).total_seconds() <= WINDOW_SECONDS:
                clusters[-1].append(event)
            else:
                clusters.append([event])
        for cluster in clusters:
            winner = max(cluster, key=lambda e: priority_of(e.source))
            for loser in cluster:
                if loser is winner:
                    continue
                for url in [loser.url, *loser.alt_urls]:
                    if url and url != winner.url and url not in winner.alt_urls:
                        winner.alt_urls.append(url)
            merged.append(winner)
    return merged


def apply_weekly_cap(
    events: list[Event], cap: int
) -> tuple[list[Event], list[Event]]:
    """Keep at most ``cap`` entries per (source, series, weekday, time, ISO week).

    Returns ``(kept, dropped)``; the dropped list feeds the health report's
    filtered-out count. Events without a series are never capped — two talks
    in the same time slot with no series name are genuinely different events.
    """
    if cap <= 0:
        return events, []
    kept: list[Event] = []
    dropped: list[Event] = []
    seen: set[tuple] = set()
    for event in sorted(events, key=lambda e: e.start):
        if not event.series:
            kept.append(event)
            continue
        iso = event.start.isocalendar()
        key = (
            event.source,
            normalize_title(event.series),
            event.start.weekday(),
            event.start.strftime("%H:%M"),
            iso[0],
            iso[1],
        )
        if key in seen:
            dropped.append(event)
            continue
        seen.add(key)
        kept.append(event)
    return kept, dropped
