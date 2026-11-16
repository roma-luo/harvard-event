"""Harvard Innovation Labs list-page scrape."""

from __future__ import annotations

from datetime import date

from harvard_events.adapters.ilab import IlabAdapter, infer_date, parse_clock
from harvard_events.config import SourceConfig

LIST_HTML = """
<ul>
<li class="event-tease ">
  <a href="https://innovationlabs.harvard.edu/events/coffee-connections-7" class="event-tease__link">
    <div class="event-tease__hgroup featured">
      <p class="event-tease__date">Tue, Nov 17</p>
      <h2 class="event-tease__title">Coffee + Connections: PIC Edition!</h2>
    </div>
    <div class="event-tease__info featured">
      <p class="event-tease__info-date">3:00pm &ndash; 4:00pm</p>
      <p class="event-tease__info-location">Harvard Innovation Labs</p>
    </div>
  </a>
</li>
<li class="event-tease ">
  <a href="https://innovationlabs.harvard.edu/events/build-your-mvp-founder-clinics-3" class="event-tease__link">
    <p class="event-tease__date">Tue, Nov 17</p>
    <h2 class="event-tease__title">Founder Clinic: Build Your MVP</h2>
    <p class="event-tease__info-date">4:00pm &ndash; 5:00pm</p>
    <p class="event-tease__info-location">Online</p>
  </a>
</li>
<li class="event-tease event-tease--partner">
  <a href="https://innovationlabs.harvard.edu/events/founder-pathways-2" class="event-tease__link">
    <p class="event-tease__date">Thu, Nov 19</p>
    <h2 class="event-tease__title">Founder Pathways: Is This Startup Worth Pursuing?</h2>
    <p class="event-tease__info-date">5:30pm &ndash; 7:00pm</p>
    <p class="event-tease__info-location">Hawes Hall 201, Harvard Business School</p>
  </a>
</li>
<li class="event-tease ">
  <a href="https://innovationlabs.harvard.edu/events/pic-deadline" class="event-tease__link">
    <p class="event-tease__date">Tue, Dec 08</p>
    <h2 class="event-tease__title">Application Deadline: 2027 President's Innovation Challenge</h2>
    <p class="event-tease__info-date">11:59pm</p>
    <p class="event-tease__info-location">Online</p>
  </a>
</li>
<li class="event-tease ">
  <a href="https://innovationlabs.harvard.edu/events/far-away" class="event-tease__link">
    <p class="event-tease__date">Fri, Feb 26</p>
    <h2 class="event-tease__title">Spring Kickoff</h2>
    <p class="event-tease__info-date">5:00pm &ndash; 6:00pm</p>
    <p class="event-tease__info-location">Harvard Innovation Labs</p>
  </a>
</li>
</ul>
"""

TODAY = date(2026, 11, 16)


def adapter():
    cfg = SourceConfig(id="harvard_ilab", type="ilab", campus="allston",
                       taxonomy="harvard_ilab", calendar="hbs")
    return IlabAdapter(cfg, fetcher=None)


def test_infer_date_rolls_into_next_year():
    assert infer_date("Tue, Nov 17", TODAY) == date(2026, 11, 17)
    # Jan 5 2027 is a Tuesday; seen in November it must be next year.
    assert infer_date("Tue, Jan 05", TODAY) == date(2027, 1, 5)


def test_parse_clock_handles_noon_and_midnight_edges():
    assert [t.hour for t in parse_clock("12:00pm – 11:59pm")] == [12, 23]
    assert [t.hour for t in parse_clock("10:00am – 12:30am")] == [10, 0]


def test_parse_cards():
    events = adapter().parse(LIST_HTML, days=30, today=TODAY)
    by_slug = {e.uid.split("-", 2)[-1].split("@")[0]: e for e in events}
    # Feb 26 is outside the 30-day window.
    assert len(events) == 4

    coffee = events[0]
    assert coffee.title == "Coffee + Connections: PIC Edition!"
    assert coffee.start.isoformat() == "2026-11-17T15:00:00-05:00"
    assert coffee.end.hour == 16
    assert coffee.kind == "social"
    assert coffee.campus == "allston" and not coffee.is_virtual
    assert coffee.uid == "harvard_ilab-coffee-connections-7@harvard-mit-events"

    clinic = events[1]
    assert clinic.is_virtual and clinic.campus == "online"
    assert clinic.kind == "workshop"

    pathways = events[2]
    assert pathways.kind == "lecture"
    assert "Business School" in pathways.address
    assert pathways.topics == ["partner"]

    deadline = events[3]
    assert deadline.kind == "admin"
    assert deadline.end is None
    assert by_slug  # uids are slug-based, stable across runs
