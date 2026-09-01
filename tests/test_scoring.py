from datetime import timedelta

from harvard_events.config import Settings
from harvard_events.core.scoring import ScoringContext, score_event


def make_settings(**overrides):
    defaults = dict(
        sources=[],
        subscriptions={},
        keywords={},
        scoring={
            "subscription_bonus": 25,
            "subscription_suppresses_keywords": True,
            "kind_weight": {"lecture": 6},
            "conflict": {"overlap_penalty": -30, "outside_window_penalty": -8},
            "access_penalty": {"open": 0, "check": -2, "restricted": -25},
            "virtual_adjustment": -3,
        },
        campus={"penalties": {"cambridge_harvard": 0, "cambridge_mit": -2, "online": -3}},
        busy={},
        registry={},
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_subscription_hit_gives_bonus_and_suppresses_keywords(event_factory):
    settings = make_settings(
        subscriptions={"test": {"series": ["Great Series"]}},
        keywords={
            "groups": [],
            "negative": [
                {"name": "bad", "weight": -10, "terms": ["lecture"], "acronyms": []}
            ],
        },
    )
    ctx = ScoringContext.from_settings(settings)
    event = event_factory(series="Great Series", title="Sample Lecture")
    score, detail = score_event(event, ctx)
    assert detail["subscription"] == 25
    assert detail["keywords"] == 0  # negative keyword suppressed
    assert detail["subscription_match"].startswith("series")


def test_subscription_matching_ignores_case_and_punctuation(event_factory):
    settings = make_settings(
        subscriptions={"test": {"series": ["CRCS Seminars"]}},
    )
    ctx = ScoringContext.from_settings(settings)
    event = event_factory(series="CRCS seminar")
    _, detail = score_event(event, ctx)
    assert detail["subscription"] == 25


def test_busy_conflict_penalty(event_factory):
    start = event_factory().start  # 16:00
    day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][start.weekday()]
    settings = make_settings(
        busy={"busy": [{"name": "Studio", "days": [day], "start": "15:00", "end": "18:00"}]}
    )
    ctx = ScoringContext.from_settings(settings)
    _, detail = score_event(event_factory(start=start), ctx)
    assert detail["conflict"] == -30
    assert detail["conflict_reason"] == "busy_overlap"


def test_outside_window_penalty(event_factory):
    start = event_factory().start  # 16:00 on some weekday
    day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][start.weekday()]
    settings = make_settings(
        busy={"available": [{"days": [day], "start": "18:00", "end": "22:00"}]}
    )
    ctx = ScoringContext.from_settings(settings)
    _, detail = score_event(event_factory(start=start), ctx)
    assert detail["conflict"] == -8
    assert detail["conflict_reason"] == "outside_window"


def test_no_conflict_check_for_exhibitions(event_factory):
    start = event_factory().start
    day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][start.weekday()]
    settings = make_settings(
        busy={"busy": [{"name": "Studio", "days": [day], "start": "00:00", "end": "23:59"}]}
    )
    ctx = ScoringContext.from_settings(settings)
    event = event_factory(kind="exhibition", start=start)
    _, detail = score_event(event, ctx)
    assert detail["conflict"] == 0


def test_access_and_commute(event_factory):
    ctx = ScoringContext.from_settings(make_settings())
    event = event_factory(access="restricted", campus="cambridge_mit", kind="lecture")
    _, detail = score_event(event, ctx)
    assert detail["commute_access"] == -25 + -2
    virtual = event_factory(is_virtual=True, campus="online")
    _, detail = score_event(virtual, ctx)
    assert detail["commute_access"] == -3 + -3  # campus + virtual adjustment
