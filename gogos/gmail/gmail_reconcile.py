"""Reconciliation loop — learn from manual moves, surface unsubscribe (Phase 4.6 §8 v1b–v1d).

The classifier is fire-and-forget: it never sees you overrule it by dragging a
message elsewhere. Reconciliation closes that loop. It compares each applied
message's CURRENT Gmail labels against where the classifier filed it (recorded
at apply time by gmail_apply). The delta is your manual move:

  filed GSD/X, now carries GSD/Y  -> correction to Y (you re-filed it)
  filed GSD/X, now back in INBOX  -> rescue (you pulled it back)

Three consumers, all local:
  * v1b  Correction counts per sender, persisted in
         `.core/storage/gmail/<account>/reconcile-state.json`, keyed by message
         id so re-running reconcile never double-counts.
  * v1c  Auto-learn: after AUTO_LEARN_THRESHOLD (=3, pinned) distinct
         corrections of a sender to the same category, the sender ledger is
         updated (source "learned") — logged in the reconcile artefact and the
         report, reversible by a user rule or by editing the ledger. Pure
         rescues to INBOX are counted but never auto-learned: no GSD category
         means "leave it in the inbox", and pinning Review would re-archive
         mail you deliberately pulled back — repeated rescues are surfaced as
         a user-rule suggestion instead.
  * v1d  Unsubscribe candidates: senders carrying List-Unsubscribe whose mail
         sits in Safe to Delete / Newsletters and whom you have NEVER rescued
         from those categories. The report shows the link; you click it —
         no write-back, no new scope.

Privacy and safety:
  * Reads label sets only (messages.get format="minimal"; only labelIds are
    used) — no body, no headers, nothing new stored beyond label names.
  * NEVER mutates Gmail. The only writes are local: reconcile state, the
    dated reconcile artefact, and (on auto-learn) the sender ledger.
  * Auto-learn cannot make protected mail deletable: protected mail ignores
    ledger pins entirely (see gmail_classify / gmail_ledger, slice 3).
  * A batch reversed by /email-undo is marked undone_at and skipped here:
    GogOS restored INBOX itself, so those are not user corrections.

Entry points:
  detect_corrections(applied, current_labels)      -> list of corrections (pure)
  record_corrections(state, corrections)           -> newly recorded (pure)
  auto_learn(state, ledger)                        -> learned entries (pure-ish)
  unsubscribe_candidates(slim, triage, state)      -> candidates (pure)
  reconcile(account[, service])                    -> exit code (I/O wrapper)

  python -m gogos.gmail.gmail_reconcile <account>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.gmail import gmail_ledger
from gogos.gmail.gmail_classify import _domain
from gogos.paths import STORAGE_ROOT, latest_alias, storage_path

# Pinned in the Phase 4.6 scope lock: corrections of one sender to one category
# before the ledger auto-learns it.
AUTO_LEARN_THRESHOLD = 3

_GSD_PREFIX = "GSD/"
# Categories a sender must be "never rescued" from to qualify for unsubscribe.
_UNSUB_CATEGORIES = {"Safe to Delete", "Newsletters"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# v1b — detect corrections (pure)
# ---------------------------------------------------------------------------

def detect_corrections(applied: dict,
                       current_labels: dict[str, list[str] | None]) -> list[dict]:
    """Compare applied moves against current label sets -> corrections.

    `current_labels` maps message id -> list of label NAMES, or None when the
    message no longer exists (user deleted it — their call, not a correction).
    A batch marked undone_at yields nothing: those restorations were GogOS's.
    """
    if applied.get("undone_at"):
        return []

    corrections = []
    for move in applied.get("moves", []):
        labels = current_labels.get(move["id"])
        if labels is None:
            continue  # message gone — never learn from a deletion
        label_set = set(labels)
        filed = move["label_name"]

        other_gsd = {
            name.removeprefix(_GSD_PREFIX)
            for name in label_set
            if name.startswith(_GSD_PREFIX) and name != filed
        }
        rescued = "INBOX" in label_set

        if not other_gsd and not rescued:
            # Still where we filed it — or the filed label was removed with no
            # destination (archived, unlabelled): ambiguous, learn nothing.
            continue

        # Re-filed to another GSD category wins over a plain rescue: it names
        # the category the user actually wanted.
        to = sorted(other_gsd)[0] if other_gsd else "INBOX"
        corrections.append({
            "id": move["id"],
            "sender": _domain(move.get("from", "")),
            "from_category": move["category"],
            "to": to,
            "detected_at": _utcnow(),
        })
    return corrections


# ---------------------------------------------------------------------------
# Reconcile state (per-account, keyed by message id => idempotent)
# ---------------------------------------------------------------------------

def state_path(account: str) -> Path:
    return STORAGE_ROOT / "gmail" / resolve_account(account) / "reconcile-state.json"


def load_state(account: str) -> dict:
    path = state_path(account)
    if not path.exists():
        return {"corrections": {}}
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"WARN  reconcile: cannot parse {path}: {exc} — starting fresh",
              file=sys.stderr)
        return {"corrections": {}}
    state.setdefault("corrections", {})
    return state


def save_state(account: str, state: dict) -> Path:
    path = state_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utcnow()
    path.write_text(json.dumps(state, indent=2))
    return path


def record_corrections(state: dict, corrections: list[dict]) -> list[dict]:
    """Record corrections keyed by message id; return only the NEW ones.

    A message id already recorded is skipped, so re-running reconcile over the
    same applied batch never double-counts a correction.
    """
    new = []
    for c in corrections:
        if c["id"] in state["corrections"]:
            continue
        state["corrections"][c["id"]] = {
            k: c[k] for k in ("sender", "from_category", "to", "detected_at")
        }
        new.append(c)
    return new


def sender_counts(state: dict) -> dict[str, dict[str, int]]:
    """{sender: {to_category_or_INBOX: distinct corrected-message count}}."""
    counts: dict[str, dict[str, int]] = {}
    for rec in state["corrections"].values():
        if not rec["sender"]:
            continue
        per = counts.setdefault(rec["sender"], {})
        per[rec["to"]] = per.get(rec["to"], 0) + 1
    return counts


def _rescued_senders(state: dict) -> set[str]:
    """Senders with any correction OUT of Safe to Delete / Newsletters."""
    return {
        rec["sender"]
        for rec in state["corrections"].values()
        if rec["sender"] and rec["from_category"] in _UNSUB_CATEGORIES
    }


# ---------------------------------------------------------------------------
# v1c — auto-learn into the sender ledger
# ---------------------------------------------------------------------------

def auto_learn(state: dict, ledger: dict) -> tuple[list[dict], list[dict]]:
    """Apply the pinned threshold -> (learned, rescue_suggestions).

    learned: senders re-pinned in the ledger (source "learned") because the
    user corrected them to the same GSD category >= AUTO_LEARN_THRESHOLD times.
    rescue_suggestions: senders rescued to INBOX >= threshold times — surfaced
    for a user rule, never auto-pinned (see module docstring).
    Mutates `ledger`; the caller persists it.
    """
    learned, suggestions = [], []
    for sender, per in sorted(sender_counts(state).items()):
        for to, count in sorted(per.items()):
            if count < AUTO_LEARN_THRESHOLD:
                continue
            if to == "INBOX":
                suggestions.append({"sender": sender, "rescues": count})
                continue
            if gmail_ledger.lookup(ledger, sender) == to:
                continue  # already learned on an earlier run
            gmail_ledger.record(ledger, sender, to, source="learned")
            learned.append({"sender": sender, "category": to, "corrections": count})
    return learned, suggestions


# ---------------------------------------------------------------------------
# v1d — unsubscribe candidates (pure)
# ---------------------------------------------------------------------------

def unsubscribe_candidates(slim: dict, triage: dict, state: dict) -> list[dict]:
    """Senders safe to surface an unsubscribe link for.

    Candidate = sender with a List-Unsubscribe value whose mail is filed in
    Safe to Delete / Newsletters and who was NEVER rescued from those
    categories. A rescued sender is excluded — reconciliation re-learns it
    instead of suggesting you kill it.
    """
    category_by_id = {i["id"]: i["category"] for i in triage.get("items", [])}
    rescued = _rescued_senders(state)

    by_sender: dict[str, dict] = {}
    for msg in slim.get("messages", []):
        sender = _domain(msg.get("from", ""))
        category = category_by_id.get(msg.get("id", ""))
        if not sender or category not in _UNSUB_CATEGORIES:
            continue
        entry = by_sender.setdefault(
            sender, {"sender": sender, "category": category,
                     "unsubscribe": "", "message_count": 0})
        entry["message_count"] += 1
        if not entry["unsubscribe"] and msg.get("unsubscribe"):
            entry["unsubscribe"] = msg["unsubscribe"]

    return [
        entry for sender, entry in sorted(by_sender.items())
        if entry["unsubscribe"] and sender not in rescued
    ]


# ---------------------------------------------------------------------------
# Current labels via Gmail (read-only; labelIds only)
# ---------------------------------------------------------------------------

def fetch_current_labels(service, message_ids: list[str]) -> dict[str, list[str] | None]:
    """Current label NAMES per message id; None for messages that are gone.

    Read-only: messages.get(format="minimal") and labels.list. Only labelIds
    are consumed — no headers, no snippet, no body is ever stored.
    """
    from gogos.gmail.gmail_apply import fetch_label_map

    id_to_name = {v: k for k, v in fetch_label_map(service).items()}
    out: dict[str, list[str] | None] = {}
    for mid in message_ids:
        try:
            msg = (service.users().messages()
                   .get(userId="me", id=mid, format="minimal").execute())
        except Exception:  # noqa: BLE001 — deleted/inaccessible message
            out[mid] = None
            continue
        out[mid] = [id_to_name.get(lid, str(lid)) for lid in msg.get("labelIds", [])]
    return out


# ---------------------------------------------------------------------------
# I/O wrapper + CLI
# ---------------------------------------------------------------------------

def _load_latest(account: str, kind: str, filename: str) -> dict:
    path = latest_alias(storage_path("gmail", account, kind), filename)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_latest_applied(account: str) -> dict:
    """The most recent applied batch across ALL approval dates.

    Unlike gmail_undo.load_applied (deliberately today-only: undo reverses the
    batch you just applied), corrections show up days after an apply — so
    reconcile scans approvals/<account>/<date>/ newest-first.
    """
    root = STORAGE_ROOT / "approvals" / resolve_account(account)
    if not root.exists():
        return {}
    for dated in sorted(root.iterdir(), reverse=True):
        path = dated / "gmail-applied.json"
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def reconcile(account: str, service=None) -> int:
    """Full reconcile pass: detect -> record -> learn -> candidates -> artefact."""
    account = resolve_account(account)
    applied = load_latest_applied(account)

    state = load_state(account)

    new_corrections: list[dict] = []
    if applied.get("moves") and not applied.get("undone_at"):
        if service is None:
            service = _service(account)
        ids = [m["id"] for m in applied["moves"]]
        current = fetch_current_labels(service, ids)
        new_corrections = record_corrections(state, detect_corrections(applied, current))

    ledger = gmail_ledger.load_ledger(account)
    learned, suggestions = auto_learn(state, ledger)
    if learned:
        gmail_ledger.save_ledger(account, ledger)

    slim = _load_latest(account, "inbox", "latest-slim.json")
    triage = _load_latest(account, "triage", "latest-triage.json")
    candidates = unsubscribe_candidates(slim, triage, state)

    save_state(account, state)

    artefact = {
        "generated_at": _utcnow(),
        "account": account,
        "new_corrections": new_corrections,
        "sender_counts": sender_counts(state),
        "learned": learned,
        "rescue_suggestions": suggestions,
        "unsubscribe_candidates": candidates,
    }
    dated_dir = storage_path("gmail", account, "reconcile")
    (dated_dir / "reconcile.json").write_text(json.dumps(artefact, indent=2))
    alias = latest_alias(dated_dir, "latest-reconcile.json")
    alias.write_text(json.dumps(artefact, indent=2))

    print(
        f"OK  Reconciled: {len(new_corrections)} new correction(s), "
        f"{len(learned)} learned, {len(suggestions)} rescue suggestion(s), "
        f"{len(candidates)} unsubscribe candidate(s) → {alias}"
    )
    return 0


def _service(account: str):
    from googleapiclient.discovery import build

    from gogos.auth.google_auth import get_credentials

    creds = get_credentials(resolve_account(account))
    return build("gmail", "v1", credentials=creds)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m gogos.gmail.gmail_reconcile <account>", file=sys.stderr)
        sys.exit(1)
    sys.exit(reconcile(sys.argv[1]))
