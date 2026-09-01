"""Loading of every YAML file under ``config/``.

All paths are resolved relative to the project root (see ``paths.py``); nothing
here ever sees an absolute path from the caller.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from .paths import CONFIG_DIR, TAXONOMY_DIR


def _load_yaml(path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if data is not None else ({} if default is None else default)


@dataclass
class SourceConfig:
    id: str
    type: str
    enabled: bool = True
    weight: float = 0.0
    domain: str | None = None
    url: str | None = None
    path: str | None = None
    module: str | None = None
    #: name of the config/taxonomy/<name>.yml file; defaults to the source id.
    #: Two sources on the same Localist instance share one mapping file.
    taxonomy: str | None = None
    campus: str = "other"
    priority: int = 0
    filters: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceConfig":
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in raw.items() if k in known}
        kwargs.setdefault("filters", {})
        kwargs.setdefault("options", {})
        return cls(**kwargs)


@dataclass
class Settings:
    sources: list[SourceConfig]
    subscriptions: dict[str, Any]
    keywords: dict[str, Any]
    scoring: dict[str, Any]
    campus: dict[str, Any]
    busy: dict[str, Any]
    registry: dict[str, Any]

    def source(self, source_id: str) -> SourceConfig | None:
        for src in self.sources:
            if src.id == source_id:
                return src
        return None

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]

    def source_priority(self, source_id: str) -> int:
        src = self.source(source_id)
        return src.priority if src else 0


def load_busy() -> dict[str, Any]:
    """The user's fixed schedule.

    Read from the ``BUSY_SCHEDULE_JSON`` environment variable when set (that is
    how CI injects it, since the file is deliberately kept out of the public
    repo), otherwise from ``config/busy.yml`` for local runs.
    """
    raw = os.environ.get("BUSY_SCHEDULE_JSON", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return yaml.safe_load(raw) or {}
    return _load_yaml(CONFIG_DIR / "busy.yml", {})


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    sources_raw = _load_yaml(CONFIG_DIR / "sources.yml", {}).get("sources", [])
    return Settings(
        sources=[SourceConfig.from_dict(s) for s in sources_raw],
        subscriptions=_load_yaml(CONFIG_DIR / "subscriptions.yml", {}),
        keywords=_load_yaml(CONFIG_DIR / "keywords.yml", {}),
        scoring=_load_yaml(CONFIG_DIR / "scoring.yml", {}),
        campus=_load_yaml(CONFIG_DIR / "campus.yml", {}),
        busy=load_busy(),
        registry=_load_yaml(CONFIG_DIR / "registry.yml", {}),
    )


def load_taxonomy(source_id: str) -> dict[str, Any]:
    """Layer-1 mapping file for one source. Missing file means no mapping."""
    return _load_yaml(TAXONOMY_DIR / f"{source_id}.yml", {})


def reset_cache() -> None:
    load_settings.cache_clear()
