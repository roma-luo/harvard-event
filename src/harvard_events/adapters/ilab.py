"""Harvard Innovation Labs — a scrape of the upcoming-events list page.

The probe found no API, ICS or RSS (the WordPress REST route is behind
Cloudflare), but ``/events/upcoming`` renders every event as a tease card:

    <li class="event-tease">
      <a href=".../events/<slug>" class="event-tease__link">
        <p class="event-tease__date">Tue, Nov 17</p>
        <h2 class="event-tease__title">Coffee + Connections</h2>
        <p class="event-tease__info-date">3:00pm – 4:00pm</p>
        <p class="event-tease__info-location">Harvard Innovation Labs</p>

The card has no year and no type, so the year is inferred from the weekday
and the type comes from title rules in ``config/taxonomy/harvard_ilab.yml``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from bs4 import BeautifulSoup

from ..core.text import clean
from ..models import Event
from .base import EASTERN, Adapter, now_utc

LIST_URL = "https://innovationlabs.harvard.edu/events/upcoming"
ILAB_ADDRESS = "125 Western Avenue, Allston, MA 02163"
HBS_ADDRESS = "Harvard Business School, Boston, MA 02163"

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
    start=1,
)}
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DATE_RE = re.compile(r"(?:(\w{3})\w*,?\s+)?(\w{3})\w*\.?\s+(\d{1,2})")
_CLOCK_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", re.I)


def infer_date(label: str, today: date) -> date | None:
    """"Tue, Nov 17" -> the nearest such date not long past.

    The list only shows upcoming events, so the first candidate year that is
    no more than a week behind today is right; the weekday breaks ties when
    the card has one.
    """
    match = _DATE_RE.search(label or "")
    if not match:
        return None
    weekday, month_name, day = match.group(1), match.group(2), int(match.group(3))
    month = _MONTHS.get(month_name.lower())
    if not month:
        return None
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    floor = today - timedelta(days=7)
    viable = [d for d in candidates if d >= floor]
    if weekday and weekday.lower()[:3] in _DAYS:
        wanted = _DAYS.index(weekday.lower()[:3])
        matching = [d for d in viable if d.weekday() == wanted]
        if matching:
            return matching[0]
    return viable[0] if viable else None


def parse_clock(text: str) -> list[time]:
    out = []
    for hour, minute, meridiem in _CLOCK_RE.findall(text or ""):
        h = int(hour) % 12 + (12 if meridiem.lower() == "p" else 0)
        out.append(time(h, int(minute or 0)))
    return out


class IlabAdapter(Adapter):
    type_name = "ilab"

    def fetch(self, days: int) -> list[Event]:
        html = self.fetcher.get_text(self.config.url or LIST_URL)
        return self.parse(html, days)

    def parse(self, html: str, days: int, *, today: date | None = None) -> list[Event]:
        today = today or datetime.now(EASTERN).date()
        horizon = today + timedelta(days=days + 1)
        soup = BeautifulSoup(html, "lxml")
        events: list[Event] = []
        seen: set[str] = set()
        for card in soup.select("li.event-tease"):
            event = self._to_event(card, today)
            if event is None or event.uid in seen:
                continue
            if not (today - timedelta(days=1) <= event.start.date() <= horizon):
                continue
            seen.add(event.uid)
            events.append(event)
        return events

    def _to_event(self, card, today: date) -> Event | None:
        link = card.select_one("a.event-tease__link") or card.find("a", href=True)
        title_el = card.select_one(".event-tease__title")
        date_el = card.select_one(".event-tease__date")
        if not (link and title_el and date_el):
            return None
        url = link["href"]
        title = clean(title_el.get_text(" "))
        day = infer_date(clean(date_el.get_text(" ")), today)
        if not (title and day):
            return None

        time_el = card.select_one(".event-tease__info-date")
        clocks = parse_clock(clean(time_el.get_text(" ")) if time_el else "")
        all_day = not clocks
        start = datetime.combine(day, clocks[0] if clocks else time(0), EASTERN)
        end = None
        if len(clocks) > 1:
            end = datetime.combine(day, clocks[1], EASTERN)
            if end <= start:
                end += timedelta(days=1)

        loc_el = card.select_one(".event-tease__info-location")
        location = clean(loc_el.get_text(" ")) if loc_el else ""
        lowered = location.lower()
        is_virtual = lowered in {"online", "virtual"} or "zoom" in lowered
        if "register to see" in lowered:
            location = ""
        if is_virtual:
            campus, address = "online", None
        elif "business school" in lowered or "hbs" in lowered:
            campus, address = self.config.campus or "allston", HBS_ADDRESS
        else:
            campus, address = self.config.campus or "allston", ILAB_ADDRESS

        partner = "event-tease--partner" in (card.get("class") or [])
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        return Event(
            uid=self.make_uid(slug),
            source=self.source_id,
            title=title,
            start=start,
            end=end,
            all_day=all_day,
            url=url,
            location=location or None,
            address=address,
            campus=campus,
            is_virtual=is_virtual,
            registration_url=url,
            kind=self.mapper.kind_from_title(title),
            access="check",  # nearly every i-lab event needs an Eventbrite RSVP
            units=["Harvard Innovation Labs"],
            topics=["partner"] if partner else [],
            raw_facets={"location_label": location, "partner": partner},
            fetched_at=now_utc(),
        )
