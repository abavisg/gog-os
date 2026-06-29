"""Gmail triage JSON writer — persists triage output from the email-triage skill.

Reads triage JSON from stdin (or a file path argument) and writes it to the
dated storage path plus a latest-triage.json alias.

Entry point:
  python -m gogos.gmail.gmail_triage <account>          (reads stdin)
  python -m gogos.gmail.gmail_triage <account> <file>   (reads file)

Safety: read-only Gmail scopes. No write-back to Gmail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.paths import latest_alias, storage_path

_REQUIRED_KEYS = {"generated_at", "account", "items"}
_ITEM_REQUIRED_KEYS = {"id", "category", "confidence", "rationale", "suggested_action"}


def validate_triage(data: dict) -> None:
    """Raise ValueError if the triage JSON does not match the expected schema."""
    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"Triage JSON missing required keys: {missing}")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Triage JSON 'items' must be a list")
    for i, item in enumerate(items):
        item_missing = _ITEM_REQUIRED_KEYS - set(item.keys())
        if item_missing:
            raise ValueError(f"Item {i} missing required keys: {item_missing}")


def write_triage(account: str, triage_data: dict) -> int:
    """Validate and persist triage data. Returns exit code (0 = success)."""
    try:
        validate_triage(triage_data)
    except ValueError as exc:
        print(f"ERROR: invalid triage JSON: {exc}", file=sys.stderr)
        return 1

    # Resolve the alias to its canonical email so every gmail module keys storage
    # off the same directory; fetch/normalise/triage/apply must all agree.
    account = resolve_account(account)
    dated_dir = storage_path("gmail", account, "triage")
    dated_file = dated_dir / "triage.json"
    dated_file.write_text(json.dumps(triage_data, indent=2))

    alias = latest_alias(dated_dir, "latest-triage.json")
    alias.write_text(json.dumps(triage_data, indent=2))

    item_count = len(triage_data.get("items", []))
    print(f"OK  Wrote {item_count} triage item(s) to {alias}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python -m gogos.gmail.gmail_triage <account> [triage_json_path]",
            file=sys.stderr,
        )
        sys.exit(1)

    account = sys.argv[1]

    if len(sys.argv) >= 3:
        src = Path(sys.argv[2])
        try:
            raw = src.read_text()
        except OSError as exc:
            print(f"ERROR: cannot read {src}: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        raw = sys.stdin.read()

    try:
        triage_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(write_triage(account, triage_data))
