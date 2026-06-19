# /account-add <alias> <email>

Purpose: register a new account alias→email mapping in `.core/config/accounts.json`.

## Steps

1. Parse `alias` and `email` from `$ARGUMENTS` (two space-separated tokens).
   If either is missing, print:
   ```
   Usage: /account-add <alias> <email>
   Example: /account-add abavisg abavisg@gmail.com
   ```
   and stop.

2. Run:
   ```
   python -m gogos.auth.account_mgmt add <alias> <email>
   ```
   Report the output verbatim.

3. If successful (`OK` prefix), confirm:
   ```
   Account '<alias>' registered → <email>
   Use /login-google <alias> to authenticate.
   ```

## Safety

- Does not launch OAuth or touch any tokens.
- Does not write anything outside `.core/config/accounts.json`.
- Alias must not contain `@`. Email must contain `@`.
