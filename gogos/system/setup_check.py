"""Setup check for GogOS. Run with: python -m gogos.system.setup_check"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_REQUIRED_DIRS = [
    _REPO_ROOT / ".core/storage",
    _REPO_ROOT / ".core/config",
]


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"OK       {label}{suffix}")


def _missing(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"MISSING  {label}{suffix}")


def _error(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"ERROR    {label}{suffix}", file=sys.stderr)


def check_python_version() -> bool:
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        _ok("Python version", f"{major}.{minor}")
        return True
    _error("Python version", f"need >= 3.11, got {major}.{minor}")
    return False


def check_required_dirs() -> bool:
    all_ok = True
    for dir_path in _REQUIRED_DIRS:
        rel = dir_path.relative_to(_REPO_ROOT)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            _ok(str(rel))
        except OSError as exc:
            _error(str(rel), str(exc))
            all_ok = False
    return all_ok


def check_env_file() -> None:
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        _ok(".env")
    else:
        _missing(".env", "copy .env.example to .env to configure")


def check_accounts_config() -> None:
    from gogos.auth.accounts import _config_path, load_accounts_config
    p = _config_path()
    if not p.exists():
        _missing("accounts.json", "run /account-add <alias> <email> to register your first account")
        return
    try:
        cfg = load_accounts_config()
    except RuntimeError as exc:
        _error("accounts.json", str(exc))
        return
    count = len(cfg.get("aliases", {}))
    if count == 0:
        print(f"WARNING  accounts.json  (exists but no accounts registered)")
    else:
        _ok("accounts.json", f"{count} account(s) registered")


def check_google_credentials() -> None:
    creds_path_str = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
    if not creds_path_str:
        _missing("GOOGLE_CREDENTIALS_PATH", "env var not set — Google modules will not work")
        return
    creds_path = Path(creds_path_str)
    if not creds_path.is_absolute():
        creds_path = _REPO_ROOT / creds_path
    if creds_path.exists():
        _ok("GOOGLE_CREDENTIALS_PATH", str(creds_path))
    else:
        _missing("GOOGLE_CREDENTIALS_PATH", f"file not found at {creds_path} — Google modules will not work")


def run() -> int:
    print("GogOS setup check\n")
    hard_fail = False

    if not check_python_version():
        hard_fail = True

    if not check_required_dirs():
        hard_fail = True

    check_env_file()
    check_accounts_config()
    check_google_credentials()

    print()
    if hard_fail:
        print("Setup FAILED — fix the ERROR items above before proceeding.", file=sys.stderr)
        return 1
    print("Setup OK — optional MISSING items are shown above.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
