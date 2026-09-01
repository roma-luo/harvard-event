"""Art Museums adapter tests with a stubbed fetcher."""

from __future__ import annotations

from harvard_events.adapters.artmuseums import ArtMuseumsAdapter
from harvard_events.config import SourceConfig

EXHIBITIONS_HTML = """
<article class="flex flex-col items-center justify-center md:flex-row py-10 border-b">
  <div class="flex flex-col max-w-lg justify-end text-xl">
    <a class="group border-0" href="https://harvardartmuseums.org/exhibitions/6763/intro">
      <span class="exhibition-row__type text-2xl block">Current</span>
      <h2 class="exhibition-row__title"><span>Introduction to the History of Art</span></h2>
      <p class="exhibition-row__meta text-sm">
        <time>August 29, 2026&ndash;January 3, 2027</time><br />
        University Teaching Gallery, Harvard Art Museums
      </p>
      <p>An installation accompanying a Harvard course.</p>
    </a>
  </div>
</article>
<article class="flex flex-col items-center justify-center md:flex-row py-10 border-b">
  <div class="flex flex-col max-w-lg justify-end text-xl">
    <a class="group border-0" href="https://harvardartmuseums.org/exhibitions/9999/old-show">
      <span class="exhibition-row__type text-2xl block">Past</span>
      <h2 class="exhibition-row__title"><span>A Past Show</span></h2>
      <p class="exhibition-row__meta text-sm">
        <time>January 1, 2020&ndash;March 1, 2020</time><br />
        Harvard Art Museums
      </p>
      <p>Long gone.</p>
    </a>
  </div>
</article>
"""

CALENDAR_HTML = "<html><body>var initialEvents = [].concat([]);</body></html>"


class FakeFetcher:
    def get_text(self, url: str, **kwargs) -> str:
        if "exhibitions" in url:
            return EXHIBITIONS_HTML
        return CALENDAR_HTML


def adapter() -> ArtMuseumsAdapter:
    return ArtMuseumsAdapter(
        SourceConfig(id="harvard_art_museums", type="artmuseums",
                     campus="cambridge_harvard"),
        FakeFetcher(),
    )


def test_current_exhibition_is_parsed():
    events = adapter().fetch(21)
    assert len(events) == 1
    show = events[0]
    assert show.kind == "exhibition"
    assert show.all_day
    assert show.title == "Introduction to the History of Art"
    assert show.uid == "harvard_art_museums-6763@harvard-mit-events"
    assert show.start.strftime("%Y-%m-%d") == "2026-08-29"
    assert show.end.strftime("%Y-%m-%d") == "2027-01-03"
    assert "University Teaching Gallery" in show.location
    assert show.url.endswith("/exhibitions/6763/intro")


def test_past_exhibition_is_skipped():
    events = adapter().fetch(21)
    assert all("Past Show" not in e.title for e in events)
