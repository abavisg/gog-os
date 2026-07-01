"""Drain an oversized inbox in batches: fetch -> classify -> apply, repeat.

When the inbox holds more than the fetch cap (GOGOS_ALL_CAP), one pass can't
clear it. This loops the pipeline: each apply archives its batch, so the next
'all' fetch sees the next slice — the inbox drains without pagination state.

Approval is preserved. By default the loop builds each batch's move plan but
does NOT apply it (the caller/command shows the plan and gets a yes). With
auto_apply=True (CLI --yes) the caller has pre-authorised all batches.

A max-iteration bound prevents an infinite loop if something stops draining.

Entry points:
  run_loop(account, ...) -> result dict
  python -m gogos.gmail.gmail_loop <account> [--yes] [--max N]
"""
from __future__ import annotations

import sys

from gogos.auth.accounts import resolve_account
from gogos.gmail import gmail_apply, gmail_classify, gmail_fetch, gmail_normalise
from gogos.paths import latest_alias, storage_path

_DEFAULT_MAX_ITERATIONS = 20


def _count_inbox(service) -> int:
    """Live count of messages currently in the inbox (one labels.get call)."""
    label = service.users().labels().get(userId="me", id="INBOX").execute()
    return int(label.get("messagesTotal", 0) or 0)


def _run_batch_read(account: str) -> int:
    """Fetch all -> normalise -> classify for one batch. Returns batch size.

    Read-only: produces latest-slim.json and latest-triage.json. No Gmail writes.
    """
    rc = gmail_fetch.fetch(account, "all")
    if rc != 0:
        raise RuntimeError("fetch failed")

    raw_path = latest_alias(storage_path("gmail", account, "inbox"), "latest-raw.json")
    rc = gmail_normalise.normalise(account, raw_path)
    if rc != 0:
        raise RuntimeError("normalise failed")

    rc = gmail_classify.classify(account)
    if rc != 0:
        raise RuntimeError("classify failed")

    triage = gmail_apply._load_latest(account, "triage", "latest-triage.json")
    return len(triage.get("items", []))


def run_loop(account: str, *, auto_apply: bool = False,
             max_iterations: int = _DEFAULT_MAX_ITERATIONS,
             service=None) -> dict:
    """Drain the inbox in batches.

    auto_apply=False (default): build each batch's plan but stop — return after
      the first batch with the plan staged for the caller to approve. The loop
      is only meaningful when batches are auto-applied; without approval the
      caller handles apply + re-invocation.
    auto_apply=True: approve and apply each batch, repeating until the inbox is
      empty or max_iterations is hit.

    Returns a summary dict.
    """
    account = resolve_account(account)
    svc = service if service is not None else gmail_apply._service(account)

    batches = []
    iterations = 0

    while True:
        if iterations >= max_iterations:
            return {
                "account": account, "status": "max_iterations_reached",
                "iterations": iterations, "batches": batches,
                "remaining": _count_inbox(svc),
            }

        batch_size = _run_batch_read(account)
        if batch_size == 0:
            return {
                "account": account, "status": "empty",
                "iterations": iterations, "batches": batches, "remaining": 0,
            }

        plan = gmail_apply.build_plan(account)

        if not auto_apply:
            # Stop and hand the plan to the caller for approval.
            return {
                "account": account, "status": "awaiting_approval",
                "iterations": iterations, "batches": batches,
                "pending_plan_size": len(plan.get("moves", [])),
            }

        # Pre-authorised: approve and apply this batch.
        plan["approved"] = True
        result = gmail_apply.apply_plan(account, plan, svc)
        iterations += 1
        batches.append({
            "iteration": iterations,
            "planned": len(plan.get("moves", [])),
            "moved": result["moved_count"],
            "failed": result["failed_count"],
        })

        if result["failed_count"] > 0:
            return {
                "account": account, "status": "failures",
                "iterations": iterations, "batches": batches,
                "remaining": _count_inbox(svc),
            }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python -m gogos.gmail.gmail_loop <account> [--yes] [--max N]",
            file=sys.stderr,
        )
        sys.exit(1)

    account = sys.argv[1]
    auto = "--yes" in sys.argv[2:]
    max_iter = _DEFAULT_MAX_ITERATIONS
    if "--max" in sys.argv:
        try:
            max_iter = int(sys.argv[sys.argv.index("--max") + 1])
        except (ValueError, IndexError):
            print("ERROR: --max needs an integer", file=sys.stderr)
            sys.exit(1)

    try:
        result = run_loop(account, auto_apply=auto, max_iterations=max_iter)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    status = result["status"]
    if status == "empty":
        total = sum(b["moved"] for b in result["batches"])
        print(f"OK  Inbox drained in {result['iterations']} batch(es); {total} email(s) moved.")
    elif status == "awaiting_approval":
        print(
            f"OK  Batch ready: {result['pending_plan_size']} move(s) proposed. "
            "Approve to apply (run /email-apply, or re-run with --yes to drain all)."
        )
    elif status == "max_iterations_reached":
        print(
            f"WARNING: hit max {result['iterations']} iterations; "
            f"{result['remaining']} still in inbox. Re-run to continue.",
            file=sys.stderr,
        )
        sys.exit(1)
    else:  # failures
        total = sum(b["moved"] for b in result["batches"])
        print(f"WARNING: stopped after failures; {total} moved, {result['remaining']} remain.", file=sys.stderr)
        sys.exit(1)
