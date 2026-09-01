from harvard_events.pipeline import RunResult, select
from tests.test_scoring import make_settings


def settings():
    return make_settings(
        scoring={
            "priority_calendar_size": 3,
            "priority_min_score": 12,
            "all_calendar_min_score": -5,
        }
    )


def test_priority_is_a_ceiling_not_a_target(event_factory):
    events = [event_factory(uid=f"e-{i}@x", title=f"Talk {i}", score=score)
              for i, score in enumerate([50, 40, 30, 20, 15, 5, -20])]
    result = RunResult(events=events)
    select(result, settings())
    # 5 events qualify for priority but the calendar holds at most 3.
    assert [e.score for e in result.priority] == [50, 40, 30]
    assert [e.score for e in result.others] == [20, 15, 5]
    assert [e.score for e in result.dropped] == [-20]


def test_priority_slots_stay_empty_below_min_score(event_factory):
    events = [event_factory(uid=f"e-{i}@x", title=f"Talk {i}", score=score)
              for i, score in enumerate([5, 4, 3, 2, 1, 0])]
    result = RunResult(events=events)
    select(result, settings())
    assert result.priority == []
    assert len(result.others) == 6


def test_exhibitions_never_enter_a_calendar(event_factory):
    events = [
        event_factory(uid="ex-1@x", title="Big Show", kind="exhibition", score=99),
        event_factory(uid="le-1@x", title="Talk", kind="lecture", score=50),
    ]
    result = RunResult(events=events)
    select(result, settings())
    assert [e.uid for e in result.exhibitions] == ["ex-1@x"]
    assert all(e.kind != "exhibition" for e in result.priority + result.others)
    assert result.decisions["ex-1@x"] == "exhibition"


def test_cancelled_events_rerouted_not_selected(event_factory):
    cancelled = event_factory(uid="c-1@x", title="Gone", status="CANCELLED", score=99)
    result = RunResult(events=[cancelled])
    select(result, settings())
    assert result.priority == [] and result.others == []
    assert result.cancelled == [cancelled]
    assert result.decisions["c-1@x"] == "cancelled"
