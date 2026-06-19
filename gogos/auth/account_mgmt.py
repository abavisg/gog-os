"""Account management CLI — add, remove, rename alias, list.

Usage:
  python -m gogos.auth.account_mgmt add <alias> <email>
  python -m gogos.auth.account_mgmt remove <alias-or-email>
  python -m gogos.auth.account_mgmt alias <current-alias> <new-alias>
  python -m gogos.auth.account_mgmt list
"""
from __future__ import annotations

import sys

from gogos.auth.accounts import (
    add_account,
    list_accounts,
    remove_account,
    rename_alias,
)


def cmd_add(args: list[str]) -> int:
    if len(args) != 2:
        print("Usage: account_mgmt add <alias> <email>", file=sys.stderr)
        return 1
    alias, email = args
    try:
        add_account(alias, email)
        print(f"OK  Registered '{alias}' → {email}")
        return 0
    except ValueError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 1


def cmd_remove(args: list[str]) -> int:
    if len(args) != 1:
        print("Usage: account_mgmt remove <alias-or-email>", file=sys.stderr)
        return 1
    try:
        remove_account(args[0])
        print(f"OK  Removed account '{args[0]}'")
        print("NOTE  Storage files on disk are unchanged. Delete manually if desired.")
        return 0
    except ValueError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 1


def cmd_alias(args: list[str]) -> int:
    if len(args) != 2:
        print("Usage: account_mgmt alias <current-alias> <new-alias>", file=sys.stderr)
        return 1
    current, new = args
    try:
        rename_alias(current, new)
        print(f"OK  Renamed alias '{current}' → '{new}'")
        return 0
    except ValueError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 1


def cmd_list(args: list[str]) -> int:
    accounts = list_accounts()
    if not accounts:
        print("No accounts registered. Run /account-add to add one.")
        return 0
    width = max(len(a["alias"]) for a in accounts)
    for entry in accounts:
        marker = " *" if entry["default"] else "  "
        print(f"{marker} {entry['alias']:<{width}}  {entry['email']}")
    print("\n  * = default account")
    return 0


_COMMANDS = {
    "add": cmd_add,
    "remove": cmd_remove,
    "alias": cmd_alias,
    "list": cmd_list,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print(
            "Usage: python -m gogos.auth.account_mgmt <command> [args]\n"
            "Commands: add, remove, alias, list",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(_COMMANDS[sys.argv[1]](sys.argv[2:]))
