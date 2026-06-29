"""Gmail write-back — move triaged emails into GSD/<Category> folders.

"Move to folder" in Gmail = add the GSD/<Category> label AND remove the INBOX
label (archive). Archived is NOT deleted: the message stays searchable and can
be dragged back. This module NEVER deletes, trashes, or marks spam.

Safety invariants (enforced in code, not just convention):
  * The ONLY label ever added is a GSD/* destination label.
  * The ONLY label ever removed is INBOX.
  * TRASH / SPAM are never added or removed; no delete/trash API is called.
  * Application is two-step: build_plan writes a proposal, apply_plan runs it
    only after the caller has obtained explicit user approval.

Entry points:
  build_plan(account)            -> proposal dict (also written to approvals/)
  apply_plan(account, plan, svc) -> result dict

  python -m gogos.gmail.gmail_apply <account> plan     (build + write proposal)
  python -m gogos.gmail.gmail_apply <account> apply    (apply approved proposal)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.paths import STORAGE_ROOT, latest_alias, storage_path

# The parent folder under which all destination labels live.
_GSD_PREFIX = "GSD"

# Labels GogOS is allowed to add: exactly the GSD destinations, derived from the
# triage categories config. Anything outside this set is rejected.
_GSD_CATEGORIES = {
    "Action",
    "Events",
    "Information",
    "Newsletters",
    "Review",
    "Safe to Delete",
}

# The only label GogOS is ever allowed to remove (this is what "archive" means).
_REMOVABLE = {"INBOX"}

# Labels that must never be added or removed under any circumstance.
_FORBIDDEN = {"TRASH", "SPAM"}


def gsd_label_name(category: str) -> str:
    """Map a triage category to its full nested Gmail label name."""
    return f"{_GSD_PREFIX}/{category}"


# ---------------------------------------------------------------------------
# Safety-critical core
# ---------------------------------------------------------------------------

def _assert_safe(add_label_ids: list[str], remove_label_ids: list[str],
                 label_id_to_name: dict[str, str]) -> None:
    """Hard gate. Raise if a modify call would do anything but move-to-GSD.

    label_id_to_name maps Gmail label IDs -> human names so we can validate the
    *names* being added (GSD destinations only) regardless of opaque IDs.
    """
    add_names = {label_id_to_name.get(lid, lid) for lid in add_label_ids}
    remove_set = set(remove_label_ids)

    # Never touch TRASH/SPAM in either direction.
    touched = add_names | remove_set | set(add_label_ids)
    forbidden_hit = touched & _FORBIDDEN
    if forbidden_hit:
        raise AssertionError(
            f"SAFETY: refusing to touch forbidden label(s) {forbidden_hit}. "
            "GogOS never deletes, trashes, or marks spam."
        )

    # Only ever add GSD/<Category> destinations.
    bad_adds = {n for n in add_names if not _is_gsd_destination(n)}
    if bad_adds:
        raise AssertionError(
            f"SAFETY: refusing to add non-GSD label(s) {bad_adds}."
        )

    # Only ever remove INBOX.
    bad_removes = remove_set - _REMOVABLE
    if bad_removes:
        raise AssertionError(
            f"SAFETY: refusing to remove label(s) {bad_removes}. "
            "Only INBOX may be removed (archive)."
        )


def _is_gsd_destination(name: str) -> bool:
    if "/" not in name:
        return False
    prefix, _, leaf = name.partition("/")
    return prefix == _GSD_PREFIX and leaf in _GSD_CATEGORIES


def _modify(service, message_id: str,
            add_label_ids: list[str], remove_label_ids: list[str],
            label_id_to_name: dict[str, str]) -> None:
    """The ONLY path to the Gmail mutation API. Gated by _assert_safe."""
    _assert_safe(add_label_ids, remove_label_ids, label_id_to_name)
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": add_label_ids, "removeLabelIds": remove_label_ids},
    ).execute()


# ---------------------------------------------------------------------------
# Label resolution
# ---------------------------------------------------------------------------

def fetch_label_map(service) -> dict[str, str]:
    """Return {label_name: label_id} for the account. No mutation."""
    resp = service.users().labels().list(userId="me").execute()
    return {lbl["name"]: lbl["id"] for lbl in resp.get("labels", [])}


def resolve_destinations(categories: set[str], label_map: dict[str, str]) -> dict[str, str]:
    """Map each needed category -> label_id. Raise if any GSD label is missing.

    We do NOT create missing labels (deliberate, conservative choice).
    """
    missing = []
    resolved: dict[str, str] = {}
    for cat in sorted(categories):
        name = gsd_label_name(cat)
        if name not in label_map:
            missing.append(name)
        else:
            resolved[cat] = label_map[name]
    if missing:
        raise ValueError(
            "Missing Gmail label(s): "
            + ", ".join(missing)
            + ". Create them under the GSD folder, then re-run."
        )
    return resolved


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------

def _yesterday_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date() - timedelta(days=1), time.min, tzinfo=timezone.utc)


def _load_latest(account: str, kind: str, filename: str) -> dict:
    path = latest_alias(storage_path("gmail", account, kind), filename)
    return json.loads(path.read_text())


def build_plan(account: str, *, triage: dict | None = None,
               slim: dict | None = None) -> dict:
    """Build a move proposal from latest triage + slim. Does NOT touch Gmail.

    Returns a plan dict and writes it to approvals/<date>/gmail-labels.json.
    triage/slim can be injected for testing; otherwise read from latest-* aliases.
    """
    account = resolve_account(account)
    if triage is None:
        triage = _load_latest(account, "triage", "latest-triage.json")
    if slim is None:
        slim = _load_latest(account, "inbox", "latest-slim.json")

    by_id = {m["id"]: m for m in slim.get("messages", [])}
    stale_cutoff = _yesterday_start_utc()

    moves = []
    stale = []
    for item in triage.get("items", []):
        mid = item["id"]
        category = item["category"]
        msg = by_id.get(mid, {})
        date_str = msg.get("date", "")
        move = {
            "id": mid,
            "category": category,
            "label_name": gsd_label_name(category),
            "subject": msg.get("subject", ""),
            "from": msg.get("from", ""),
            "date": date_str,
        }
        moves.append(move)
        if _is_stale(date_str, stale_cutoff):
            stale.append(mid)

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "action": "move",  # add GSD/<category>, remove INBOX
        "approved": False,
        "moves": moves,
        "stale_ids": stale,
        "categories": sorted({m["category"] for m in moves}),
    }
    _write_plan(account, plan)
    return plan


def _is_stale(date_str: str, cutoff: datetime) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < cutoff


def _approvals_dir(account: str) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d = STORAGE_ROOT / "approvals" / account / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_plan(account: str, plan: dict) -> Path:
    path = _approvals_dir(account) / "gmail-labels.json"
    path.write_text(json.dumps(plan, indent=2))
    return path


def load_plan(account: str) -> dict:
    account = resolve_account(account)
    path = _approvals_dir(account) / "gmail-labels.json"
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------

def apply_plan(account: str, plan: dict, service) -> dict:
    """Apply an APPROVED move plan. Refuses unless plan['approved'] is True.

    For each move: add GSD/<category> label, remove INBOX. Never deletes.
    Returns a result summary. Aborts (raising) before any mutation if a GSD
    label is missing — never partially applies due to label resolution.
    """
    if not plan.get("approved"):
        raise PermissionError(
            "Refusing to apply: plan is not approved. "
            "Set approved=True only after explicit user confirmation."
        )

    label_map = fetch_label_map(service)
    label_id_to_name = {v: k for k, v in label_map.items()}

    needed = {m["category"] for m in plan.get("moves", [])}
    dest = resolve_destinations(needed, label_map)  # raises if any missing

    moved, failed = [], []
    for m in plan.get("moves", []):
        label_id = dest[m["category"]]
        try:
            _modify(
                service, m["id"],
                add_label_ids=[label_id],
                remove_label_ids=["INBOX"],
                label_id_to_name=label_id_to_name,
            )
            moved.append(m["id"])
        except Exception as exc:  # noqa: BLE001 — report, continue
            failed.append({"id": m["id"], "error": str(exc)})

    return {
        "account": account,
        "moved_count": len(moved),
        "failed_count": len(failed),
        "moved_ids": moved,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _service(account: str):
    from googleapiclient.discovery import build

    from gogos.auth.accounts import resolve_account
    from gogos.auth.google_auth import get_credentials

    resolved = resolve_account(account)
    creds = get_credentials(resolved)
    return build("gmail", "v1", credentials=creds)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[2] not in {"plan", "apply"}:
        print(
            "Usage: python -m gogos.gmail.gmail_apply <account> plan|apply",
            file=sys.stderr,
        )
        sys.exit(1)

    account, mode = sys.argv[1], sys.argv[2]

    if mode == "plan":
        try:
            plan = build_plan(account)
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"ERROR: cannot build plan for '{account}': {exc}. "
                f"Run /email-report {account} first to produce a triage.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            f"OK  Proposed {len(plan['moves'])} move(s) across "
            f"{len(plan['categories'])} folder(s). "
            f"{len(plan['stale_ids'])} stale. "
            "Review and approve before applying."
        )
        sys.exit(0)

    # apply
    plan = load_plan(account)
    if not plan.get("approved"):
        print(
            "ERROR: plan not approved. Approve the proposal first "
            "(set approved=true after confirmation).",
            file=sys.stderr,
        )
        sys.exit(1)
    result = apply_plan(account, plan, _service(account))
    print(
        f"OK  Moved {result['moved_count']} email(s); "
        f"{result['failed_count']} failed."
    )
    sys.exit(0 if result["failed_count"] == 0 else 1)
