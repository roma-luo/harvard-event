"""Shared fixtures: a small Event factory."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from harvard_events.models import Event

EASTERN = ZoneInfo("America/New_York")


def make_event(**overrides) -> Event:
    """An Event with sensible defaults; override whatever the test cares about."""
    start = datetime.now(EASTERN).replace(
        hour=16, minute=0, second=0, microsecond=0
    ) + timedelta(days=3)
    defaults = dict(
        uid="test-1@harvard-mit-events",
        source="test",
        title="Sample Lecture",
        start=start,
        end=start + timedelta(hours=1),
        url="https://example.edu/event/1",
        kind="lecture",
        access="open",
        campus="cambridge_harvard",
    )
    defaults.update(overrides)
    return Event(**defaults)


@pytest.fixture
def event_factory():
    return make_event
