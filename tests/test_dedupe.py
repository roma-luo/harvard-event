from datetime import timedelta

from harvard_events.core.dedupe import apply_weekly_cap, dedupe


def prio(source: str) -> int:
    return {"high": 100, "low": 10}.get(source, 0)


def test_same_uid_deduped(event_factory):
    e1 = event_factory(uid="a-1@harvard-mit-events")
    e2 = event_factory(uid="a-1@harvard-mit-events", title="Changed title")
    out = dedupe([e1, e2], prio)
    assert len(out) == 1


def test_cross_source_merge_keeps_high_priority(event_factory):
    start = event_factory().start
    hi = event_factory(
        uid="hi-1@x", source="high", title="The Big Lecture",
        start=start, url="https://hi.edu/e",
    )
    lo = event_factory(
        uid="lo-1@x", source="low", title="The Big Lecture",
        start=start + timedelta(minutes=10), url="https://lo.edu/e",
    )
    out = dedupe([lo, hi], prio)
    assert len(out) == 1
    assert out[0].source == "high"
    assert "https://lo.edu/e" in out[0].alt_urls


def test_cross_source_outside_window_not_merged(event_factory):
    start = event_factory().start
    a = event_factory(uid="a-1@x", source="high", title="The Big Lecture", start=start)
    b = event_factory(
        uid="b-1@x", source="low", title="The Big Lecture",
        start=start + timedelta(minutes=20),
    )
    out = dedupe([a, b], prio)
    assert len(out) == 2


def test_weekly_cap_keeps_one_per_series_slot(event_factory):
    start = event_factory().start
    events = [
        event_factory(
            uid=f"cap-{i}@x", title=f"Weekly Group Meeting #{i}",
            series="Weekly Group Meeting", start=start + timedelta(weeks=i),
        )
        for i in range(3)
    ]
    # Same series, same weekday+time, three consecutive weeks: all kept
    # (different ISO weeks).
    kept, dropped = apply_weekly_cap(events, 1)
    assert len(kept) == 3
    assert dropped == []


def test_weekly_cap_drops_same_week_duplicate(event_factory):
    start = event_factory().start
    events = [
        event_factory(
            uid=f"cap-{i}@x", title=f"Seminar instance {i}",
            series="Standing Seminar", start=start,
        )
        for i in range(2)
    ]
    kept, dropped = apply_weekly_cap(events, 1)
    assert len(kept) == 1
    assert len(dropped) == 1


def test_weekly_cap_ignores_events_without_series(event_factory):
    start = event_factory().start
    events = [
        event_factory(uid=f"ns-{i}@x", title=f"One-off {i}", start=start)
        for i in range(3)
    ]
    kept, dropped = apply_weekly_cap(events, 1)
    assert len(kept) == 3
