from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
STORAGE_ROOT: Path = REPO_ROOT / ".core/storage"

_DEFAULT_TZ = ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))


def storage_path(module: str, account: str, kind: str, date: str | None = None) -> Path:
    if date is None:
        date = datetime.now(tz=_DEFAULT_TZ).strftime("%Y-%m-%d")
    path = STORAGE_ROOT / module / account / kind / date
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_alias(dir_path: Path, filename: str) -> Path:
    return dir_path / filename
