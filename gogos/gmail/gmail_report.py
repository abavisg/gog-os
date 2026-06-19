"""Gmail triage Markdown + HTML report renderer.

Reads latest-triage.json + latest-slim.json and renders a grouped report.
Report style is controlled by .core/config/gmail/report.json:
  style: "compact" | "card" | "summary"
  detail_categories: list of category names expanded in "summary" style

Entry point:
  python -m gogos.gmail.gmail_report <account> <triage_json_path> <slim_json_path>

Safety: no Gmail API calls, no write-back, no auto-open.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gogos.paths import latest_alias, storage_path

_LOCAL_TZ = ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))
_REPORT_CONFIG_PATH = Path(__file__).parents[2] / ".core/config/gmail/report.json"

# Category display metadata: emoji + short label
_CAT_META: dict[str, tuple[str, str]] = {
    "Action":        ("⚡", "Action"),
    "Review":        ("📋", "Review"),
    "Events":        ("📅", "Events"),
    "Information":   ("ℹ️ ", "Information"),
    "Newsletters":   ("📰", "Newsletters"),
    "Safe to Delete": ("🗑 ", "Safe to Delete"),
}
_DEFAULT_EMOJI = "•"


def _now_local() -> str:
    return datetime.now(tz=_LOCAL_TZ).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _load_report_config() -> dict:
    if _REPORT_CONFIG_PATH.exists():
        try:
            return json.loads(_REPORT_CONFIG_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {"style": "compact", "detail_categories": ["Action", "Events"]}


def _slim_index(slim_data: dict) -> dict[str, dict]:
    return {m["id"]: m for m in slim_data.get("messages", [])}


def _sender_short(sender: str) -> str:
    """Extract a readable short name: display name or local part of address."""
    m = re.match(r'^"?([^"<]+?)"?\s*<', sender)
    if m:
        return m.group(1).strip()
    m = re.match(r'^([^@]+)@', sender)
    if m:
        return m.group(1).strip()
    return sender.strip() or "*(unknown sender)*"


def _date_short(iso: str) -> str:
    """Format ISO-8601 date as 'DD Mon HH:MM'."""
    try:
        dt = datetime.fromisoformat(iso).astimezone(_LOCAL_TZ)
        return dt.strftime("%-d %b %H:%M")
    except (ValueError, OSError):
        return iso[:10] if iso else ""


def _cat_prefix(category: str) -> str:
    emoji, _ = _CAT_META.get(category, (_DEFAULT_EMOJI, category))
    return emoji


# ---------------------------------------------------------------------------
# Style: compact
# One line per email in Action/Review/Events; name-run for the rest.
# ---------------------------------------------------------------------------

def _render_compact(
    groups: dict[str, list[dict]],
    index: dict[str, dict],
) -> list[str]:
    lines: list[str] = []
    collapsed_cats = {"Newsletters", "Safe to Delete", "Information"}

    for category, items in groups.items():
        emoji = _cat_prefix(category)
        lines.append(f"### {emoji} {category} ({len(items)})")
        if category in collapsed_cats:
            names = []
            for item in items:
                msg = index.get(item.get("id", ""), {})
                names.append(_sender_short(msg.get("from", "") or ""))
            lines.append("  " + " · ".join(names))
            lines.append("")
        else:
            lines.append("")
            for item in items:
                msg = index.get(item.get("id", ""), {})
                sender = _sender_short(msg.get("from", "") or "*(unknown sender)*")
                subject = msg.get("subject") or "*(no subject)*"
                action = item.get("suggested_action", "")
                sender_col = f"{sender:<24}"
                lines.append(f"  {sender_col}  {subject}")
                if action:
                    lines.append(f"  {'':24}  → {action}")
                lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Style: card
# Small block per email: sender + date, subject, → action
# ---------------------------------------------------------------------------

def _render_card(
    groups: dict[str, list[dict]],
    index: dict[str, dict],
) -> list[str]:
    lines: list[str] = []
    for category, items in groups.items():
        emoji = _cat_prefix(category)
        lines.append(f"### {emoji} {category} ({len(items)})")
        lines.append("")
        for item in items:
            msg = index.get(item.get("id", ""), {})
            sender = _sender_short(msg.get("from", "") or "*(unknown sender)*")
            subject = msg.get("subject") or "*(no subject)*"
            date = _date_short(msg.get("date", ""))
            action = item.get("suggested_action", "")
            lines.append(f"**{sender}** · {date}")
            lines.append(subject)
            if action:
                lines.append(f"→ {action}")
            lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Style: summary
# Count table up top; detail_categories expanded; rest collapsed.
# ---------------------------------------------------------------------------

def _render_summary(
    groups: dict[str, list[dict]],
    index: dict[str, dict],
    detail_categories: list[str],
) -> list[str]:
    lines: list[str] = []

    # Count table
    lines.append("| Category | # |")
    lines.append("|---|---|")
    for category, items in groups.items():
        emoji = _cat_prefix(category)
        lines.append(f"| {emoji} {category} | {len(items)} |")
    lines.append("")

    # Expanded sections
    for category in detail_categories:
        items = groups.get(category, [])
        if not items:
            continue
        emoji = _cat_prefix(category)
        lines.append(f"{'─' * 42}")
        lines.append(f"{emoji} **{category}**")
        lines.append(f"{'─' * 42}")
        lines.append("")
        for item in items:
            msg = index.get(item.get("id", ""), {})
            sender = _sender_short(msg.get("from", "") or "*(unknown sender)*")
            subject = msg.get("subject") or "*(no subject)*"
            action = item.get("suggested_action", "")
            lines.append(f"• **{sender}** — {subject}")
            if action:
                lines.append(f"  → {action}")
        lines.append("")

    # Collapsed remainder
    collapsed = [c for c in groups if c not in detail_categories]
    if collapsed:
        parts = [f"{c} ({len(groups[c])})" for c in collapsed]
        lines.append(f"{'─' * 42}")
        lines.append(", ".join(parts))
        lines.append(f"{'─' * 42}")
    return lines


# ---------------------------------------------------------------------------
# Public render entry point
# ---------------------------------------------------------------------------

def render_report(
    triage_data: dict,
    slim_data: dict,
    triage_path: Path,
    slim_path: Path,
    generated_at: str | None = None,
    config: dict | None = None,
) -> str:
    if generated_at is None:
        generated_at = _now_local()
    if config is None:
        config = _load_report_config()

    style = config.get("style", "compact")
    detail_categories = config.get("detail_categories", ["Action", "Events"])

    account = triage_data.get("account", "unknown")
    items = triage_data.get("items", [])
    index = _slim_index(slim_data)

    lines: list[str] = []

    # Header
    date_part = generated_at[:10]
    lines.append(f"# Email Triage — {account} · {date_part}")
    lines.append("")

    if not items:
        lines.append("*No messages to triage.*")
        lines.append("")
        lines.append(f"Generated: {generated_at}")
        lines.append(f"Sources: `{triage_path}` · `{slim_path}`")
        return "\n".join(lines)

    # Group by category
    groups: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "Uncategorised")
        groups.setdefault(cat, []).append(item)

    msg_word = "message" if len(items) == 1 else "messages"
    lines.append(f"{len(items)} {msg_word} · {len(groups)} categories · style: `{style}`")
    lines.append("")

    if style == "card":
        lines.extend(_render_card(groups, index))
    elif style == "summary":
        lines.extend(_render_summary(groups, index, detail_categories))
    else:
        lines.extend(_render_compact(groups, index))

    # Footer
    lines.append("")
    lines.append("---")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Sources: `{triage_path}` · `{slim_path}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

_CAT_COLORS: dict[str, str] = {
    "Action":          "#d93025",
    "Review":          "#1a73e8",
    "Events":          "#188038",
    "Information":     "#e37400",
    "Newsletters":     "#7627bb",
    "Safe to Delete":  "#80868b",
}
_DEFAULT_COLOR = "#5f6368"


def render_html_report(
    triage_data: dict,
    slim_data: dict,
    triage_path: Path,
    slim_path: Path,
    generated_at: str | None = None,
    config: dict | None = None,
) -> str:
    if generated_at is None:
        generated_at = _now_local()
    if config is None:
        config = _load_report_config()

    account = triage_data.get("account", "unknown")
    items = triage_data.get("items", [])
    index = _slim_index(slim_data)
    date_part = generated_at[:10]

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
        )

    groups: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "Uncategorised")
        groups.setdefault(cat, []).append(item)

    sections: list[str] = []
    for category, cat_items in groups.items():
        emoji, _ = _CAT_META.get(category, (_DEFAULT_EMOJI, category))
        color = _CAT_COLORS.get(category, _DEFAULT_COLOR)
        rows: list[str] = []
        for item in cat_items:
            msg = index.get(item.get("id", ""), {})
            sender = esc(_sender_short(msg.get("from", "") or ""))
            subject = esc(msg.get("subject") or "(no subject)")
            date = esc(_date_short(msg.get("date", "")))
            action = esc(item.get("suggested_action", ""))
            action_row = f'<td class="action">→ {action}</td>' if action else '<td class="action"></td>'
            rows.append(
                f'<tr><td class="sender">{sender}</td>'
                f'<td class="date">{date}</td>'
                f'<td class="subject">{subject}</td>'
                f'{action_row}</tr>'
            )
        rows_html = "\n".join(rows)
        sections.append(f"""
