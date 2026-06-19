# /login-google [account]

Model: Claude Sonnet 4.6

Purpose: authenticate a Google account using the local OAuth desktop flow and store a read-only token.
The `account` argument can be an alias (e.g. `abavisg`) or a full email (e.g. `abavisg@gmail.com`).

## Steps

1. Read the `account` argument from `$ARGUMENTS`. If empty, print:
   ```
   Usage: /login-google <alias-or-email>
   Examples: /login-google abavisg   or   /login-google abavisg@gmail.com
   ```
   and stop.

2. Resolve the argument to a canonical email:
   ```
   python -c "
   from dotenv import load_dotenv; load_dotenv()
   from gogos.auth.accounts import resolve_account
   import sys
   try:
       print(resolve_account(sys.argv[1]))
   except ValueError as e:
       print(f'UNRESOLVED', end='')
   " <account>
   ```
   - If resolved: use the returned email for all subsequent steps.
   - If `UNRESOLVED` and the argument contains `@` (looks like an email):
     Ask the user: "Email `<account>` is not registered. Enter an alias for it
     (or press Enter to proceed without registering):"
     - If alias provided: run `/account-add <alias> <account>` first, then use `<account>` as the email.
     - If Enter: proceed with `<account>` as the email directly (first-run bootstrap).
   - If `UNRESOLVED` and no `@`: print:
     ```
     Error: '<account>' is not a known alias. Register it first with /account-add <alias> <email>.
     ```
     and stop.

3. Check that `GOOGLE_CREDENTIALS_PATH` is set and the file it points to exists.
   If either check fails, print the error and stop. Never print credential file contents.

4. Run the OAuth flow using the resolved email:
   ```
   python -c "
   import sys
   from dotenv import load_dotenv; load_dotenv()
   from gogos.auth.google_auth import get_credentials, _token_path
   email = sys.argv[1]
   try:
       creds = get_credentials(email)
       token = _token_path(email)
       print(f'OK  Authenticated as {email!r}')
       print(f'OK  Token stored at {token}')
       print(f'OK  Token valid: {creds.valid}')
   except RuntimeError as e:
       print(f'ERROR  {e}', file=sys.stderr)
       sys.exit(1)
   except FileNotFoundError as e:
       print(f'ERROR  {e}', file=sys.stderr)
       sys.exit(1)
   " <resolved-email>
   ```

5. Report the output verbatim. If exit code is non-zero, surface the error and stop.

6. If successful, confirm:
   ```
   Login complete for <alias> (<resolved-email>).
   Token written to .core/storage/auth/<resolved-email>/google_token.json
   ```
   Never print token contents, refresh tokens, client secrets, or .env values.

## Safety

- Never print token contents, refresh tokens, client secrets, or credential file contents.
- Never create or modify credentials files — only read them.
- If the helper raises a scope-mismatch error, surface it verbatim and instruct
  the user to run `/logout-google <account>` first.
- Never launch OAuth for an unresolvable argument.
