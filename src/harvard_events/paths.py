"""Project-relative path resolution.

Every path in this project is derived from the project root, which is itself
derived from this file's location. No absolute path is ever hard-coded.
The ``HME_ROOT`` environment variable can override the root (used by CI when
the checkout lives somewhere else).
"""

from __future__ import annotations

import os
from pathlib import Path

# src/harvard_events/paths.py -> src/harvard_events -> src -> <project root>
_DERIVED_ROOT = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(os.environ.get("HME_ROOT", _DERIVED_ROOT)).resolve()

CONFIG_DIR = PROJECT_ROOT / "config"
TAXONOMY_DIR = CONFIG_DIR / "taxonomy"
DOCS_DIR = PROJECT_ROOT / "docs"
STATE_DIR = PROJECT_ROOT / "state"
LOGS_DIR = PROJECT_ROOT / "logs"
DISCOVERED_DIR = PROJECT_ROOT / "discovered"
CACHE_DIR = PROJECT_ROOT / ".cache"

SEEN_FILE = STATE_DIR / "seen.json"
UNMAPPED_LOG = LOGS_DIR / "unmapped.log"
SCORING_LOG = LOGS_DIR / "scoring.jsonl"
HEALTH_FILE = STATE_DIR / "health.json"

PRIORITY_ICS = DOCS_DIR / "priority.ics"
ALL_ICS = DOCS_DIR / "all.ics"


def ensure_dirs() -> None:
    """Create the writable directories the pipeline needs."""
    for d in (DOCS_DIR, STATE_DIR, LOGS_DIR, DISCOVERED_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
