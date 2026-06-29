"""Calendar brief Markdown + HTML report renderer.

Reads latest-slim.json + brief JSON (from calendar-brief skill) and renders a report.

Entry point:
  python -m gogos.calendar.calendar_report <account> <brief_json_path> <slim_json_path>

Safety: no Calendar API calls, no write-back, no auto-open.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gogos.auth.accounts import resolve_account
from gogos.paths import latest_alias, storage_path

_LOCAL_TZ = ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))


def _now_local() -> str:
    return datetime.now(tz=_LOCAL_TZ).isoformat(timespec="seconds")


def _parse_local(dt_str: str) -> str:
    """Convert UTC ISO-8601 to local time display string, or return date string as-is."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is not None:
            return dt.astimezone(_LOCAL_TZ).strftime("%H:%M")
        return dt_str
    except Exception:
        return dt_str


def _format_time_range(event: dict) -> str:
    if event.get("all_day"):
        return "all day"
    start = _parse_local(event.get("start_datetime_utc", ""))
    dur = event.get("duration_minutes")
    if start and dur:
        return f"{start} ({dur}m)"
    return start or ""


def _attendee_summary(event: dict) -> str:
    count = event.get("attendee_count", 0)
    if count <= 1:
        return ""
    return f"{count} attendees"


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_report(
    brief_data: dict,
    slim_data: dict,
    brief_path: Path,
    slim_path: Path,
    generated_at: str | None = None,
) -> str:
    if generated_at is None:
        generated_at = _now_local()

    account = slim_data.get("account", "unknown")
    period = slim_data.get("period", "")
    events = slim_data.get("events", [])
    event_index = {e["id"]: e for e in events}

    lines: list[str] = []
    lines.append(f"# Calendar Brief — {account} · {period}")
    lines.append(f"")
    lines.append(f"_Generated: {generated_at}_  ")
    lines.append(f"_Sources: {brief_path} · {slim_path}_")
    lines.append("")

    summary = brief_data.get("summary", "")
    if summary:
        lines.append(f"> {summary}")
        lines.append("")

    focus_gaps = brief_data.get("focus_gaps", [])
    if focus_gaps:
        lines.append("## Focus Gaps")
        for gap in focus_gaps:
            lines.append(f"- {gap}")
        lines.append("")

    risks = brief_data.get("risks", [])
    if risks:
        lines.append("## Risks & Conflicts")
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")

    event_briefs = brief_data.get("events", [])
    if event_briefs:
        lines.append("## Events")
        for eb in event_briefs:
            ev = event_index.get(eb.get("id", ""), {})
            title = ev.get("summary") or eb.get("summary", "(No title)")
            time_range = _format_time_range(ev)
            location = ev.get("location", "")
            attendees = _attendee_summary(ev)

            meta_parts = [p for p in [time_range, location, attendees] if p]
            meta = "  ·  ".join(meta_parts) if meta_parts else ""

            lines.append(f"### {title}")
            if meta:
                lines.append(f"_{meta}_")

            prep = eb.get("prep", "")
            if prep:
                lines.append(f"")
                lines.append(f"**Prep:** {prep}")

            notes = eb.get("notes", "")
            if notes:
                lines.append(f"")
                lines.append(f"{notes}")

            lines.append("")
    else:
        lines.append("_No events in this period._")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def render_html_report(
    brief_data: dict,
    slim_data: dict,
    brief_path: Path,
    slim_path: Path,
    generated_at: str | None = None,
) -> str:
    if generated_at is None:
        generated_at = _now_local()

    account = slim_data.get("account", "unknown")
    period = slim_data.get("period", "")
    events = slim_data.get("events", [])
    event_index = {e["id"]: e for e in events}
    date_part = generated_at[:10]

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
        )

    sections: list[str] = []

    summary = brief_data.get("summary", "")
    if summary:
        sections.append(f'<div class="summary"><p>{esc(summary)}</p></div>')

    focus_gaps = brief_data.get("focus_gaps", [])
    if focus_gaps:
        items_html = "".join(f"<li>{esc(g)}</li>" for g in focus_gaps)
        sections.append(f'<section class="panel"><h2>Focus Gaps</h2><ul>{items_html}</ul></section>')

    risks = brief_data.get("risks", [])
    if risks:
        items_html = "".join(f'<li class="risk">{esc(r)}</li>' for r in risks)
        sections.append(f'<section class="panel"><h2>Risks &amp; Conflicts</h2><ul>{items_html}</ul></section>')

    event_briefs = brief_data.get("events", [])
    if event_briefs:
        cards: list[str] = []
        for eb in event_briefs:
            ev = event_index.get(eb.get("id", ""), {})
            title = ev.get("summary") or eb.get("summary", "(No title)")
            time_range = _format_time_range(ev)
            location = ev.get("location", "")
            attendees = _attendee_summary(ev)
            prep = eb.get("prep", "")
            notes = eb.get("notes", "")

            meta_parts = [p for p in [time_range, location, attendees] if p]
            meta_html = "  ·  ".join(esc(p) for p in meta_parts)

            prep_html = f'<div class="prep"><strong>Prep:</strong> {esc(prep)}</div>' if prep else ""
            notes_html = f'<div class="notes">{esc(notes)}</div>' if notes else ""
            has_conf = "🎥 " if ev.get("has_conference") else ""
            recurring = " <span class='recur'>↺</span>" if ev.get("is_recurring") else ""

            cards.append(f"""<div class="event-card">
  <h3>{esc(has_conf)}{esc(title)}{recurring}</h3>
  <div class="meta">{meta_html}</div>
  {prep_html}
  {notes_html}
</div>""")
        sections.append(
            '<section class="panel"><h2>Events</h2>'
            + "\n".join(cards)
            + "</section>"
        )
    else:
        sections.append('<section class="panel"><p><em>No events in this period.</em></p></section>')

    body_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Calendar Brief — {esc(account)} · {esc(period)} · {esc(date_part)}</title>
