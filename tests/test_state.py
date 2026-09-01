from datetime import timedelta

from harvard_events.core.state import SeenState


def test_sequence_bumps_only_on_content_change(tmp_path, event_factory):
    state = SeenState(tmp_path / "seen.json")
    event = event_factory()
    state.update(event)
    assert event.sequence == 0

    # Same content again: no bump.
    state.update(event_factory())
    assert event.sequence == 0

    # Content changed: bump.
    changed = event_factory(title="Renamed Lecture")
    state.update(changed)
    assert changed.sequence == 1


def test_state_roundtrip(tmp_path, event_factory):
    path = tmp_path / "seen.json"
    state = SeenState(path)
    state.update(event_factory(uid="rt-1@x", title="Roundtrip"))
    state.save()
    loaded = SeenState(path)
    assert "rt-1@x" in loaded.entries
    assert loaded.entries["rt-1@x"]["event"]["title"] == "Roundtrip"


def test_disappeared_future_event_becomes_cancelled_ghost(tmp_path, event_factory):
    state = SeenState(tmp_path / "seen.json")
    event = event_factory(uid="ghost-1@x")
    state.update(event)
    state.set_calendar(event.uid, "priority")

    ghosts = state.ghosts(seen_uids=set())
    assert len(ghosts) == 1
    ghost, calendar = ghosts[0]
    assert ghost.status == "CANCELLED"
    assert ghost.sequence == 1  # bumped once on disappearance
    assert calendar == "priority"

    # A second run must not bump again.
    ghosts = state.ghosts(seen_uids=set())
    assert ghosts[0][0].sequence == 1


def test_past_event_is_not_a_ghost(tmp_path, event_factory):
    state = SeenState(tmp_path / "seen.json")
    past = event_factory(
        uid="past-1@x",
        start=event_factory().start - timedelta(days=5),
    )
    state.update(past)
    assert state.ghosts(seen_uids=set()) == []


def test_purge_removes_old_entries(tmp_path, event_factory):
    state = SeenState(tmp_path / "seen.json")
    state.update(
        event_factory(uid="old-1@x", start=event_factory().start - timedelta(days=40))
    )
    state.update(event_factory(uid="new-1@x"))
    assert state.purge() == 1
    assert "old-1@x" not in state.entries
    assert "new-1@x" in state.entries
