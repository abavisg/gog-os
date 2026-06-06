"""Gmail triage Markdown report renderer.

Reads latest-triage.json + latest-slim.json and renders a grouped Markdown report.

Entry point:
  python -m gogos.gmail.gmail_report <account> <triage_json_path> <slim_json_path>

Safety: no Gmail API calls, no write-back, no HTML, no auto-open.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gogos.paths import latest_alias, storage_path

_LOCAL_TZ = ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))


def _now_local() -> str:
    return datetime.now(tz=_LOCAL_TZ).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _slim_index(slim_data: dict) -> dict[str, dict]:
    """Return a mapping from message id → slim message dict."""
    return {m["id"]: m for m in slim_data.get("messages", [])}


def render_report(
    triage_data: dict,
    slim_data: dict,
    triage_path: Path,
    slim_path: Path,
    generated_at: str | None = None,
) -> str:
    """Pure function: produce the Markdown report string."""
    if generated_at is None:
        generated_at = _now_local()

    account = triage_data.get("account", "unknown")
    items = triage_data.get("items", [])
    index = _slim_index(slim_data)

    lines: list[str] = []

    # Header
    lines.append(f"# Email Triage Report — {account}")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Triage source: `{triage_path}`")
    lines.append(f"Slim source:   `{slim_path}`")
    lines.append("")

    if not items:
        lines.append("*No messages to triage.*")
        return "\n".join(lines)

    # Group items by category, preserving insertion order
    groups: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "Uncategorised")
        groups.setdefault(cat, []).append(item)

    for category, cat_items in groups.items():
        lines.append(f"## {category} ({len(cat_items)})")
        lines.append("")
        for item in cat_items:
            msg_id = item.get("id", "")
            msg = index.get(msg_id, {})
            sender = msg.get("from") or "*(unknown sender)*"
            subject = msg.get("subject") or "*(no subject)*"
            action = item.get("suggested_action", "")
            confidence = item.get("confidence", 0.0)
            lines.append(f"- **From:** {sender}")
            lines.append(f"  **Subject:** {subject}")
            lines.append(f"  **Action:** {action}")
            lines.append(f"  **Confidence:** {confidence:.0%}")
            lines.append("")

    return "\n".join(lines)


def report(account: str, triage_path: Path, slim_path: Path) -> int:
    """Load inputs, render Markdown, write dated file + alias. Returns exit code."""
    if not triage_path.exists():
        print(
            f"ERROR: triage file not found: {triage_path}",
            file=sys.stderr,
        )
        return 1

    if not slim_path.exists():
        print(
            f"ERROR: slim file not found: {slim_path}",
            file=sys.stderr,
        )
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

    generated_at = _now_local()
    md = render_report(triage_data, slim_data, triage_path, slim_path, generated_at)

    # Path shape: .core/storage/reports/email/<account>/<date>/
    dated_dir = storage_path("reports", "email", account)
    dated_file = dated_dir / "email-report.md"
    dated_file.write_text(md)

    alias = latest_alias(dated_dir, "latest.md")
    alias.write_text(md)

    item_count = len(triage_data.get("items", []))
    print(f"OK  Wrote {item_count}-item report to {alias}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python -m gogos.gmail.gmail_report <account> <triage_json_path> <slim_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(report(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))
