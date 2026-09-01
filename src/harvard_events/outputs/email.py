"""The weekly digest email.

Sent Sunday evening, covering the coming 7 days. Five fixed sections; an empty
section keeps its heading and says 无 — a silently-shrinking email is how a
dead scraper goes unnoticed, so the health section is mandatory and the email
goes out even when zero events were found.

Credentials come from the environment (GitHub Secrets in CI):
``SMTP_HOST``, ``SMTP_USER``, ``SMTP_PASS``, ``MAIL_TO``; optional
``SMTP_PORT`` (default 465, SSL) and ``MAIL_FROM`` (default: SMTP_USER).
The body is always written to ``logs/weekly_email.txt`` as well, so a run
without credentials still produces something inspectable.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText

from ..models import Event, SourceHealth
from ..paths import LOGS_DIR

ACCESS_PREFIX = {"open": "[开放] ", "check": "[需确认] ", "restricted": "[受限] "}


@dataclass
class Digest:
    """Everything the five sections need, collected by the pipeline."""

    priority: list[Event] = field(default_factory=list)
    others: list[Event] = field(default_factory=list)
    deadline_events: list[Event] = field(default_factory=list)
    exhibitions: list[Event] = field(default_factory=list)
    cancelled: list[Event] = field(default_factory=list)
    health: list[SourceHealth] = field(default_factory=list)
    consecutive_failures: dict[str, int] = field(default_factory=dict)
    week_start: datetime | None = None


def _fmt_time(event: Event) -> str:
    start = event.start.strftime("%m-%d %a %H:%M")
    if event.end:
        return f"{start}–{event.end.strftime('%H:%M')}"
    return start


def _event_line(event: Event, *, verbose: bool) -> str:
    prefix = ACCESS_PREFIX.get(event.access, "")
    line = f"* {_fmt_time(event)}｜{prefix}{event.title}"
    if verbose:
        extras = []
        if event.series:
            extras.append(f"系列 {event.series}")
        if event.location:
            extras.append(event.location)
        if event.url:
            extras.append(event.url)
        if extras:
            line += "\n    " + "｜".join(extras)
    return line


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"■ {title}", *(lines or ["无"]), ""]


def render_body(digest: Digest) -> str:
    week = digest.week_start or datetime.now()
    parts: list[str] = [
        f"Harvard + MIT 活动周报（{week.strftime('%Y-%m-%d')} 起 7 天）",
        "",
    ]
    parts += _section(
        "本周必看",
        [_event_line(e, verbose=True) for e in digest.priority],
    )
    parts += _section(
        "本周其他",
        [_event_line(e, verbose=False) for e in digest.others],
    )
    parts += _section(
        "报名截止在本周",
        [
            f"* 截止 {e.registration_deadline.isoformat()}｜"
            f"{e.start.strftime('%m-%d')} 开始｜{e.title}"
            + (f"\n    报名：{e.registration_url}" if e.registration_url else "")
            for e in digest.deadline_events
        ],
    )
    parts += _section(
        "在展中的展览",
        [
            f"* {e.title}（至 "
            f"{(e.end or e.start).strftime('%Y-%m-%d')}）"
            + (f"\n    {e.url}" if e.url else "")
            for e in digest.exhibitions
        ],
    )
    health_lines = []
    ok = sum(1 for h in digest.health if h.ok)
    health_lines.append(f"来源状态：{ok}/{len(digest.health)} 正常。")
    for h in digest.health:
        if h.ok:
            continue
        streak = digest.consecutive_failures.get(h.source_id, 1)
        line = f"* {h.source_id} 抓取失败"
        if streak > 1:
            line += f"，已连续 {streak} 周"
        if h.error:
            line += f"：{h.error}"
        health_lines.append(line)
    for h in digest.health:
        for item in h.unmapped:
            health_lines.append(f"* {h.source_id} 出现未映射分类：{item}")
        if h.filtered_out:
            health_lines.append(
                f"* {h.source_id} 被规则过滤 {h.filtered_out} 条（例会每周去重）"
            )
    if digest.cancelled:
        health_lines.append("本周被取消/下线的活动：")
        for e in digest.cancelled:
            health_lines.append(f"* {_fmt_time(e)}｜{e.title}")
    parts += _section("来源健康状态", health_lines)
    return "\n".join(parts)


def render_subject(digest: Digest) -> str:
    week = digest.week_start or datetime.now()
    return f"活动周报 {week.strftime('%Y-%m-%d')}（必看 {len(digest.priority)} 条）"


def send_email(subject: str, body: str) -> bool:
    """Send via SMTP from env credentials. Returns False when not configured."""
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    mail_to = os.environ.get("MAIL_TO", "").strip()
    if not (host and user and password and mail_to):
        return False
    port = int(os.environ.get("SMTP_PORT", "465"))
    mail_from = os.environ.get("MAIL_FROM", user).strip()
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = mail_from
    msg["To"] = mail_to
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(user, password)
            smtp.send_message(msg)
    return True


def deliver(digest: Digest) -> tuple[bool, str]:
    """Render, archive to logs/, and send when credentials exist."""
    subject, body = render_subject(digest), render_body(digest)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / "weekly_email.txt").write_text(
        f"Subject: {subject}\n\n{body}", encoding="utf-8"
    )
    return send_email(subject, body), subject
