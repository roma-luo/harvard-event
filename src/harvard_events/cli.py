"""Command line interface.

    harvard-events run [--days N] [--mail] [--source ID ...]
    harvard-events preview --source ID [--days 7]
    harvard-events discover <domain> [--path /building_e14]
    harvard-events probe <domain> | --appendix
    harvard-events busy-json
"""

from __future__ import annotations

import argparse
import json
import sys

import yaml

from . import pipeline
from .adapters.localist import discover as localist_discover
from .config import load_settings, reset_cache
from .core.scoring import ScoringContext, score_all
from .http import Fetcher
from .paths import DISCOVERED_DIR, PROJECT_ROOT
from .probe import format_domain_probe, probe_domain, write_probe_results
from .taxonomy.mapper import UnmappedRecorder


def _cmd_run(args: argparse.Namespace) -> int:
    result = pipeline.run(
        days=args.days,
        send_mail=args.mail,
        source_ids=args.source,
        write=True,
    )
    print(
        f"fetched {len(result.events)} events: "
        f"{len(result.priority)} priority, {len(result.others)} all, "
        f"{len(result.exhibitions)} exhibitions, "
        f"{len(result.cancelled)} cancelled, {len(result.dropped)} dropped"
    )
    for row in result.health:
        mark = "ok" if row.ok else "FAIL"
        extra = f" ({row.error})" if row.error else ""
        print(f"  {mark:4} {row.source_id}: {row.count} events{extra}")
    return 0 if all(r.ok for r in result.health) else 1


def _cmd_preview(args: argparse.Namespace) -> int:
    settings = load_settings()
    recorder = UnmappedRecorder()
    with Fetcher() as fetcher:
        events, health = pipeline.fetch_all(
            settings, fetcher, recorder, [args.source], args.days
        )
    ctx = ScoringContext.from_settings(settings)
    score_all(events, ctx)
    events.sort(key=lambda e: e.score, reverse=True)
    row = health[0]
    if not row.ok:
        print(f"source {args.source} failed: {row.error}")
        return 1
    print(f"{args.source}: {len(events)} events in the next {args.days} days\n")
    for e in events:
        sub = e.score_detail.get("subscription_match") or ""
        print(
            f"{e.score:6.1f}  {e.start.strftime('%m-%d %a %H:%M')}  "
            f"{e.kind:<10} {e.access:<10} {e.title[:70]}"
        )
        if sub:
            print(f"        └ 订阅命中: {sub}")
    if row.unmapped:
        print("\n未映射分类（应补进 config/taxonomy/）:")
        for item in row.unmapped:
            print(f"  - {item}")
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    with Fetcher() as fetcher:
        data = localist_discover(fetcher, args.domain, args.path)
    DISCOVERED_DIR.mkdir(parents=True, exist_ok=True)
    name = args.domain + (f"-{args.path.strip('/').replace('/', '_')}" if args.path else "")
    out = DISCOVERED_DIR / f"{name}.yml"
    out.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"scanned {data['events_scanned']} events across {len(data['facets'])} facet groups")
    print(f"written to {out.relative_to(PROJECT_ROOT)}")
    for group, values in data["facets"].items():
        print(f"\n{group} ({len(values)}):")
        for value in values[:15]:
            print(f"  - {value}")
        if len(values) > 15:
            print(f"  … and {len(values) - 15} more in the file")
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    with Fetcher() as fetcher:
        if args.appendix:
            path = write_probe_results(fetcher)
            print(f"wrote {path}")
            return 0
        result = probe_domain(fetcher, args.domain)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_domain_probe(result))
    return 0


def _cmd_busy_json(args: argparse.Namespace) -> int:
    """Print config/busy.yml as one line of JSON, for the BUSY_SCHEDULE_JSON secret."""
    from .paths import CONFIG_DIR

    data = yaml.safe_load((CONFIG_DIR / "busy.yml").read_text(encoding="utf-8"))
    print(json.dumps(data, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harvard-events")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="full pipeline: fetch, score, write ICS, mail on Sunday")
    p.add_argument("--days", type=int, default=None, help="lookahead window (default: config)")
    p.add_argument("--mail", action="store_true", help="send the weekly email regardless of weekday")
    p.add_argument("--source", action="append", default=None, help="limit to source id(s)")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("preview", help="show what one source would contribute, no writes")
    p.add_argument("--source", required=True)
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(func=_cmd_preview)

    p = sub.add_parser("discover", help="dump a Localist instance's full vocabulary")
    p.add_argument("domain")
    p.add_argument("--path", default=None, help="sub-channel path, e.g. /building_e14")
    p.set_defaults(func=_cmd_discover)

    p = sub.add_parser("probe", help="sniff a domain's platform, or re-run the appendix checks")
    p.add_argument("domain", nargs="?", default=None)
    p.add_argument("--appendix", action="store_true", help="rewrite PROBE_RESULTS.md")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_probe)

    p = sub.add_parser("busy-json", help="print busy.yml as JSON for the CI secret")
    p.set_defaults(func=_cmd_busy_json)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "probe" and not (args.appendix or args.domain):
        print("probe needs a domain, or --appendix", file=sys.stderr)
        return 2
    reset_cache()
    return args.func(args)
