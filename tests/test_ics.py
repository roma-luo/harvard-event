from datetime import timedelta

from icalendar import Calendar

from harvard_events.outputs.ics import build_calendar, describe


def parse(data: bytes) -> Calendar:
    return Calendar.from_ical(data)


def test_calendar_level_fields(event_factory):
    cal = parse(build_calendar([event_factory()], "Events - Priority"))
    assert cal["METHOD"] == "PUBLISH"
    assert cal["X-WR-CALNAME"] == "Events - Priority"
    assert cal["X-PUBLISHED-TTL"].to_ical() == b"PT12H"


def test_event_fields(event_factory):
    event = event_factory(sequence=3, access="check")
    cal = parse(build_calendar([event], "X"))
    vevent = cal.walk("VEVENT")[0]
    assert str(vevent["UID"]) == event.uid
    assert vevent["SEQUENCE"] == 3
    assert str(vevent["STATUS"]) == "CONFIRMED"
    assert str(vevent["SUMMARY"]).startswith("[需确认] ")
    # TZID must be the named zone, not a fixed offset (Boston has DST).
    assert vevent["DTSTART"].params.get("TZID") is not None
    assert "America/New_York" in str(vevent["DTSTART"].params["TZID"])


def test_cancelled_prefix(event_factory):
    event = event_factory(status="CANCELLED")
    cal = parse(build_calendar([event], "X"))
    vevent = cal.walk("VEVENT")[0]
    assert str(vevent["SUMMARY"]).startswith("[已取消] ")
    assert str(vevent["STATUS"]) == "CANCELLED"


def test_all_day_event_uses_date(event_factory):
    event = event_factory(all_day=True)
    cal = parse(build_calendar([event], "X"))
    vevent = cal.walk("VEVENT")[0]
    assert not hasattr(vevent.decoded("DTSTART"), "hour")


def test_location_prefers_address(event_factory):
    event = event_factory(location="Piper Auditorium, Gund Hall",
                          address="48 Quincy Street, Cambridge, MA 02138")
    cal = parse(build_calendar([event], "X"))
    vevent = cal.walk("VEVENT")[0]
    assert "Quincy" in str(vevent["LOCATION"])
    assert "Piper" in str(vevent["DESCRIPTION"])  # room name lives in DESCRIPTION


def test_description_template_contains_score_and_source(event_factory):
    event = event_factory(score=24, speaker="Dorte Mandrup",
                          series="Kenzō Tange Lecture")
    body = describe(event)
    assert "准入：" in body
    assert "系列：Kenzō Tange Lecture" in body
    assert "主讲：Dorte Mandrup" in body
    assert "得分 24" in body
