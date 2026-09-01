"""The daily pipeline: fetch -> dedupe -> state -> score -> select -> outputs.

Split into small functions so the CLI commands (``run`` / ``preview``) and the
tests can each take the slice they need.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .adapters.registry import build_adapter
from .config import Settings, load_settings
from .core.dedupe import apply_weekly_cap, dedupe
from .core.scoring import ScoringContext, append_scoring_log, score_all
from .core.state import SeenState
from .http import Fetcher
from .models import Event, SourceHealth
from .outputs.email import Digest, deliver
from .outputs.ics import write_calendars
from .paths import HEALTH_FILE, ensure_dirs
from .taxonomy.mapper import UnmappedRecorder

EASTERN = ZoneInfo("America/New_York")


@dataclass
class RunResult:
    events: list[Event] = field(default_factory=list)  # active, scored
    priority: list[Event] = field(default_factory=list)
    others: list[Event] = field(default_factory=list)
    exhibitions: list[Event] = field(default_factory=list)
    cancelled: list[Event] = field(default_factory=list)
    dropped: list[Event] = field(default_factory=list)
    health: list[SourceHealth] = field(default_factory=list)
    decisions: dict[str, str] = field(default_factory=dict)


def fetch_all(
    settings: Settings,
    fetcher: Fetcher,
    recorder: UnmappedRecorder,
    source_ids: list[str] | None = None,
    days: int = 21,
) -> tuple[list[Event], list[SourceHealth]]:
    """Fetch every enabled source; a dead source is a health row, not a crash."""
    events: list[Event] = []
    health: list[SourceHealth] = []
    for src in settings.enabled_sources():
        if source_ids and src.id not in source_ids:
            continue
        row = SourceHealth(source_id=src.id, ok=False)
        try:
            adapter = build_adapter(src, fetcher, recorder)
            found = adapter.fetch(days)
            row.ok = True
            row.count = len(found)
            events.extend(found)
        except Exception as exc:  # noqa: BLE001 — any adapter failure is data
            row.error = f"{type(exc).__name__}: {exc}"
        row.unmapped = recorder.for_source(src.id)
        health.append(row)
    return events, health


def select(result: RunResult, settings: Settings) -> None:
    """Split scored events into priority / all / exhibitions / dropped.

    8 is a ceiling, not a target: a slot stays empty rather than take an
    event below ``priority_min_score``. Exhibitions never enter an ICS.
    Cancelled events keep the calendar they were last published in.
    """
    scoring = settings.scoring or {}
    size = int(scoring.get("priority_calendar_size", 8))
    priority_min = float(scoring.get("priority_min_score", 12))
    all_min = float(scoring.get("all_calendar_min_score", -5))

    active = [e for e in result.events if e.status != "CANCELLED"]
    cancelled_now = [e for e in result.events if e.status == "CANCELLED"]

    exhibitions = [e for e in active if e.kind == "exhibition"]
    regular = [e for e in active if e.kind != "exhibition"]
    regular.sort(key=lambda e: e.score, reverse=True)

    result.priority = [e for e in regular if e.score >= priority_min][:size]
    rest = regular[len(result.priority):]
    result.others = [e for e in rest if e.score >= all_min]
    result.dropped = [e for e in rest if e.score < all_min]
    result.exhibitions = exhibitions
    result.cancelled = cancelled_now  # ghosts are appended by run()

    for e in result.priority:
        result.decisions[e.uid] = "priority"
    for e in result.others:
        result.decisions[e.uid] = "all"
    for e in result.dropped:
        result.decisions[e.uid] = "dropped"
    for e in exhibitions:
        result.decisions[e.uid] = "exhibition"
    for e in cancelled_now:
        result.decisions[e.uid] = "cancelled"


def _load_health_history() -> dict:
    if HEALTH_FILE.exists():
        try:
            return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_health(health: list[SourceHealth]) -> dict[str, int]:
    """Persist per-source health and return the consecutive-failure counts."""
    history = _load_health_history()
    streaks: dict[str, int] = {}
    for row in health:
        prev = history.get(row.source_id) or {}
        streak = 0 if row.ok else int(prev.get("consecutive_failures", 0)) + 1
        streaks[row.source_id] = streak
        history[row.source_id] = {
            "ok": row.ok,
            "consecutive_failures": streak,
            "count": row.count,
            "error": row.error,
            "last_run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(
        json.dumps(history, indent=1, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return streaks


def build_digest(result: RunResult, settings: Settings, streaks: dict[str, int]) -> Digest:
    scoring = settings.scoring or {}
    now = datetime.now(EASTERN)
    week_end = now + timedelta(days=int(scoring.get("deadline_lookahead_days", 7)))
    win_lo, win_hi = scoring.get("deadline_event_window", [8, 21])

    in_week = [e for e in result.priority if e.start <= week_end]
    others_week = [e for e in result.others if e.start <= week_end]
    deadlines = [
        e
        for e in result.events
        if e.registration_deadline
        and now.date() <= e.registration_deadline <= week_end.date()
        and now + timedelta(days=win_lo) <= e.start <= now + timedelta(days=win_hi)
    ]
    exhibitions = [
        e for e in result.exhibitions if (e.end or e.start) >= now
    ]
    exhibitions.sort(key=lambda e: e.end or e.start)
    return Digest(
        priority=in_week,
        others=others_week,
        deadline_events=sorted(deadlines, key=lambda e: e.registration_deadline),
        exhibitions=exhibitions,
        cancelled=result.cancelled,
        health=result.health,
        consecutive_failures=streaks,
        week_start=now,
    )


def run(
    days: int | None = None,
    *,
    send_mail: bool = False,
    source_ids: list[str] | None = None,
    write: bool = True,
) -> RunResult:
    settings = load_settings()
    scoring = settings.scoring or {}
    days = days or int(scoring.get("horizon_days", 21))
    if write:
        ensure_dirs()

    recorder = UnmappedRecorder()
    result = RunResult()
    with Fetcher() as fetcher:
        events, result.health = fetch_all(
            settings, fetcher, recorder, source_ids, days
        )

    events = dedupe(events, settings.source_priority)
    cap = int(scoring.get("recurring_weekly_cap", 1))
    events, capped = apply_weekly_cap(events, cap)
    capped_per_source: dict[str, int] = {}
    for e in capped:
        capped_per_source[e.source] = capped_per_source.get(e.source, 0) + 1
    for row in result.health:
        row.filtered_out = capped_per_source.get(row.source_id, 0)

    state = SeenState()
    for event in events:
        state.update(event)
    seen = state.seen_uids(events)
    ghosts = state.ghosts(seen) if write else []

    ctx = ScoringContext.from_settings(settings)
    result.events = score_all(events, ctx)
    select(result, settings)

    # Cancelled entries (marker-cancelled now, or ghosts from earlier runs)
    # go back to the calendar they were last published in, so Outlook removes
    # them from the right place.
    priority_uids = {e.uid for e in result.priority}
    for event, calendar in ghosts:
        event.score_detail = event.score_detail or {}
        (result.priority if calendar == "priority" else result.others).append(event)
        result.decisions[event.uid] = "cancelled"
    for event in result.cancelled:
        entry = state.entries.get(event.uid) or {}
        if entry.get("calendar") == "priority" and event.uid not in priority_uids:
            result.priority.append(event)
        elif event.uid not in priority_uids:
            result.others.append(event)
    result.cancelled += [e for e, _ in ghosts]

    for event in result.priority:
        state.set_calendar(event.uid, "priority")
    for event in result.others:
        state.set_calendar(event.uid, "all")

    if write:
        write_calendars(result.priority, result.others)
        append_scoring_log(result.events, result.decisions)
        recorder.flush()
        state.purge()
        state.save()
        streaks = _save_health(result.health)
    else:
        streaks = {}

    now = datetime.now(EASTERN)
    should_mail = send_mail or (write and now.weekday() == 6)
    if should_mail:
        digest = build_digest(result, settings, streaks)
        sent, subject = deliver(digest)
        print(f"weekly email: {'sent' if sent else 'written to logs/ (no SMTP credentials)'} — {subject}")
    return result
