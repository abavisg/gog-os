"""Gmail undo — reverse the most recent move batch back into the inbox.

Undo is the exact inverse of gmail_apply's "move": for each message that was
moved, REMOVE the GSD/<category> label and ADD the INBOX label back. This
un-archives the message and returns it to the inbox, undoing the move.

Safety invariants (enforced in code, mirror-image of gmail_apply):
  * The ONLY label ever removed is a GSD/* destination label.
  * The ONLY label ever added is INBOX.
  * TRASH / SPAM are never added or removed; no delete/trash API is called.
  * Undo reads the applied-result file written by gmail_apply, so it reverses
    exactly the messages that actually moved — never a proposal, never a guess.

Entry points:
  build_undo(account)             -> undo plan derived from latest applied result
  apply_undo(account, plan, svc)  -> result dict

  python -m gogos.gmail.gmail_undo <account>          (reverse latest applied batch)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from gogos.auth.accounts import resolve_account
from gogos.gmail.gmail_apply import (
    _FORBIDDEN,
    _approvals_dir,
    _is_gsd_destination,
)

# The only label undo is ever allowed to ADD (the inverse of archive).
_ADDABLE = {"INBOX"}


# ---------------------------------------------------------------------------
# Safety-critical core (inverse of gmail_apply._assert_safe)
# ---------------------------------------------------------------------------

def _assert_safe_undo(add_label_ids: list[str], remove_label_ids: list[str],
                      label_id_to_name: dict[str, str]) -> None:
    """Hard gate. Raise unless a modify call would do nothing but un-move.

    Un-move = remove a GSD/<Category> label, add INBOX. Nothing else is allowed.
    """
    add_names = {label_id_to_name.get(lid, lid) for lid in add_label_ids}
    remove_names = {label_id_to_name.get(lid, lid) for lid in remove_label_ids}

    # Never touch TRASH/SPAM in either direction.
    touched = add_names | remove_names | set(add_label_ids) | set(remove_label_ids)
    forbidden_hit = touched & _FORBIDDEN
    if forbidden_hit:
        raise AssertionError(
            f"SAFETY: refusing to touch forbidden label(s) {forbidden_hit}. "
            "Undo never deletes, trashes, or marks spam."
        )

    # Only ever add INBOX.
    bad_adds = add_names - _ADDABLE
    if bad_adds:
        raise AssertionError(
            f"SAFETY: refusing to add label(s) {bad_adds}. "
            "Undo may only add INBOX (un-archive)."
        )

    # Only ever remove GSD/<Category> destinations.
    bad_removes = {n for n in remove_names if not _is_gsd_destination(n)}
    if bad_removes:
        raise AssertionError(
            f"SAFETY: refusing to remove non-GSD label(s) {bad_removes}."
        )


def _modify_undo(service, message_id: str,
                 add_label_ids: list[str], remove_label_ids: list[str],
                 label_id_to_name: dict[str, str]) -> None:
    """The ONLY path to the Gmail mutation API for undo. Gated by _assert_safe_undo."""
    _assert_safe_undo(add_label_ids, remove_label_ids, label_id_to_name)
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": add_label_ids, "removeLabelIds": remove_label_ids},
    ).execute()


# ---------------------------------------------------------------------------
# Undo plan
# ---------------------------------------------------------------------------

def load_applied(account: str) -> dict:
    """Read the latest applied-result file written by gmail_apply.apply_plan."""
    account = resolve_account(account)
    path = _approvals_dir(account) / "gmail-applied.json"
    return json.loads(path.read_text())


def build_undo(account: str, *, applied: dict | None = None) -> dict:
    """Build an undo plan from the latest applied result. Does NOT touch Gmail."""
    account = resolve_account(account)
    if applied is None:
        applied = load_applied(account)

    reversals = [
        {"id": mv["id"], "category": mv["category"], "label_name": mv["label_name"]}
        for mv in applied.get("moves", [])
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "action": "undo-move",  # remove GSD/<category>, add INBOX
        "reversals": reversals,
        "categories": sorted({r["category"] for r in reversals}),
    }


# ---------------------------------------------------------------------------
# Applying the undo
# ---------------------------------------------------------------------------

def apply_undo(account: str, plan: dict, service) -> dict:
    """Reverse an applied move batch: for each message remove GSD/<cat>, add INBOX.

    Resolves GSD label names to ids up front and aborts (raising) if a label the
    batch used is missing — never partially applies. Never deletes.
    """
    from gogos.gmail.gmail_apply import fetch_label_map

    label_map = fetch_label_map(service)
    label_id_to_name = {v: k for k, v in label_map.items()}

    needed = {r["label_name"] for r in plan.get("reversals", [])}
    missing = sorted(n for n in needed if n not in label_map)
    if missing:
        raise ValueError(
            "Missing Gmail label(s): " + ", ".join(missing)
            + ". Cannot undo a move whose destination label no longer exists."
        )

    # apply_undo does not resolve the account (mirror of gmail_apply.apply_plan):
    # the plan already carries resolved ids; account is used only for the result.
    reversed_ids, failed = [], []
    for r in plan.get("reversals", []):
        label_id = label_map[r["label_name"]]
        try:
            _modify_undo(
                service, r["id"],
                add_label_ids=["INBOX"],
                remove_label_ids=[label_id],
                label_id_to_name=label_id_to_name,
            )
            reversed_ids.append(r["id"])
        except Exception as exc:  # noqa: BLE001 — report, continue
            failed.append({"id": r["id"], "error": str(exc)})

    return {
        "account": account,
        "reversed_count": len(reversed_ids),
        "failed_count": len(failed),
        "reversed_ids": reversed_ids,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _service(account: str):
    from googleapiclient.discovery import build

    from gogos.auth.google_auth import get_credentials

    resolved = resolve_account(account)
    creds = get_credentials(resolved)
    return build("gmail", "v1", credentials=creds)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m gogos.gmail.gmail_undo <account>", file=sys.stderr)
        sys.exit(1)

    acct = sys.argv[1]
    try:
        undo_plan = build_undo(acct)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"ERROR: no applied batch to undo for '{acct}': {exc}. "
            f"Run /email-apply {acct} first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not undo_plan["reversals"]:
        print("OK  Nothing to undo (last applied batch moved 0 messages).")
        sys.exit(0)

    result = apply_undo(acct, undo_plan, _service(acct))
    print(
        f"OK  Reversed {result['reversed_count']} move(s) back to inbox; "
        f"{result['failed_count']} failed."
    )
    sys.exit(0 if result["failed_count"] == 0 else 1)
