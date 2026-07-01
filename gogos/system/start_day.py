"""Morning entry point — EmailOS read-only across accounts, one merged panel.

Phase 4.6 §5 + §6. For every registered account: reconcile (learn from manual
moves) -> fetch -> normalise -> classify, all READ-ONLY towards Gmail, then
merge the per-account triage into a single panel where every item is
account-tagged ([personal] / [work]). Fetch/classify/apply/undo/approval stay
per-account; only the view is unified.

Safety invariant (tested): this module never imports the apply module and
never mutates Gmail. Write-back stays behind /email-apply and /email-loop.

A failing account is reported loudly (stderr + a warning line in the panel)
and the run continues with the remaining accounts; only if every account
fails is the exit code non-zero.

Entry points:
  run(accounts=None, window="yesterday") -> exit code
  nudge() -> exit code  (SessionStart hook: offers /start-day, never runs it)

  python -m gogos.system.start_day [account ...] [--window W]
  python -m gogos.system.start_day --nudge
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gogos.auth.accounts import known_accounts, list_accounts, resolve_account
from gogos.gmail import gmail_classify, gmail_fetch, gmail_normalise, gmail_reconcile
from gogos.gmail.gmail_report import _cat_prefix, _sender_short, build_digest
from gogos.paths import STORAGE_ROOT, latest_alias, storage_path

_LOCAL_TZ = ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))

_ATTENTION_CATS = ("Action", "Review", "Events")


def _now_local() -> datetime:
    return datetime.now(tz=_LOCAL_TZ)


def _today() -> str:
    return _now_local().strftime("%Y-%m-%d")


def alias_for(email: str) -> str:
    """Display tag for an account: its alias, else the address local part."""
    for entry in list_accounts():
        if entry["email"] == email:
            return entry["alias"]
    return email.split("@")[0]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _load_latest(email: str, kind: str, filename: str) -> dict:
    path = latest_alias(storage_path("gmail", email, kind), filename)
    if not path.exists():
        return {}
    try:
        return _load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Per-account pipeline (read-only towards Gmail)
# ---------------------------------------------------------------------------

def run_account(account: str, window: str = "yesterday") -> dict:
    """reconcile -> fetch -> normalise -> classify for one account.

    Returns {account, alias, triage, slim, reconcile, triage_path, slim_path}.
    Raises RuntimeError if the read pipeline fails; reconcile is best-effort
    (it needs a previously applied batch) and never blocks the morning run.
    """
    email = resolve_account(account)

    try:
        gmail_reconcile.reconcile(email)
    except Exception as exc:  # noqa: BLE001 — enhancement, not the pipeline
        print(f"WARN  [{alias_for(email)}] reconcile skipped: {exc}", file=sys.stderr)

    if gmail_fetch.fetch(email, window) != 0:
        raise RuntimeError("fetch failed")

    raw_path = latest_alias(storage_path("gmail", email, "inbox"), "latest-raw.json")
    if gmail_normalise.normalise(email, raw_path) != 0:
        raise RuntimeError("normalise failed")

    if gmail_classify.classify(email) != 0:
        raise RuntimeError("classify failed")

    triage_path = latest_alias(storage_path("gmail", email, "triage"), "latest-triage.json")
    slim_path = latest_alias(storage_path("gmail", email, "inbox"), "latest-slim.json")
    return {
        "account": email,
        "alias": alias_for(email),
        "triage": _load_json(triage_path),
        "slim": _load_json(slim_path),
        "reconcile": _load_latest(email, "reconcile", "latest-reconcile.json"),
        "triage_path": triage_path,
        "slim_path": slim_path,
    }


# ---------------------------------------------------------------------------
# Multi-account merge (§5): one panel, every item account-tagged
# ---------------------------------------------------------------------------

def merge_results(results: list[dict]) -> tuple[dict, dict]:
    """Merge per-account triage + reconcile data for the combined digest."""
    merged_triage = {"items": [item for r in results
                              for item in r["triage"].get("items", [])]}
    merged_reconcile: dict = {"learned": [], "rescue_suggestions": [],
                              "unsubscribe_candidates": []}
    for r in results:
        for key in merged_reconcile:
            merged_reconcile[key].extend(r.get("reconcile", {}).get(key, []))
    return merged_triage, merged_reconcile


def render_panel(results: list[dict], errors: dict[str, str] | None = None,
                 generated_at: str | None = None) -> str:
    """Merged morning panel: combined digest, account-tagged attention items,
    per-account queue counts. Pure — no I/O."""
    if generated_at is None:
        generated_at = _now_local().isoformat(timespec="seconds")
    date_part = generated_at[:10]

    lines: list[str] = [f"# Start Day — {date_part}", ""]

    for account, err in (errors or {}).items():
        lines.append(f"> ⚠️ **[{alias_for(account)}]** skipped: {err}")
    if errors:
        lines.append("")

    merged_triage, merged_reconcile = merge_results(results)
    digest = build_digest(merged_triage, merged_reconcile)
    if digest:
        lines.extend(f"> {d}" for d in digest)
        lines.append("")

    if not merged_triage["items"]:
        lines.append("*No messages to triage.*")
        lines.append("")

    # Needs-you list: every item account-tagged, category order preserved.
    attention: list[str] = []
    for category in _ATTENTION_CATS:
        for r in results:
            index = {m["id"]: m for m in r["slim"].get("messages", [])}
            for item in r["triage"].get("items", []):
                if item.get("category") != category:
                    continue
                msg = index.get(item.get("id", ""), {})
                sender = _sender_short(msg.get("from", "") or "*(unknown sender)*")
                subject = msg.get("subject") or "*(no subject)*"
                entry = (f"- **[{r['alias']}]** {_cat_prefix(category).strip()} "
                         f"{sender} — {subject}")
                action = item.get("suggested_action", "")
                if action:
                    entry += f" → {action}"
                attention.append(entry)
    if attention:
        lines.append(f"## Needs you ({len(attention)})")
        lines.append("")
        lines.extend(attention)
        lines.append("")

    # Queue: one line per account so the tag covers every count too.
    queue_lines: list[str] = []
    for r in results:
        counts: dict[str, int] = {}
        for item in r["triage"].get("items", []):
            cat = item.get("category", "Uncategorised")
            if cat in _ATTENTION_CATS:
                continue
            counts[cat] = counts.get(cat, 0) + 1
        if counts:
            parts = [f"{_cat_prefix(c).strip()} {n} {c}" for c, n in counts.items()]
            queue_lines.append(f"- **[{r['alias']}]** {' · '.join(parts)}")
    if queue_lines:
        lines.append("## Queue")
        lines.append("")
        lines.extend(queue_lines)
        lines.append("")

    lines.append("---")
    lines.append("Read-only — nothing was moved. Run `/email-apply <account>` "
                 "to file the queue, `/email-undo <account>` to reverse the last batch.")
    lines.append(f"Generated: {generated_at}")
    for r in results:
        lines.append(f"Sources [{r['alias']}]: `{r['triage_path']}` · `{r['slim_path']}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator (§6): the single morning command, read-only, then stop
# ---------------------------------------------------------------------------

def run(accounts: list[str] | None = None, window: str = "yesterday") -> int:
    """Run the read pipeline for every account, write + print the merged panel."""
    if not accounts:
        accounts = known_accounts()
    if not accounts:
        print("ERROR: no accounts registered. Run /account-add first.", file=sys.stderr)
        return 1

    results: list[dict] = []
    errors: dict[str, str] = {}
    for account in accounts:
        try:
            results.append(run_account(account, window))
        except Exception as exc:  # noqa: BLE001 — keep the other accounts alive
            email = account
            try:
                email = resolve_account(account)
            except ValueError:
                pass
            errors[email] = str(exc)
            print(f"ERROR: [{account}] {exc}", file=sys.stderr)

    if not results:
        print("ERROR: every account failed — no panel written.", file=sys.stderr)
        return 1

    panel = render_panel(results, errors)

    dated_dir = storage_path("reports", "start-day", "all")
    (dated_dir / "start-day.md").write_text(panel)
    alias = latest_alias(dated_dir, "latest.md")
    alias.write_text(panel)

    print(panel)
    print(f"\nOK  Wrote merged panel → {alias}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# SessionStart nudge: offer /start-day, never run it
# ---------------------------------------------------------------------------

def nudge() -> int:
    """One-line offer for the SessionStart hook. Reads only local artefacts —
    no network, no Gmail, no directory creation — and always exits 0.

    Quiet once today's panel exists (already run); shows counts when a
    scheduled/earlier triage from today is available; otherwise a plain offer.
    """
    today = _today()

    panel = STORAGE_ROOT / "reports" / "start-day" / "all" / today / "start-day.md"
    if panel.exists():
        return 0

    total = actions = 0
    found = False
    for email in known_accounts():
        path = STORAGE_ROOT / "gmail" / email / "triage" / today / "latest-triage.json"
        if not path.exists():
            continue
        try:
            items = _load_json(path).get("items", [])
        except (OSError, json.JSONDecodeError):
            continue
        found = True
        total += len(items)
        actions += sum(1 for i in items if i.get("category") == "Action")

    if found:
        print(f"🌅 Run /start-day? {total} triaged this morning, {actions} need action.")
    else:
        print("🌅 Run /start-day for a read-only merged email brief across your accounts.")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--nudge" in argv:
        sys.exit(nudge())

    win = "yesterday"
    if "--window" in argv:
        try:
            i = argv.index("--window")
            win = argv[i + 1]
            del argv[i:i + 2]
        except IndexError:
            print("ERROR: --window needs a value", file=sys.stderr)
            sys.exit(1)

    sys.exit(run(argv or None, win))
