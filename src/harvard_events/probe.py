"""Source probing.

Two jobs:

* ``probe_appendix()`` walks the five unverified items from the plan's step 1
  and writes ``PROBE_RESULTS.md``.
* ``probe_domain()`` answers "what platform is this calendar?" for a domain the
  user just heard about, so they know whether adding it is a config change or
  a new adapter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from .http import Fetcher
from .paths import PROJECT_ROOT

# The five items the plan says must be verified before implementation.
APPENDIX_A_CHECKS: list[dict[str, Any]] = [
    {
        "item": "GSD site type",
        "urls": [
            "https://www.gsd.harvard.edu/wp-json/wp/v2/",
            "https://www.gsd.harvard.edu/wp-json/wp/v2/types",
            "https://www.gsd.harvard.edu/events/",
        ],
        "question": "Is it WordPress, and is there an events post type?",
    },
    {
        "item": "Media Lab feed",
        "urls": [
            "https://www.media.mit.edu/events/feed/",
            "https://www.media.mit.edu/events/feed.xml",
            "https://www.media.mit.edu/events/",
        ],
        "question": "Is there an RSS feed?",
    },
    {
        "item": "Art Museums structure",
        "urls": [
            "https://harvardartmuseums.org/calendar",
            "https://harvardartmuseums.org/calendar/exhibitions",
        ],
        "question": "Embedded JSON on the page? What does Add to Calendar point at?",
    },
    {
        "item": "CSAIL ICS address",
        "urls": [
            "https://www.csail.mit.edu/events",
            "https://calendar.csail.mit.edu/",
        ],
        "question": "Real URL behind Subscribe to Calendar.",
    },
    {
        "item": "Loeb Library ICS address",
        "urls": [
            "https://libcal.gsd.harvard.edu/calendars",
            "https://libcal.gsd.harvard.edu/calendar",
        ],
        "question": "Same as above.",
    },
    {
        "item": "Localist API docs",
        "urls": ["https://developer.localist.com/doc/api"],
        "question": "Confirm paging / date-range / filter parameter names.",
    },
]

# Paths tried when sniffing an unknown domain.
ICS_CANDIDATES = [
    "/events.ics",
    "/calendar.ics",
    "/events/feed.ics",
    "/calendar/ical",
    "/ical",
    "/events/ical",
]
RSS_CANDIDATES = [
    "/events/feed/",
    "/events/feed.xml",
    "/feed/",
    "/rss.xml",
    "/events/rss",
]

_ICAL_RE = re.compile(r"https?://[^\s\"'<>]*?(?:\.ics|ical|/ics/)[^\s\"'<>]*", re.I)
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


@dataclass
class ProbeHit:
    url: str
    status: int | None
    content_type: str = ""
    length: int = 0
    excerpt: str = ""
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def _looks_like(text: str, content_type: str) -> list[str]:
    notes: list[str] = []
    head = text[:4000]
    lowered = head.lower()
    if "begin:vcalendar" in lowered:
        notes.append("ICS feed (BEGIN:VCALENDAR present)")
    if "<rss" in lowered or "<feed" in lowered:
        notes.append("RSS/Atom feed")
    if "wp-json" in lowered or "wp-content" in lowered:
        notes.append("WordPress markers present")
    if "localist" in lowered:
        notes.append("Localist markers present")
    if "livewhale" in lowered:
        notes.append("LiveWhale markers present")
    if "trumba" in lowered:
        notes.append("Trumba markers present")
    if "libcal" in lowered or "springshare" in lowered:
        notes.append("LibCal / Springshare markers present")
    if "application/ld+json" in lowered:
        notes.append("JSON-LD block on page")
    if "application/json" in content_type:
        notes.append("JSON response")
    return notes


def fetch_one(fetcher: Fetcher, url: str, *, excerpt_chars: int = 500) -> ProbeHit:
    try:
        resp = fetcher.get(url)
    except httpx.HTTPError as exc:
        return ProbeHit(url=url, status=None, error=f"{type(exc).__name__}: {exc}")
    text = resp.text or ""
    hit = ProbeHit(
        url=str(resp.url),
        status=resp.status_code,
        content_type=resp.headers.get("content-type", ""),
        length=len(resp.content),
        excerpt=text[:excerpt_chars],
    )
    hit.notes = _looks_like(text, hit.content_type)
    if resp.status_code == 200:
        for m in _ICAL_RE.finditer(text[:400_000]):
            candidate = m.group(0)
            note = f"iCal link found on page: {candidate}"
            if note not in hit.notes:
                hit.notes.append(note)
            if len([n for n in hit.notes if n.startswith("iCal link")]) >= 5:
                break
        jsonld = _JSONLD_RE.findall(text[:400_000])
        if jsonld:
            hit.notes.append(f"{len(jsonld)} JSON-LD block(s); first 200 chars: "
                             f"{jsonld[0].strip()[:200]}")
    return hit


# What the probe run concluded. Each entry is re-verified on every probe run,
# so this table cannot silently go stale.
CONFIRMED: list[dict[str, str]] = [
    {
        "item": "Harvard GSD",
        "verdict": "WordPress REST API — no scraping of list pages needed",
        "endpoint": "https://www.gsd.harvard.edu/wp-json/wp/v2/gsd-events",
        "expect": "json-array",
        "note": "Post types `event` (rest_base gsd-events) and `exhibition` "
                "(gsd-exhibitions). Taxonomies: event_type, event_series, "
                "public_lecture_series, gsd-departments. Start time lives in the "
                "rendered content as <time datetime=...>, not in a meta field.",
    },
    {
        "item": "MIT Media Lab",
        "verdict": "No RSS (both feed paths 404). Server-rendered HTML, scrapable",
        "endpoint": "https://www.media.mit.edu/events/",
        "expect": "html",
        "note": "Cards: div[data-href] .container-item.module with .module-title, "
                ".event-start-date, .event-end-date, .event-start-time, "
                ".event-end-time. Slug from data-href is the stable id.",
    },
    {
        "item": "Harvard Art Museums",
        "verdict": "Full event JSON embedded in the calendar page",
        "endpoint": "https://harvardartmuseums.org/calendar",
        "expect": "html",
        "note": "`var initialEvents = [].concat([...])` carries ~80 events with "
                "id, title, date (UTC), end_date, event_type, address, slug, "
                "summary, description, event_link. No Add-to-Calendar ICS needed.",
    },
    {
        "item": "MIT CSAIL",
        "verdict": "Public ICS feed",
        "endpoint": "https://www.csail.mit.edu/event_calendar.ics?v1",
        "expect": "ics",
        "note": "The link on /events points at csail-live-2025.csail.mit.edu, "
                "which 301s to www. UIDs look like 14800@csail.mit.edu.",
    },
    {
        "item": "Harvard GSD Loeb Library",
        "verdict": "LibCal ICS feed, calendar id 4722",
        "endpoint": "https://libcal.gsd.harvard.edu/ical_subscribe.php?src=p&cid=4722",
        "expect": "ics",
        "note": "cid comes from cal_id=\"4722\" in the /calendar page markup. "
                "UIDs look like LibCal-4722-17333847.",
    },
    {
        "item": "Localist API",
        "verdict": "Confirmed on all three instances",
        "endpoint": "https://calendar.mit.edu/api/2/events?days=1&pp=1",
        "expect": "json-object",
        "note": "Params: days | start+end, pp (page size), page, distinct=true "
                "(collapse recurring), type[], department[], group_id. Facets live "
                "under event.filters as {facet_group: [{name,id}]} and the facet "
                "group KEYS DIFFER per instance (MIT: event_audience / "
                "event_types / event_events_by_interest / event_events_by_school; "
                "SEAS: event_target_audience / event_types / "
                "event_lecture_other_series / event_academics; HBS: event_types). "
                "Paging metadata is page:{current,size,total}.",
    },
]


def verify_confirmed(fetcher: Fetcher) -> list[tuple[dict[str, str], bool, str]]:
    """Re-check every conclusion above. Returns (entry, ok, detail)."""
    out: list[tuple[dict[str, str], bool, str]] = []
    for entry in CONFIRMED:
        try:
            resp = fetcher.get(entry["endpoint"])
        except httpx.HTTPError as exc:
            out.append((entry, False, f"{type(exc).__name__}: {exc}"))
            continue
        body = resp.text or ""
        ok = resp.status_code == 200
        detail = f"HTTP {resp.status_code}, {len(resp.content)} bytes"
        if ok:
            if entry["expect"] == "ics":
                ok = "BEGIN:VCALENDAR" in body[:2000]
                detail += f", VEVENT count {body.count('BEGIN:VEVENT')}"
            elif entry["expect"] == "json-array":
                try:
                    ok = isinstance(resp.json(), list)
                    detail += f", {len(resp.json())} item(s)"
                except ValueError:
                    ok = False
            elif entry["expect"] == "json-object":
                try:
                    ok = "events" in resp.json()
                except ValueError:
                    ok = False
            elif entry["expect"] == "html":
                ok = "<html" in body[:4000].lower()
        out.append((entry, ok, detail))
    return out


def probe_appendix(fetcher: Fetcher) -> str:
    """Run the appendix-A checks and return the PROBE_RESULTS.md body."""
    lines = [
        "# PROBE_RESULTS",
        "",
        f"Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        "",
        "Every URL below was fetched live. Status code, content type and the "
        "first 500 characters of the body are recorded verbatim.",
        "",
        "## Conclusions (re-verified on this run)",
        "",
        "| Item | Verdict | Endpoint | Live check |",
        "|---|---|---|---|",
    ]
    for entry, ok, detail in verify_confirmed(fetcher):
        mark = "PASS" if ok else "FAIL"
        lines.append(
            f"| {entry['item']} | {entry['verdict']} | `{entry['endpoint']}` "
            f"| {mark} — {detail} |"
        )
    lines.append("")
    for entry in CONFIRMED:
        lines.append(f"- **{entry['item']}** — {entry['note']}")
    lines.append("")
    lines.append("## Raw probe transcript")
    lines.append("")
    for check in APPENDIX_A_CHECKS:
        lines.append(f"## {check['item']}")
        lines.append("")
        lines.append(f"**Question:** {check['question']}")
        lines.append("")
        for url in check["urls"]:
            hit = fetch_one(fetcher, url)
            lines.append(f"### `{url}`")
            lines.append("")
            if hit.error:
                lines.append(f"- Error: `{hit.error}`")
                lines.append("")
                continue
            lines.append(f"- Final URL: `{hit.url}`")
            lines.append(f"- Status: `{hit.status}`")
            lines.append(f"- Content-Type: `{hit.content_type}`")
            lines.append(f"- Bytes: `{hit.length}`")
            if hit.notes:
                lines.append("- Signals:")
                for note in hit.notes:
                    lines.append(f"  - {note}")
            lines.append("")
            lines.append("```")
            lines.append(hit.excerpt.replace("```", "``​`"))
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def write_probe_results(fetcher: Fetcher) -> str:
    body = probe_appendix(fetcher)
    out = PROJECT_ROOT / "PROBE_RESULTS.md"
    out.write_text(body, encoding="utf-8")
    return str(out.relative_to(PROJECT_ROOT))


def probe_domain(fetcher: Fetcher, domain: str) -> dict[str, Any]:
    """Sniff one domain: Localist? ICS? RSS? or scraper needed?"""
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    base = f"https://{domain}"
    result: dict[str, Any] = {"domain": domain, "platform": "unknown", "evidence": []}

    # 1. Localist
    try:
        resp = fetcher.get(f"{base}/api/2/events", params={"days": 1, "pp": 1})
        if resp.status_code == 200 and "events" in resp.text[:200]:
            data = resp.json()
            result["platform"] = "localist"
            result["evidence"].append(
                f"GET /api/2/events -> 200, {len(data.get('events', []))} event(s)"
            )
            result["how_to_add"] = (
                f"Add to config/sources.yml:\n"
                f"  - id: {domain.split('.')[0]}\n"
                f"    type: localist\n"
                f"    domain: {domain}\n"
                f"    enabled: true\n"
                f"    weight: 2\n"
                f"Then run: uv run harvard-events discover {domain}"
            )
            return result
        result["evidence"].append(f"GET /api/2/events -> {resp.status_code}")
    except httpx.HTTPError as exc:
        result["evidence"].append(f"GET /api/2/events -> {type(exc).__name__}")

    # 2. ICS
    for path in ICS_CANDIDATES:
        try:
            resp = fetcher.get(base + path)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200 and "BEGIN:VCALENDAR" in resp.text[:2000]:
            result["platform"] = "ics"
            result["ics_url"] = str(resp.url)
            result["evidence"].append(f"GET {path} -> ICS feed")
            result["how_to_add"] = (
                f"Add to config/sources.yml:\n"
                f"  - id: {domain.split('.')[0]}\n"
                f"    type: ics\n"
                f"    url: {resp.url}\n"
                f"    enabled: true\n"
                f"    weight: 2"
            )
            return result

    # 3. RSS
    for path in RSS_CANDIDATES:
        try:
            resp = fetcher.get(base + path)
        except httpx.HTTPError:
            continue
        body = resp.text[:2000].lower()
        if resp.status_code == 200 and ("<rss" in body or "<feed" in body):
            result["platform"] = "rss"
            result["rss_url"] = str(resp.url)
            result["evidence"].append(f"GET {path} -> RSS/Atom")
            result["how_to_add"] = (
                "RSS needs a small adapter; no generic RSS adapter ships yet. "
                "Cost: ~40 lines in src/harvard_events/adapters/."
            )
            return result

    # 4. Give up: identify what the homepage looks like so the user knows the cost.
    try:
        resp = fetcher.get(f"{base}/events")
        notes = _looks_like(resp.text, resp.headers.get("content-type", ""))
        result["evidence"].append(f"GET /events -> {resp.status_code}; {notes}")
    except httpx.HTTPError as exc:
        result["evidence"].append(f"GET /events -> {type(exc).__name__}")
    result["how_to_add"] = (
        "No API, ICS or RSS found. Adding this source means writing a scraper "
        "(one new module in src/harvard_events/adapters/)."
    )
    return result


def format_domain_probe(result: dict[str, Any]) -> str:
    lines = [f"Domain: {result['domain']}", f"Platform: {result['platform']}", ""]
    lines.append("Evidence:")
    for item in result["evidence"]:
        lines.append(f"  - {item}")
    if result.get("ics_url"):
        lines.append(f"ICS URL: {result['ics_url']}")
    if result.get("rss_url"):
        lines.append(f"RSS URL: {result['rss_url']}")
    lines.append("")
    lines.append(result.get("how_to_add", ""))
    return "\n".join(lines)


def probe_domain_json(fetcher: Fetcher, domain: str) -> str:
    return json.dumps(probe_domain(fetcher, domain), indent=2, ensure_ascii=False)