<section class="category">
  <h2 style="color:{color}">{emoji} {esc(category)} <span class="count">({len(cat_items)})</span></h2>
  <table>
    <thead><tr>
      <th>From</th><th>Date</th><th>Subject</th><th>Action</th>
    </tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
</section>""")

    sections_html = "\n".join(sections) if sections else "<p><em>No messages to triage.</em></p>"
    msg_count = len(items)
    cat_count = len(groups)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Email Triage — {esc(account)} · {esc(date_part)}</title>
<style>
  body {{font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; padding: 24px 32px; background: #f8f9fa; color: #202124;}}
  h1   {{font-size: 1.4rem; margin-bottom: 4px; color: #202124;}}
  .meta {{font-size: 0.8rem; color: #5f6368; margin-bottom: 24px;}}
  section.category {{background:#fff; border-radius:8px; padding:16px 20px;
                     margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.12);}}
  h2   {{font-size: 1rem; margin: 0 0 12px; display:flex; align-items:center; gap:6px;}}
  .count {{font-weight:400; color:#5f6368;}}
  table {{border-collapse:collapse; width:100%; font-size:0.85rem;}}
  th   {{text-align:left; padding:4px 8px; border-bottom:1px solid #e8eaed;
         color:#5f6368; font-weight:500;}}
  td   {{padding:6px 8px; border-bottom:1px solid #f1f3f4; vertical-align:top;}}
  tr:last-child td {{border-bottom:none;}}
  .sender {{white-space:nowrap; font-weight:500; width:16%;}}
  .date   {{white-space:nowrap; color:#5f6368; width:10%;}}
  .subject {{width:42%;}}
  .action  {{color:#1a73e8; width:32%; font-style:italic;}}
  footer   {{font-size:0.75rem; color:#9aa0a6; margin-top:24px;}}
</style>
</head>
<body>
<h1>Email Triage — {esc(account)} · {esc(date_part)}</h1>
<div class="meta">{msg_count} messages &nbsp;·&nbsp; {cat_count} categories &nbsp;·&nbsp; generated {esc(generated_at)}</div>
{sections_html}
<footer>Sources: {esc(str(triage_path))} · {esc(str(slim_path))}</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# I/O entry point
# ---------------------------------------------------------------------------

def report(account: str, triage_path: Path, slim_path: Path) -> int:
    if not triage_path.exists():
        print(f"ERROR: triage file not found: {triage_path}", file=sys.stderr)
        return 1
    if not slim_path.exists():
        print(f"ERROR: slim file not found: {slim_path}", file=sys.stderr)
        return 1

    try:
        triage_data = _load_json(triage_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read triage file {triage_path}: {exc}", file=sys.stderr)
        return 1

    try:
        slim_data = _load_json(slim_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read slim file {slim_path}: {exc}", file=sys.stderr)
        return 1

    config = _load_report_config()
    generated_at = _now_local()
    md = render_report(triage_data, slim_data, triage_path, slim_path, generated_at, config)
    html = render_html_report(triage_data, slim_data, triage_path, slim_path, generated_at, config)

    dated_dir = storage_path("reports", "email", account)

    (dated_dir / "email-report.md").write_text(md)
    latest_alias(dated_dir, "latest.md").write_text(md)

    html_file = dated_dir / "email-report.html"
    html_file.write_text(html)
    html_alias = latest_alias(dated_dir, "latest.html")
    html_alias.write_text(html)

    item_count = len(triage_data.get("items", []))
    style = config.get("style", "compact")
    print(f"OK  Wrote {item_count}-item {style} report → {html_alias}")

    import subprocess
    subprocess.Popen(["open", "-a", "Google Chrome", str(html_alias)])

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python -m gogos.gmail.gmail_report <account> <triage_json_path> <slim_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(report(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))
