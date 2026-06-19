# /logout-google [account]

Model: Claude Sonnet 4.6

Purpose: delete the stored local Google token for the selected account, after explicit confirmation.
The `account` argument can be an alias (e.g. `abavisg`) or full email (e.g. `abavisg@gmail.com`).

## Steps

1. Read the `account` argument from `$ARGUMENTS`. If empty, print:
   ```
   Usage: /logout-google <alias-or-email>
   ```
   and stop.

2. Resolve the argument to a canonical email:
   ```
   python -c "
   from dotenv import load_dotenv; load_dotenv()
   from gogos.auth.accounts import resolve_account
   import sys
   try: print(resolve_account(sys.argv[1]))
   except ValueError as e: print(f'ERROR  {e}', end='')
   " <account>
   ```
   If resolution fails, print the error and stop.

3. Ask the user for explicit confirmation:
   ```
   Delete token for '<alias> (<resolved-email>)'
   at .core/storage/auth/<resolved-email>/google_token.json? [y/N]
   ```
   If not `y`/`yes`, print "Aborted." and stop.

4. Run:
   ```
   python -c "
   import sys
   from dotenv import load_dotenv; load_dotenv()
   from gogos.auth.logout import logout
   sys.exit(logout(sys.argv[1], confirmed=True))
   " <resolved-email>
   ```
   Report output verbatim. If non-zero, surface error and stop.

5. If successful, confirm:
   ```
   Token for '<alias> (<resolved-email>)' deleted.
   Re-authenticate with /login-google <alias> when needed.
   ```

## Safety

- Never print token contents, refresh tokens, client secrets, or credential file contents.
- Never delete the credentials file (`GOOGLE_CREDENTIALS_PATH`).
- Never delete any directory — only the single token file.
- Never delete anything outside `.core/storage/auth/<email>/`.
- Deletion only happens after the user explicitly confirms with `y` or `yes`.
