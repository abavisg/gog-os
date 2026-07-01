"""Sender-consistency ledger — same sender, same category, every run (Phase 4.6 §3).

A local ledger at `.core/storage/gmail/<account>/sender-ledger.json` records
`sender-domain -> category` decisions. Once a sender is ledgered, later runs
(and later messages in the same run) reuse that category instead of
re-deriving it, so a sender can never drift between categories silently.

Two deliberate — never silent — ways an entry changes:
  * A user rule matches the sender (rules are authoritative; the entry is
    rewritten to the rule's category, source "user-rule").
  * The config fingerprint (rules.json + classify.json) changed since the
    ledger was written: the whole ledger re-learns this run — built-in
    decisions overwrite entries, and every change is logged to stderr.

PROTECTED MAIL IS NEVER LEDGERED. Financial/security/civic/real-person mail
is classified fresh per message (see gmail_classify.is_protected): pinning a
bank to one category would route a statement (Action) like an app notice
(Information). The consistency guarantee therefore covers the non-protected
tail — exactly the mail the ledger exists to keep stable.

Entry points:
  load_ledger(account) / save_ledger(account, ledger)
  config_fingerprint()             -> hash of rules.json + classify.json
  lookup(ledger, sender)           -> pinned category or None
  record(ledger, sender, category, source) -> mutates ledger, logs changes

The ledger file is storage, not config: dated storage conventions don't apply
because it is a single evolving fact-table per account, not a daily artefact.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.paths import STORAGE_ROOT

from gogos.gmail.gmail_rules import RULES_PATH

_CLASSIFY_CONFIG_PATH = RULES_PATH.parent / "classify.json"


def ledger_path(account: str) -> Path:
    return STORAGE_ROOT / "gmail" / resolve_account(account) / "sender-ledger.json"


def config_fingerprint() -> str:
    """Hash of the classification config (user rules + sender lists).

    A changed fingerprint is the explicit re-learn signal: ledger pins are
    recomputed rather than enforced, and changes are logged.
    """
    digest = hashlib.sha256()
    for path in (RULES_PATH, _CLASSIFY_CONFIG_PATH):
        digest.update(path.read_bytes() if path.exists() else b"<absent>")
    return digest.hexdigest()


def empty_ledger() -> dict:
    return {"fingerprint": config_fingerprint(), "senders": {}}


def load_ledger(account: str) -> dict:
    """Load the account's ledger; a missing/corrupt file starts a fresh one."""
    path = ledger_path(account)
    if not path.exists():
        return empty_ledger()
    try:
        ledger = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"WARN  ledger: cannot parse {path}: {exc} — starting fresh",
              file=sys.stderr)
        return empty_ledger()
    ledger.setdefault("fingerprint", "")
    ledger.setdefault("senders", {})
    return ledger


def save_ledger(account: str, ledger: dict) -> Path:
    path = ledger_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger["fingerprint"] = config_fingerprint()
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(ledger, indent=2))
    return path


def needs_relearn(ledger: dict) -> bool:
    """True when config changed since the ledger was written -> re-learn run."""
    return ledger["fingerprint"] != config_fingerprint()


def lookup(ledger: dict, sender: str) -> str | None:
    """The pinned category for a sender, or None if the sender is new."""
    entry = ledger["senders"].get(sender)
    return entry["category"] if entry else None


def record(ledger: dict, sender: str, category: str, source: str) -> None:
    """Record a decision. A changed category is logged — never a silent drift."""
    if not sender:
        return
    now = datetime.now(timezone.utc).isoformat()
    entry = ledger["senders"].get(sender)
    if entry is None:
        ledger["senders"][sender] = {
            "category": category, "source": source,
            "first_seen": now, "updated_at": now,
        }
        return
    if entry["category"] != category:
        print(
            f"INFO  ledger: re-learned {sender}: "
            f"{entry['category']} → {category} ({source})",
            file=sys.stderr,
        )
        entry.update(category=category, source=source, updated_at=now)
