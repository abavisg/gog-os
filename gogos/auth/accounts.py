"""Account registry — alias→email mapping backed by .core/config/accounts.json.

Public API (all callers use these; signatures unchanged from the old env-var version):
  resolve_account(arg)   — alias or email → canonical email; raises ValueError if unknown
  validate_account(arg)  — thin wrapper around resolve_account; kept for compat
  known_accounts()       — list of registered canonical emails
  default_account()      — the default canonical email
  add_account(alias, email)
  remove_account(alias_or_email)
  rename_alias(current, new_alias)
  list_accounts()        — [{"alias": ..., "email": ..., "default": bool}]

Legacy fallback: if accounts.json is missing or empty, falls back to GOGOS_ACCOUNTS
env var (short strings treated as-is). Prints a deprecation warning on first use.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EMPTY_CONFIG: dict = {"version": 1, "default": None, "aliases": {}}


def _config_path() -> Path:
    return _REPO_ROOT / ".core/config/accounts.json"


def load_accounts_config() -> dict:
    """Read accounts.json. Returns empty-default dict if missing. Raises RuntimeError on bad JSON."""
    p = _config_path()
    if not p.exists():
        return dict(_EMPTY_CONFIG)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed accounts config at {p}: {exc}") from exc
    # Ensure required keys present
    data.setdefault("version", 1)
    data.setdefault("default", None)
    data.setdefault("aliases", {})
    return data


def _write_config(config: dict) -> None:
    """Atomically write config to accounts.json."""
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2))
    tmp.replace(p)


def _valid_email(email: str) -> bool:
    parts = email.split("@")
    return len(parts) == 2 and bool(parts[0]) and "." in parts[1] and bool(parts[1])


def _valid_alias(alias: str) -> bool:
    return bool(alias) and "@" not in alias


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_account(arg: str) -> str:
    """Resolve alias or email to a canonical email address.

    Resolution order:
    1. Check aliases map — if arg is a key, return its email value.
    2. If arg looks like an email (contains @):
       a. If it appears as a value in aliases map → return it (registered email).
       b. If aliases map is completely empty → return it as-is (first-run bootstrap).
       c. Otherwise → raise ValueError (unregistered email when accounts exist).
    3. Otherwise (no @, not a known alias) → raise ValueError.
    """
    config = load_accounts_config()
    aliases: dict[str, str] = config.get("aliases", {})

    # Direct alias hit
    if arg in aliases:
        return aliases[arg]

    if "@" in arg:
        registered_emails = set(aliases.values())
        # Registered raw email
        if arg in registered_emails:
            return arg
        # First-run bootstrap — no accounts registered yet
        if not aliases:
            return arg
        raise ValueError(
            f"Email '{arg}' is not registered. "
            f"Run /account-add <alias> {arg} to register it."
        )

    # Unknown alias
    known = sorted(aliases.keys())
    hint = f" Known aliases: {', '.join(known)}." if known else " No accounts registered yet. Run /account-add."
    raise ValueError(f"Unknown account '{arg}'.{hint}")


def validate_account(account: str) -> None:
    """Raise ValueError if account cannot be resolved. Kept for backward compatibility."""
    resolve_account(account)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def known_accounts() -> list[str]:
    """Return registered canonical emails. Falls back to GOGOS_ACCOUNTS env var."""
    config = load_accounts_config()
    aliases = config.get("aliases", {})
    if aliases:
        # De-duplicate, preserve insertion order
        seen: dict[str, None] = {}
        for email in aliases.values():
            seen[email] = None
        return list(seen)

    # Legacy fallback
    raw = os.environ.get("GOGOS_ACCOUNTS", "")
    if raw:
        print(
            "DEPRECATION: Using GOGOS_ACCOUNTS env var for account list. "
            "Migrate with /account-add.",
            file=sys.stderr,
        )
        return [a.strip() for a in raw.split(",") if a.strip()]
    return []


def default_account() -> str:
    """Return the default canonical email."""
    config = load_accounts_config()
    if config.get("default"):
        return config["default"]

    # Env var fallback
    env_default = os.environ.get("GOGOS_DEFAULT_ACCOUNT", "").strip()
    if env_default:
        return env_default

    # First registered account
    accounts = known_accounts()
    if accounts:
        return accounts[0]

    raise RuntimeError(
        "No accounts registered and GOGOS_DEFAULT_ACCOUNT is not set. "
        "Run /account-add to register your first account."
    )


def list_accounts() -> list[dict]:
    """Return [{'alias': ..., 'email': ..., 'default': bool}] sorted by alias."""
    config = load_accounts_config()
    aliases: dict[str, str] = config.get("aliases", {})
    default = config.get("default")
    return sorted(
        [{"alias": k, "email": v, "default": (v == default)} for k, v in aliases.items()],
        key=lambda x: x["alias"],
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_account(alias: str, email: str) -> None:
    """Register a new alias→email mapping. Raises ValueError on bad input or duplicate alias."""
    if not _valid_alias(alias):
        raise ValueError(f"Invalid alias '{alias}': must not contain '@' and must not be empty.")
    if not _valid_email(email):
        raise ValueError(f"Invalid email '{email}': must contain exactly one '@' with a non-empty domain.")

    config = load_accounts_config()
    aliases = config["aliases"]

    if alias in aliases:
        raise ValueError(
            f"Alias '{alias}' is already registered (→ {aliases[alias]}). "
            f"Use /account-alias to rename it."
        )

    aliases[alias] = email
    if not config.get("default"):
        config["default"] = email
    _write_config(config)


def remove_account(alias_or_email: str) -> None:
    """Remove all aliases pointing to the resolved email. Raises ValueError if not found.

    Does NOT delete storage files — caller is responsible for communicating that to the user.
    """
    config = load_accounts_config()
    aliases = config["aliases"]

    # Resolve to email
    if "@" in alias_or_email:
        email = alias_or_email
        if email not in aliases.values():
            raise ValueError(f"Email '{email}' is not registered.")
    else:
        if alias_or_email not in aliases:
            raise ValueError(f"Alias '{alias_or_email}' is not registered.")
        email = aliases[alias_or_email]

    # Remove all aliases pointing to this email
    config["aliases"] = {k: v for k, v in aliases.items() if v != email}

    # Clear default if it was this email
    if config.get("default") == email:
        remaining = list(config["aliases"].values())
        config["default"] = remaining[0] if remaining else None

    _write_config(config)


def rename_alias(current: str, new_alias: str) -> None:
    """Rename an existing alias. Raises ValueError if current not found or new_alias taken."""
    if not _valid_alias(new_alias):
        raise ValueError(f"Invalid alias '{new_alias}': must not contain '@'.")

    config = load_accounts_config()
    aliases = config["aliases"]

    if current not in aliases:
        raise ValueError(f"Alias '{current}' is not registered.")
    if new_alias in aliases:
        raise ValueError(f"Alias '{new_alias}' is already in use (→ {aliases[new_alias]}).")

    email = aliases.pop(current)
    aliases[new_alias] = email
    _write_config(config)
