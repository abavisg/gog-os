"""Gmail metadata normalisation — pure function core + thin I/O wrapper.

Entry point: normalise(account, raw_path) or run as
  python -m gogos.gmail.gmail_normalise <account> <raw_json_path>
"""
from __future__ import annotations

import json
import sys
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.paths import latest_alias, storage_path


def _header_value(headers: list[dict], name: str) -> str:
    """Return the first matching header value, or '' if absent."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def _parse_date_utc(date_str: str) -> str:
    """Parse an RFC-2822 Date header and return UTC ISO-8601. Returns '' on failure."""
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def normalise_message(raw: dict, account: str) -> dict:
    """Pure function: raw Gmail metadata record → normalised schema dict."""
    headers: list[dict] = raw.get("headers", [])
    return {
        "id": raw.get("id", ""),
        "thread_id": raw.get("threadId", ""),
        "account": account,
        "from": _header_value(headers, "From"),
        "to": _header_value(headers, "To"),
        "subject": _header_value(headers, "Subject"),
        "date": _parse_date_utc(_header_value(headers, "Date")),
        "snippet": raw.get("snippet", ""),
        "labels": list(raw.get("labelIds", [])),
        "source": "gmail",
    }


def normalise_raw(raw_data: dict) -> dict:
    """Normalise a full raw fetch output dict (as written by gmail_fetch)."""
    account = raw_data.get("account", "")
    messages = raw_data.get("messages", [])
    normalised = [normalise_message(m, account) for m in messages]
    return {
        "account": account,
        "count": len(normalised),
        "messages": normalised,
        "source": "gmail",
    }


def normalise(account: str, raw_path: Path) -> int:
    """I/O wrapper: read raw JSON, normalise, write slim JSON + alias. Returns exit code."""
    try:
        raw_data = json.loads(raw_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read raw file {raw_path}: {exc}", file=sys.stderr)
        return 1

    result = normalise_raw(raw_data)

    # Resolve the alias to its canonical email so every gmail module keys storage
    # off the same directory (see resolve_account); fetch/normalise/triage/apply
    # must all agree regardless of whether an alias or email was passed.
    account = resolve_account(account)
    dated_dir = storage_path("gmail", account, "inbox")
    slim_file = dated_dir / "slim.json"
    slim_file.write_text(json.dumps(result, indent=2))

    alias = latest_alias(dated_dir, "latest-slim.json")
    alias.write_text(json.dumps(result, indent=2))

    print(f"OK  Normalised {result['count']} message(s) to {alias}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python -m gogos.gmail.gmail_normalise <account> <raw_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(normalise(sys.argv[1], Path(sys.argv[2])))
