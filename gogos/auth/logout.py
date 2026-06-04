from __future__ import annotations

import sys
from pathlib import Path

from gogos.auth.google_auth import _REPO_ROOT, _token_path

_AUTH_ROOT = _REPO_ROOT / ".core/storage/auth"


def _safe_token_path(account: str) -> Path:
    """Return the resolved token path, refusing anything outside _AUTH_ROOT."""
    token = _token_path(account).resolve()
    try:
        token.relative_to(_AUTH_ROOT.resolve())
    except ValueError:
        raise ValueError(
            f"Resolved token path {token} is outside the auth directory. "
            "Logout aborted."
        )
    return token


def logout(account: str, *, confirmed: bool = False) -> int:
    """Delete the Google token for *account* after confirmation.

    Returns 0 on success / no-op, 1 on error.
    confirmed=True skips the interactive prompt (used by tests and the command).
    """
    try:
        token = _safe_token_path(account)
    except ValueError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 1

    if not token.exists():
        print(f"MISSING  No token found for '{account}' at {token} — nothing to do.")
        return 0

    if not confirmed:
        answer = input(
            f"Delete token for '{account}' at {token}? [y/N] "
        ).strip().lower()
        confirmed = answer in ("y", "yes")

    if not confirmed:
        print(f"Aborted. Token for '{account}' was not deleted.")
        return 0

    token.unlink()
    print(f"OK  Token for '{account}' deleted.")
    return 0
