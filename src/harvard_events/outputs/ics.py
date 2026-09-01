"""ICS generation — the two subscribable calendars.

Both files are served from GitHub Pages and subscribed by URL in Outlook
("subscribe from web", never "import": an import never refreshes).

* exhibitions are never written here — a month-long show would render as a
  week-crossing all-day banner and wreck the week view; they live in the
  weekly email instead
* ``SUMMARY`` carries a plain-text access prefix instead of emoji, which some
  Outlook clients render badly
* ``LOCATION`` is a navigable street address; the room name goes in
  ``DESCRIPTION``
* ``SEQUENCE`` comes from the change-detection state, so an edited event
  updates in place in Outlook
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event as IcsEvent
from icalendar.prop import vDuration

from ..core.text import truncate
from ..models import Event
from ..paths import ALL_ICS, PRIORITY_ICS

PRIORITY_CALNAME = "Events - Priority"
ALL_CALNAME = "Events - All"

ACCESS_PREFIX = {"open": "[开放] ", "check": "[需确认] ", "restricted": "[受限] "}
ACCESS_LABEL = {
    "open": "开放（无需报名）",
    "check": "需确认（请看活动页要求）",
    "restricted": "受限（可能不对外开放）",
}
KIND_LABEL = {
    "lecture": "讲座",
    "conference": "会议",
    "workshop": "工作坊",
    "exhibition": "展览",
    "defense": "答辩",
    "showcase": "展示",
    "social": "社交",
    "career": "职业发展",
    "admin": "行政",
    "other": "其他",
}


def describe(event: Event) -> str:
    """The fixed DESCRIPTION template — plain text, score included."""
    lines = [
        f"准入：{ACCESS_LABEL.get(event.access, event.access)}",
        f"类型：{KIND_LABEL.get(event.kind, event.kind)}"
        + (f"｜系列：{event.series}" if event.series else ""),
        "",
    ]
    if event.speaker:
        lines += [f"主讲：{event.speaker}", ""]
    if event.description:
        lines += [f"摘要：{truncate(event.description, 400)}", ""]
    if event.location:
        lines.append(f"地点：{event.location}")
    lines.append(f"活动页：{event.url}")
    for url in event.alt_urls:
        lines.append(f"同活动另见：{url}")
    if event.registration_url:
        lines.append(f"报名：{event.registration_url}")
    if event.registration_deadline:
        lines.append(f"报名截止：{event.registration_deadline.isoformat()}")
    fetched = (
        event.fetched_at.strftime("%Y-%m-%d %H:%M") if event.fetched_at else "?"
    )
    lines += [
        "",
        f"来源：{event.source}｜得分 {event.score:.0f}｜抓取于 {fetched}",
    ]
    return "\n".join(lines)


def _to_component(event: Event) -> IcsEvent:
    vevent = IcsEvent()
    vevent.add("uid", event.uid)
    vevent.add("dtstamp", datetime.now(timezone.utc))
    prefix = ACCESS_PREFIX.get(event.access, "")
    if event.status == "CANCELLED":
        prefix = "[已取消] "
    vevent.add("summary", f"{prefix}{event.title}")
    if event.all_day:
        vevent.add("dtstart", event.start.date())
        end_date = (event.end or event.start).date()
        vevent.add("dtend", end_date + timedelta(days=1))
    else:
        # zoneinfo-aware datetimes make icalendar emit TZID=America/New_York.
        vevent.add("dtstart", event.start)
        vevent.add("dtend", event.end or (event.start + timedelta(hours=1)))
    vevent.add("description", describe(event))
    if event.address or event.location:
        # LOCATION is the navigable street address; the room stays in the
        # description where it does not confuse a maps client.
        vevent.add("location", event.address or event.location)
    if event.url:
        vevent.add("url", event.url)
    vevent.add("sequence", int(event.sequence))
    vevent.add("status", event.status)
    return vevent


def build_calendar(events: list[Event], calname: str) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//harvard-mit-events//EN")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", calname)
    cal.add("x-wr-timezone", "America/New_York")
    # icalendar guesses vTime for a bare timedelta here; force a real duration
    # or Outlook sees "12:00:00" instead of "PT12H".
    cal["X-PUBLISHED-TTL"] = vDuration(timedelta(hours=12))
    for event in sorted(events, key=lambda e: e.start):
        cal.add_component(_to_component(event))
    return cal.to_ical()


def write_calendars(
    priority: list[Event],
    others: list[Event],
    priority_path: Path = PRIORITY_ICS,
    all_path: Path = ALL_ICS,
) -> tuple[Path, Path]:
    priority_path.parent.mkdir(parents=True, exist_ok=True)
    priority_path.write_bytes(build_calendar(priority, PRIORITY_CALNAME))
    all_path.write_bytes(build_calendar(others, ALL_CALNAME))
    return priority_path, all_path
