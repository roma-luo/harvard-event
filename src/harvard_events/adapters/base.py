"""What every adapter must provide."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..config import SourceConfig
from ..http import Fetcher
from ..models import Event
from ..taxonomy.mapper import Mapper, UnmappedRecorder

EASTERN = ZoneInfo("America/New_York")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_eastern(value: datetime) -> datetime:
    """Every timestamp in the pipeline is tz-aware and in America/New_York.

    Naive input is assumed to already be local Boston time, which is what the
    ICS feeds without a TZID mean.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=EASTERN)
    return value.astimezone(EASTERN)


class Adapter:
    """Base class. Subclasses implement ``fetch``."""

    #: ``type`` value in config/sources.yml that selects this adapter
    type_name: str = ""

    def __init__(
        self,
        config: SourceConfig,
        fetcher: Fetcher,
        recorder: UnmappedRecorder | None = None,
    ):
        self.config = config
        self.fetcher = fetcher
        self.mapper = Mapper(config.taxonomy or config.id, recorder, report_as=config.id)

    @property
    def source_id(self) -> str:
        return self.config.id

    def make_uid(self, source_event_id: str | int) -> str:
        """Stable UID derived from the source's own event id.

        Never a hash of title+time: a rescheduled event must keep its UID so
        Outlook updates the existing entry instead of adding a second one.
        """
        return f"{self.source_id}-{source_event_id}@harvard-mit-events"

    def fetch(self, days: int) -> list[Event]:
        raise NotImplementedError
