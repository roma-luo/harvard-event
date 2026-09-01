"""Scoring: six components, pure rules, no model anywhere in the loop.

    total = subscription hit + keywords + source weight + kind weight
          + conflict penalty + commute/access adjustments

Every component of every event's score is appended to ``logs/scoring.jsonl`` —
when the calendar shows something it should not, that file is the only place
that can say which rule fired.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import Event
from ..paths import SCORING_LOG
from .keywords import KeywordEngine, KeywordHit
from .text import normalize_for_match

_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _canon(value: str) -> str:
    """Subscription matching: case, punctuation and plurals are noise."""
    text = normalize_for_match(value).lower()
    text = _PUNCT_RE.sub(" ", text)
    words = [
        # "Seminars" and "seminar" are the same series; strip trailing plurals
        # on both sides of the comparison so either form matches.
        w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w
        for w in text.split()
    ]
    return " ".join(words)


def _parse_hhmm(value: str) -> time | None:
    try:
        hour, minute = str(value).strip().split(":")[:2]
        return time(int(hour), int(minute))
    except (ValueError, TypeError):
        return None


@dataclass
class BusySchedule:
    """The user's fixed commitments and attendable windows (config/busy.yml)."""

    busy: list[dict[str, Any]] = field(default_factory=list)
    available: list[dict[str, Any]] = field(default_factory=list)
    blackout: list[str] = field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "BusySchedule":
        return cls(
            busy=list(spec.get("busy") or []),
            available=list(spec.get("available") or []),
            blackout=[str(d) for d in (spec.get("blackout") or [])],
        )

    @staticmethod
    def _overlaps(event: Event, days: list[str], start: time, end: time) -> bool:
        if event.start.weekday() not in [
            _DAY_NAMES.index(d) for d in days if d in _DAY_NAMES
        ]:
            return False
        ev_start = event.start.time()
        ev_end = (event.end or (event.start + timedelta(hours=1))).time()
        if ev_end <= ev_start:  # crosses midnight: treat the rest as reachable
            ev_end = time(23, 59)
        return ev_start < end and ev_end > start

    def conflicts(self, event: Event) -> bool:
        if event.start.date().isoformat() in self.blackout:
            return True
        for block in self.busy:
            start, end = _parse_hhmm(block.get("start", "")), _parse_hhmm(
                block.get("end", "")
            )
            if start and end and self._overlaps(
                event, [str(d).lower()[:3] for d in block.get("days") or []], start, end
            ):
                return True
        return False

    def outside_windows(self, event: Event) -> bool:
        """True when the event falls outside every declared attendable window."""
        if not self.available:
            return False
        for window in self.available:
            days = [str(d).lower()[:3] for d in window.get("days") or []]
            start, end = _parse_hhmm(window.get("start", "")), _parse_hhmm(
                window.get("end", "")
            )
            if not (start and end):
                continue
            if event.start.weekday() not in [
                _DAY_NAMES.index(d) for d in days if d in _DAY_NAMES
            ]:
                continue
            ev_start = event.start.time()
            ev_end = (event.end or (event.start + timedelta(hours=1))).time()
            if start <= ev_start and ev_end <= end:
                return False
        return True