<style>
  body {{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         margin:0;padding:24px 32px;background:#f8f9fa;color:#202124;}}
  h1   {{font-size:1.4rem;margin-bottom:4px;}}
  .meta-header {{font-size:0.8rem;color:#5f6368;margin-bottom:24px;}}
  .summary {{background:#e8f0fe;border-left:4px solid #1a73e8;
             padding:12px 16px;border-radius:4px;margin-bottom:16px;}}
  .panel {{background:#fff;border-radius:8px;padding:16px 20px;
           margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.12);}}
  h2 {{font-size:1rem;margin:0 0 12px;color:#1a73e8;}}
  h3 {{font-size:0.95rem;margin:0 0 4px;}}
  .event-card {{border-bottom:1px solid #f1f3f4;padding:12px 0;}}
  .event-card:last-child {{border-bottom:none;}}
  .meta {{font-size:0.82rem;color:#5f6368;margin-bottom:6px;}}
  .prep {{font-size:0.85rem;margin-top:6px;color:#1a73e8;}}
  .notes {{font-size:0.85rem;margin-top:4px;color:#5f6368;}}
  .risk {{color:#d93025;}}
  .recur {{color:#9aa0a6;font-size:0.8rem;}}
  ul {{margin:0;padding-left:20px;}}
  li {{margin-bottom:4px;font-size:0.88rem;}}
  footer {{font-size:0.75rem;color:#9aa0a6;margin-top:24px;}}
</style>
</head>
<body>
<h1>Calendar Brief — {esc(account)} · {esc(period)}</h1>
<div class="meta-header">Generated {esc(generated_at)}</div>
{body_html}
<footer>Sources: {esc(str(brief_path))} · {esc(str(slim_path))}</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# I/O entry point
# ---------------------------------------------------------------------------

def report(account: str, brief_path: Path, slim_path: Path) -> int:
    """Read brief + slim JSON, render Markdown + HTML, write to storage. Returns exit code."""
    try:
        brief_data = json.loads(brief_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read brief file {brief_path}: {exc}", file=sys.stderr)
        return 1

    try:
        slim_data = json.loads(slim_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read slim file {slim_path}: {exc}", file=sys.stderr)
        return 1

    generated_at = _now_local()
    md = render_report(brief_data, slim_data, brief_path, slim_path, generated_at)
    html = render_html_report(brief_data, slim_data, brief_path, slim_path, generated_at)

    dated_dir = storage_path("reports", "calendar", resolve_account(account))
    (dated_dir / "calendar-brief.md").write_text(md)
    latest_alias(dated_dir, "latest.md").write_text(md)

    html_file = dated_dir / "calendar-brief.html"
    html_file.write_text(html)
    html_alias = latest_alias(dated_dir, "latest.html")
    html_alias.write_text(html)

    event_count = brief_data.get("event_count", len(brief_data.get("events", [])))
    print(f"OK  Wrote {event_count}-event brief → {html_alias}")

    import subprocess
    subprocess.Popen(["open", "-a", "Google Chrome", str(html_alias)])

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python -m gogos.calendar.calendar_report <account> <brief_json_path> <slim_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(report(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))
