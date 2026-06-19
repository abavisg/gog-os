# /account-alias <current-alias> <new-alias>

Purpose: rename an existing alias. The email it points to is unchanged.

## Steps

1. Parse `current-alias` and `new-alias` from `$ARGUMENTS`. If either is missing:
   ```
   Usage: /account-alias <current-alias> <new-alias>
   Example: /account-alias abavisg personal
   ```
   and stop.

2. Run:
   ```
   python -m gogos.auth.account_mgmt alias <current-alias> <new-alias>
   ```
   Report the output verbatim.

3. If successful, confirm:
   ```
   Alias renamed: '<current>' → '<new>'
   The email address and all stored data are unchanged.
   ```

## Safety

- Only renames the alias key in `.core/config/accounts.json`.
- Never touches tokens, storage files, or the email address itself.
- New alias must not contain `@`.
