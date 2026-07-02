"""Local morning scheduler — launchd wrapper for the read-only email pipeline.

Phase 4.6 §7 (slice 7, the last EmailOS item). Installs a per-user launchd
agent that runs the real gogos pipeline every morning (~08:00 by default) with
the local venv, OAuth tokens, and storage — the reason a cloud routine can't do
this job. The agent fires only while the Mac is on; launchd runs a missed
StartCalendarInterval once on wake, and skips it entirely if the machine was
off.

The scheduled run is READ-ONLY towards Gmail (tested: this module never
references the apply engine): per account it runs reconcile -> fetch ->
normalise -> classify -> report (no browser auto-open), then posts one macOS
notification with the merged counts. It deliberately does NOT write the
/start-day panel, so the SessionStart nudge still offers /start-day with this
morning's counts. Moves stay behind /email-apply and /email-loop.

Entry points:
  python -m gogos.system.scheduler install [--time HH:MM]
  python -m gogos.system.scheduler uninstall
  python -m gogos.system.scheduler status
  python -m gogos.system.scheduler run [--window W]   # what launchd executes
"""
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

from gogos.auth.accounts import known_accounts
from gogos.gmail import gmail_report
from gogos.paths import REPO_ROOT, STORAGE_ROOT
from gogos.system import start_day

LABEL = "com.gogos.start-day"

_VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
_LOG_DIR = STORAGE_ROOT / "logs" / "scheduler"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def plist_dict(hour: int = 8, minute: int = 0) -> dict:
    """The launchd agent definition. Pure — no I/O."""
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(_VENV_PYTHON), "-m", "gogos.system.scheduler", "run",
        ],
        "WorkingDirectory": str(REPO_ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "StandardOutPath": str(_LOG_DIR / "launchd.out.log"),
        "StandardErrorPath": str(_LOG_DIR / "launchd.err.log"),
    }


def plist_xml(hour: int = 8, minute: int = 0) -> str:
    return plistlib.dumps(plist_dict(hour, minute), sort_keys=False).decode()


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# install / uninstall / status
# ---------------------------------------------------------------------------

def install(hour: int = 8, minute: int = 0) -> int:
    if not _VENV_PYTHON.exists():
        print(f"ERROR: venv python not found at {_VENV_PYTHON}", file=sys.stderr)
        return 1

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        _launchctl("unload", str(path))  # reload cleanly on reinstall
    path.write_text(plist_xml(hour, minute))

    result = _launchctl("load", "-w", str(path))
    if result.returncode != 0:
        print(f"ERROR: launchctl load failed: {result.stderr.strip()}", file=sys.stderr)
        return 1

    print(f"OK  Installed {LABEL} — daily at {hour:02d}:{minute:02d} → {path}")
    print(f"    Logs: {_LOG_DIR}/launchd.{{out,err}}.log")
    print("    The run is read-only; moves stay behind /email-apply.")
    return 0


def uninstall() -> int:
    path = plist_path()
    if not path.exists():
        print(f"OK  Nothing to uninstall — {path} does not exist.")
        return 0
    _launchctl("unload", "-w", str(path))  # best-effort; may not be loaded
    path.unlink()
    print(f"OK  Uninstalled {LABEL} and removed {path}")
    return 0


def status() -> int:
    path = plist_path()
    if not path.exists():
        print(f"NOT INSTALLED  ({path} missing). Run: "
              f"python -m gogos.system.scheduler install")
        return 0

    try:
        schedule = plistlib.loads(path.read_bytes()).get("StartCalendarInterval", {})
        when = f"{schedule.get('Hour', '?'):02d}:{schedule.get('Minute', '?'):02d}"
    except Exception:  # noqa: BLE001 — status must never crash on a bad plist
        when = "unreadable plist"

    loaded = LABEL in _launchctl("list").stdout
    print(f"INSTALLED  {LABEL} — daily at {when} ({'loaded' if loaded else 'NOT loaded'})")
    print(f"    Plist: {path}")
    print(f"    Logs:  {_LOG_DIR}/launchd.{{out,err}}.log")
    return 0


# ---------------------------------------------------------------------------
# The scheduled run itself (read-only, notify, stop)
# ---------------------------------------------------------------------------

def _notify(message: str) -> None:
    """macOS notification. Best-effort: a notification failure must never fail
    the triage run itself."""
    safe = message.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe}" with title "GogOS"'],
            capture_output=True, timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"WARN  notification failed: {exc}", file=sys.stderr)


def run_scheduled(window: str = "yesterday") -> int:
    """Per account: reconcile -> fetch -> normalise -> classify -> report
    (no browser), then one notification with merged counts. Never writes the
    /start-day panel (the SessionStart nudge keeps offering it) and never
    touches write-back."""
    accounts = known_accounts()
    if not accounts:
        print("ERROR: no accounts registered.", file=sys.stderr)
        return 1

    total = actions = 0
    succeeded: list[str] = []
    failed: dict[str, str] = {}
    for email in accounts:
        try:
            result = start_day.run_account(email, window)
            gmail_report.report(email, result["triage_path"],
                                result["slim_path"], auto_open=False)
            items = result["triage"].get("items", [])
            total += len(items)
            actions += sum(1 for i in items if i.get("category") == "Action")
            succeeded.append(email)
        except Exception as exc:  # noqa: BLE001 — keep the other accounts alive
            failed[email] = str(exc)
            print(f"ERROR: [{email}] {exc}", file=sys.stderr)

    if not succeeded:
        _notify("Morning triage failed for every account — check the scheduler log.")
        return 1

    message = f"{total} emails triaged, {actions} need action. Run /start-day."
    if failed:
        message += f" ({len(failed)} account(s) failed — see log.)"
    _notify(message)
    print(f"OK  Scheduled triage: {len(succeeded)} account(s), "
          f"{total} items, {actions} Action.")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "status"

    if cmd == "install":
        hour, minute = 8, 0
        if "--time" in argv:
            try:
                hour_s, minute_s = argv[argv.index("--time") + 1].split(":")
                hour, minute = int(hour_s), int(minute_s)
                assert 0 <= hour <= 23 and 0 <= minute <= 59
            except (IndexError, ValueError, AssertionError):
                print("ERROR: --time needs HH:MM (e.g. --time 08:00)", file=sys.stderr)
                sys.exit(1)
        sys.exit(install(hour, minute))
    if cmd == "uninstall":
        sys.exit(uninstall())
    if cmd == "status":
        sys.exit(status())
    if cmd == "run":
        win = "yesterday"
        if "--window" in argv:
            try:
                win = argv[argv.index("--window") + 1]
            except IndexError:
                print("ERROR: --window needs a value", file=sys.stderr)
                sys.exit(1)
        sys.exit(run_scheduled(win))

    print(f"ERROR: unknown command '{cmd}'. "
          "Use install [--time HH:MM] | uninstall | status | run [--window W]",
          file=sys.stderr)
    sys.exit(1)
