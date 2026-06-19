# /account-list

Purpose: list all registered accounts and their aliases.

## Steps

1. Run:
   ```
   python -m gogos.auth.account_mgmt list
   ```

2. Display the output. The `*` marker indicates the default account.

3. For each account, optionally check if a token exists:
   ```
   ls .core/storage/auth/<email>/google_token.json 2>/dev/null
   ```
   and add `(authenticated)` or `(no token — run /login-google <alias>)` next to each entry.
