"""Gmail triage Markdown + HTML report renderer.

Reads latest-triage.json + latest-slim.json and renders a grouped report,
topped by a 3-line executive digest (build_digest — Phase 4.6 §4).
Report style is controlled by .core/config/gmail/report.json:
  style: "compact" | "card" | "summary"
  detail_categories: list of category names expanded in "summary" style

Entry point:
  python -m gogos.gmail.gmail_report <account> <triage_json_path> <slim_json_path>

Safety: no Gmail API calls, no write-back. Opens the HTML report in Chrome
unless called with auto_open=False (the scheduled run must never pop a browser).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gogos.auth.accounts import resolve_account
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


def _unsubscribe_href(value: str) -> str:
    """First usable link from a List-Unsubscribe value.

    The header holds comma-separated <...> entries (https and/or mailto).
    Prefer an http(s) URL; fall back to mailto; else empty.
    """
    entries = re.findall(r"<([^>]+)>", value)
    for entry in entries:
        if entry.lower().startswith(("http://", "https://")):
            return entry
    for entry in entries:
        if entry.lower().startswith("mailto:"):
            return entry
    return ""


# ---------------------------------------------------------------------------
# Digest header (Phase 4.6 §4): 3-line executive summary
# ---------------------------------------------------------------------------

_ATTENTION_CATS = ("Action", "Review", "Events")
_QUEUE_CATS = ("Information", "Newsletters", "Safe to Delete")
# Call-outs are derived from our own classifier's rationale strings
# (gmail_classify), so they are deterministic — no re-classification here.
_PROTECTED_HINT = re.compile(r"financial|security|civic|statement|bill|payment|renewal", re.I)
_INVITE_HINT = re.compile(r"invitation", re.I)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def build_digest(triage_data: dict, reconcile_data: dict | None = None) -> list[str]:
    """Executive summary lines for the top of the report (Phase 4.6 §4).

    Line 1 — what needs the user: Action / Review / Events, with call-outs
    (financial/security Actions, Events that are invitations).
    Line 2 — the queue: Information / Newsletters / Safe to Delete counts
    (plus any unknown category, so nothing is silently dropped).
    Line 3 — reconciliation signals: learned rules, rule suggestions,
    unsubscribe candidates.

    At most 3 lines; a line with nothing to say is dropped, never padded.
    Plain text, account-agnostic: /start-day reuses these lines when it
    merges accounts, and Calendar/Task digests will join them (Phases 5–6).
    """
    items = triage_data.get("items", [])
    if not items:
        return []

    counts: dict[str, int] = {}
    protected_actions = 0
    invites = 0
    for item in items:
        cat = item.get("category", "Uncategorised")
        counts[cat] = counts.get(cat, 0) + 1
        rationale = item.get("rationale", "") or ""
        if cat == "Action" and _PROTECTED_HINT.search(rationale):
            protected_actions += 1
        elif cat == "Events" and _INVITE_HINT.search(rationale):
            invites += 1

    lines: list[str] = []

    attention: list[str] = []
    if counts.get("Action"):
        part = f"⚡ {counts['Action']} Action"
        if protected_actions:
            part += f" ({protected_actions} financial/security)"
        attention.append(part)
    if counts.get("Review"):
        attention.append(f"📋 {counts['Review']} Review")
    if counts.get("Events"):
        part = f"📅 {counts['Events']} Events"
        if invites:
            part += f" ({_plural(invites, 'invite')})"
        attention.append(part)
    lines.append(" · ".join(attention) if attention else "✅ Nothing needs action")

    queue: list[str] = []
    other_cats = [c for c in counts if c not in _ATTENTION_CATS and c not in _QUEUE_CATS]
    for cat in (*_QUEUE_CATS, *other_cats):
        n = counts.get(cat, 0)
        if not n:
            continue
        emoji = _cat_prefix(cat).strip()
        part = f"{emoji} {n} {cat}"
        if cat == "Safe to Delete":
            part += " queued"
        queue.append(part)
    if queue:
        lines.append(" · ".join(queue))

    if reconcile_data:
        signals: list[str] = []
        n = len(reconcile_data.get("learned", []))
        if n:
            signals.append(f"🎓 {_plural(n, 'learned rule')}")
        n = len(reconcile_data.get("rescue_suggestions", []))
        if n:
            signals.append(f"💡 {_plural(n, 'rule suggestion')}")
        n = len(reconcile_data.get("unsubscribe_candidates", []))
        if n:
            signals.append(f"🔕 {_plural(n, 'unsubscribe candidate')}")
        if signals:
            lines.append(" · ".join(signals))

    return lines


# ---------------------------------------------------------------------------
# Reconciliation extras (Phase 4.6 §8): learned rules + unsubscribe candidates
# ---------------------------------------------------------------------------

def _render_reconcile_md(reconcile_data: dict) -> list[str]:
    lines: list[str] = []

    learned = reconcile_data.get("learned", [])
    suggestions = reconcile_data.get("rescue_suggestions", [])
    if learned or suggestions:
        lines.append("### 🎓 Learned rules")
        lines.append("")
        for entry in learned:
            lines.append(
                f"- learned: **{entry['sender']}** → {entry['category']} "
                f"({entry['corrections']} corrections) — auto-updated in the "
                "sender ledger; override with a user rule to revert"
            )
        for s in suggestions:
            lines.append(
                f"- suggestion: **{s['sender']}** rescued to inbox "
                f"{s['rescues']}× — consider a user rule in rules.json"
            )
        lines.append("")

    candidates = reconcile_data.get("unsubscribe_candidates", [])
    if candidates:
        lines.append(f"### 🔕 Unsubscribe candidates ({len(candidates)})")
        lines.append("*Never rescued from Safe to Delete / Newsletters — click to unsubscribe yourself; GogOS sends nothing.*")
        lines.append("")
        for c in candidates:
            href = _unsubscribe_href(c.get("unsubscribe", ""))
            label = f"**{c['sender']}** ({c['category']}, {c['message_count']} msg)"
            lines.append(f"- {label} — [unsubscribe]({href})" if href else f"- {label}")
        lines.append("")
    return lines


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
    reconcile_data: dict | None = None,
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

    # Digest header (§4): 3-line executive summary before anything else
    digest = build_digest(triage_data, reconcile_data)
    if digest:
        lines.extend(f"> {d}" for d in digest)
        lines.append("")

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

    # Reconciliation extras: learned rules + unsubscribe candidates
    if reconcile_data:
        lines.extend(_render_reconcile_md(reconcile_data))

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
    reconcile_data: dict | None = None,
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

    # Reconciliation extras: learned rules + unsubscribe candidates
    if reconcile_data:
        extra_rows: list[str] = []
        for entry in reconcile_data.get("learned", []):
            extra_rows.append(
                f'<li>🎓 learned: <strong>{esc(entry["sender"])}</strong> → '
                f'{esc(entry["category"])} ({entry["corrections"]} corrections; '
                f'auto-updated in the sender ledger)</li>'
            )
        for s in reconcile_data.get("rescue_suggestions", []):
            extra_rows.append(
                f'<li>💡 <strong>{esc(s["sender"])}</strong> rescued to inbox '
                f'{s["rescues"]}× — consider a user rule</li>'
            )
        for c in reconcile_data.get("unsubscribe_candidates", []):
            href = _unsubscribe_href(c.get("unsubscribe", ""))
            link = f' — <a href="{esc(href)}">unsubscribe</a>' if href else ""
            extra_rows.append(
                f'<li>🔕 <strong>{esc(c["sender"])}</strong> '
                f'({esc(c["category"])}, {c["message_count"]} msg){link}</li>'
            )
        if extra_rows:
            rows_html = "\n".join(extra_rows)
            sections.append(f"""
