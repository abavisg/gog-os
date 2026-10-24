"""Storage paths and the one definition of "today".

Every dated directory (storage, approvals) takes its date from today(): the
local date in GOGOS_TIMEZONE (default Europe/London), read at call time.
Timestamps are UTC via now_utc(); local time is for rendering only.

Library module; no CLI.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
STORAGE_ROOT: Path = REPO_ROOT / ".core/storage"


def local_tz() -> ZoneInfo:
    """The owner's timezone: GOGOS_TIMEZONE, default Europe/London."""
    return ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))


def now_utc() -> datetime:
    """The current instant, timezone-aware UTC."""
    return datetime.now(timezone.utc)


def today() -> str:
    """The local date (YYYY-MM-DD) in GOGOS_TIMEZONE."""
    return now_utc().astimezone(local_tz()).strftime("%Y-%m-%d")


def storage_path(module: str, account: str, kind: str, date: str | None = None) -> Path:
    if date is None:
        date = today()
    path = STORAGE_ROOT / module / account / kind / date
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_alias(dir_path: Path, filename: str) -> Path:
    return dir_path / filename
