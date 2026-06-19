"""Account validation — reads GOGOS_ACCOUNTS from the environment."""
from __future__ import annotations

import os


def known_accounts() -> list[str]:
    """Return the list of configured accounts (from GOGOS_ACCOUNTS env var)."""
    raw = os.environ.get("GOGOS_ACCOUNTS", "personal,work")
    return [a.strip() for a in raw.split(",") if a.strip()]


def default_account() -> str:
    """Return the default account (from GOGOS_DEFAULT_ACCOUNT env var)."""
    return os.environ.get("GOGOS_DEFAULT_ACCOUNT", "personal").strip()


def validate_account(account: str) -> None:
    """Raise ValueError if account is not in GOGOS_ACCOUNTS."""
    accounts = known_accounts()
    if account not in accounts:
        raise ValueError(
            f"Unknown account '{account}'. "
            f"Valid accounts: {', '.join(accounts)}. "
            f"Add it to GOGOS_ACCOUNTS in your .env to register a new account."
        )