<section class="category">
  <h2 style="color:#5f6368">🔁 Reconciliation</h2>
  <p class="meta">Unsubscribe is a link you click yourself — GogOS sends nothing.</p>
  <ul>
{rows_html}
  </ul>
</section>""")

    sections_html = "\n".join(sections) if sections else "<p><em>No messages to triage.</em></p>"
    msg_count = len(items)
    cat_count = len(groups)

    # Digest header (§4): 3-line executive summary before the sections
    digest_lines = build_digest(triage_data, reconcile_data)
    digest_html = ""
    if digest_lines:
        digest_body = "<br>\n".join(esc(d) for d in digest_lines)
        digest_html = f'<div class="digest">\n{digest_body}\n</div>\n'

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
  .digest  {{background:#fff; border-left:4px solid #1a73e8; border-radius:8px;
             padding:12px 16px; margin-bottom:16px; font-size:0.9rem;
             line-height:1.7; box-shadow:0 1px 3px rgba(0,0,0,.12);}}
  footer   {{font-size:0.75rem; color:#9aa0a6; margin-top:24px;}}
</style>
</head>
<body>
<h1>Email Triage — {esc(account)} · {esc(date_part)}</h1>
<div class="meta">{msg_count} messages &nbsp;·&nbsp; {cat_count} categories &nbsp;·&nbsp; generated {esc(generated_at)}</div>
{digest_html}{sections_html}
<footer>Sources: {esc(str(triage_path))} · {esc(str(slim_path))}</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# I/O entry point
# ---------------------------------------------------------------------------

def report(account: str, triage_path: Path, slim_path: Path,
           auto_open: bool = True) -> int:
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

    # Reconciliation extras are optional: absent until /email-reconcile has run.
    reconcile_data: dict | None = None
    reconcile_path = latest_alias(
        storage_path("gmail", resolve_account(account), "reconcile"),
        "latest-reconcile.json")
    if reconcile_path.exists():
        try:
            reconcile_data = _load_json(reconcile_path)
        except (OSError, json.JSONDecodeError):
            reconcile_data = None

    config = _load_report_config()
    generated_at = _now_local()
    md = render_report(triage_data, slim_data, triage_path, slim_path,
                       generated_at, config, reconcile_data)
    html = render_html_report(triage_data, slim_data, triage_path, slim_path,
                              generated_at, config, reconcile_data)

    dated_dir = storage_path("reports", "email", resolve_account(account))

    (dated_dir / "email-report.md").write_text(md)
    latest_alias(dated_dir, "latest.md").write_text(md)

    html_file = dated_dir / "email-report.html"
    html_file.write_text(html)
    html_alias = latest_alias(dated_dir, "latest.html")
    html_alias.write_text(html)

    item_count = len(triage_data.get("items", []))
    style = config.get("style", "compact")
    print(f"OK  Wrote {item_count}-item {style} report → {html_alias}")

    if auto_open:
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
