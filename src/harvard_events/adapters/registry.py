"""Adapter lookup by the `type` field in config/sources.yml."""

from __future__ import annotations

from ..config import SourceConfig
from ..http import Fetcher
from ..taxonomy.mapper import UnmappedRecorder
from .artmuseums import ArtMuseumsAdapter
from .base import Adapter
from .gsd import GsdAdapter
from .ics import IcsAdapter
from .localist import LocalistAdapter
from .medialab import MediaLabAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    cls.type_name: cls
    for cls in (
        LocalistAdapter,
        IcsAdapter,
        GsdAdapter,
        ArtMuseumsAdapter,
        MediaLabAdapter,
    )
}


def build_adapter(
    config: SourceConfig, fetcher: Fetcher, recorder: UnmappedRecorder
) -> Adapter:
    try:
        cls = ADAPTERS[config.type]
    except KeyError:
        raise ValueError(
            f"source {config.id}: unknown type {config.type!r}. "
            f"Known types: {', '.join(sorted(ADAPTERS))}"
        ) from None
    return cls(config, fetcher, recorder)
