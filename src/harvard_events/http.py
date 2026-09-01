"""Polite HTTP client shared by every adapter.

Rules from the plan's appendix B: obey robots.txt, at least 1 second between
requests to the same host, and put a contact address in the User-Agent.
"""

from __future__ import annotations

import time
import urllib.robotparser
from typing import Any
from urllib.parse import urlparse

import httpx

CONTACT_EMAIL = "ma_luo@gsd.harvard.edu"
USER_AGENT = (
    "harvard-mit-events/0.1 (personal calendar aggregator; "
    f"contact {CONTACT_EMAIL})"
)

MIN_INTERVAL_SECONDS = 1.0
DEFAULT_TIMEOUT = 30.0

_last_request_at: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _throttle(host: str) -> None:
    now = time.monotonic()
    last = _last_request_at.get(host)
    if last is not None:
        wait = MIN_INTERVAL_SECONDS - (now - last)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[host] = time.monotonic()


def _robots(client: httpx.Client, scheme: str, host: str):
    if host in _robots_cache:
        return _robots_cache[host]
    parser = urllib.robotparser.RobotFileParser()
    try:
        resp = client.get(f"{scheme}://{host}/robots.txt", timeout=10.0)
        if resp.status_code == 200:
            parser.parse(resp.text.splitlines())
        else:
            parser.parse([])
    except httpx.HTTPError:
        parser = None
    _robots_cache[host] = parser
    return parser


class Fetcher:
    """A throttled, robots-aware HTTP getter."""

    def __init__(self, *, respect_robots: bool = True, timeout: float = DEFAULT_TIMEOUT):
        self.respect_robots = respect_robots
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=timeout,
            follow_redirects=True,
        )

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        parser = _robots(self._client, parsed.scheme or "https", parsed.netloc)
        if parser is None:
            return True
        return parser.can_fetch(USER_AGENT, url)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        parsed = urlparse(url)
        _throttle(parsed.netloc)
        return self._client.get(url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = self.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        resp = self.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text