@dataclass
class ScoringContext:
    """Everything the scorer needs, built once per run from Settings."""

    subscription_bonus: float
    suppress_keywords: bool
    subscriptions: dict[str, dict[str, set[str]]]
    engine: KeywordEngine
    source_weights: dict[str, float]
    kind_weight: dict[str, float]
    overlap_penalty: float
    outside_window_penalty: float
    access_penalty: dict[str, float]
    campus_penalty: dict[str, float]
    virtual_adjustment: float
    busy: BusySchedule

    @classmethod
    def from_settings(cls, settings: Settings) -> "ScoringContext":
        scoring = settings.scoring or {}
        conflict = scoring.get("conflict") or {}
        subs: dict[str, dict[str, set[str]]] = {}
        for source_id, spec in (settings.subscriptions or {}).items():
            if not isinstance(spec, dict):
                continue
            subs[source_id] = {
                field_name: {
                    _canon(str(v))
                    for v in (spec.get(field_name) or [])
                    if str(v).strip()
                }
                for field_name in ("series", "academic_areas", "units", "topics")
            }
        return cls(
            subscription_bonus=float(scoring.get("subscription_bonus", 25)),
            suppress_keywords=bool(
                scoring.get("subscription_suppresses_keywords", True)
            ),
            subscriptions=subs,
            engine=KeywordEngine(settings.keywords or {}),
            source_weights={s.id: float(s.weight) for s in settings.sources},
            kind_weight={
                str(k): float(v)
                for k, v in (scoring.get("kind_weight") or {}).items()
            },
            overlap_penalty=float(conflict.get("overlap_penalty", -30)),
            outside_window_penalty=float(
                conflict.get("outside_window_penalty", -8)
            ),
            access_penalty={
                str(k): float(v)
                for k, v in (scoring.get("access_penalty") or {}).items()
            },
            campus_penalty={
                str(k): float(v)
                for k, v in ((settings.campus or {}).get("penalties") or {}).items()
            },
            virtual_adjustment=float(scoring.get("virtual_adjustment", 0)),
            busy=BusySchedule.from_spec(settings.busy or {}),
        )

    def subscription_hit(self, event: Event) -> str | None:
        """The matched subscription field name, or None."""
        spec = self.subscriptions.get(event.source)
        if not spec:
            return None
        if event.series and _canon(event.series) in spec["series"]:
            return f"series: {event.series}"
        unit_set = {_canon(u) for u in event.units}
        if unit_set & spec["units"]:
            return "units"
        if unit_set & spec["academic_areas"]:
            return "academic_areas"
        topic_set = {_canon(t) for t in event.topics}
        if topic_set & spec["topics"]:
            return "topics"
        return None


def score_event(event: Event, ctx: ScoringContext) -> tuple[float, dict[str, Any]]:
    detail: dict[str, Any] = {}

    hit = ctx.subscription_hit(event)
    detail["subscription"] = ctx.subscription_bonus if hit else 0.0
    detail["subscription_match"] = hit

    if hit and ctx.suppress_keywords:
        kw_total, kw_hits = 0.0, []
    else:
        kw_total, kw_hits = ctx.engine.evaluate(
            event.title, event.series, event.speaker, event.description
        )
    detail["keywords"] = kw_total
    detail["keyword_hits"] = [
        {"group": h.group, "weight": h.weight, "matched": h.matched}
        for h in kw_hits
    ]

    detail["source"] = ctx.source_weights.get(event.source, 0.0)
    detail["kind"] = ctx.kind_weight.get(event.kind, 0.0)

    # Fixed-schedule conflict. All-day events and exhibitions have no real
    # clock time, so a conflict check against them is meaningless.
    conflict = 0.0
    if not event.all_day and event.kind != "exhibition":
        if ctx.busy.conflicts(event):
            conflict += ctx.overlap_penalty
            detail["conflict_reason"] = "busy_overlap"
        elif ctx.busy.outside_windows(event):
            conflict += ctx.outside_window_penalty
            detail["conflict_reason"] = "outside_window"
    detail["conflict"] = conflict

    commute_access = ctx.campus_penalty.get(event.campus, 0.0)
    commute_access += ctx.access_penalty.get(event.access, 0.0)
    if event.is_virtual:
        commute_access += ctx.virtual_adjustment
    detail["commute_access"] = commute_access

    total = (
        detail["subscription"]
        + detail["keywords"]
        + detail["source"]
        + detail["kind"]
        + detail["conflict"]
        + detail["commute_access"]
    )
    detail["total"] = total
    return total, detail


def score_all(
    events: list[Event], ctx: ScoringContext
) -> list[Event]:
    for event in events:
        event.score, event.score_detail = score_event(event, ctx)
    return events


def append_scoring_log(
    events: list[Event], decisions: dict[str, str], path: Path = SCORING_LOG
) -> None:
    """One JSON line per event: the audit trail for every selection decision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write(
                json.dumps(
                    {
                        "run": stamp,
                        "uid": event.uid,
                        "source": event.source,
                        "title": event.title,
                        "start": event.start.isoformat() if event.start else None,
                        "kind": event.kind,
                        "access": event.access,
                        "decision": decisions.get(event.uid, "?"),
                        "score": event.score,
                        "detail": event.score_detail,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
