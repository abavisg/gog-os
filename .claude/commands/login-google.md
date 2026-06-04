# /login-google [account]

Model: Claude Sonnet 4.6

Purpose: authenticate a Google account using the local OAuth desktop flow and store a read-only token.

## Steps

1. Read the `account` argument from `$ARGUMENTS`. If it is empty, print:
   ```
   Usage: /login-google <account>   (e.g. personal or work)
   ```
   and stop.

2. Load `.env` (if present) so environment variables are available, then read
   `GOGOS_ACCOUNTS` from the environment (default: `personal,work`).
   If `account` is **not** in that comma-separated list, print:
   ```
   Error: unknown account "<account>". Valid accounts: <GOGOS_ACCOUNTS>
   No OAuth flow launched.
   ```
   and stop.

3. Check that `GOOGLE_CREDENTIALS_PATH` is set and the file it points to exists.
   If either check fails, print the error from the helper and stop. Do **not**
   print the path's file contents.

4. Run the following Python command and capture its output:
   ```
   python -c "
   import sys, os
   from dotenv import load_dotenv
   load_dotenv()
   from gogos.auth.google_auth import get_credentials, _token_path
   account = sys.argv[1]
   try:
       creds = get_credentials(account)
       token = _token_path(account)
       print(f'OK  Authenticated as {account!r}')
       print(f'OK  Token stored at {token}')
       print(f'OK  Token valid: {creds.valid}')
   except RuntimeError as e:
       print(f'ERROR  {e}', file=sys.stderr)
       sys.exit(1)
   except FileNotFoundError as e:
       print(f'ERROR  {e}', file=sys.stderr)
       sys.exit(1)
   " <account>
   ```

5. Report the output verbatim. If the exit code is non-zero, surface the error
   message and stop — do **not** retry or launch a second flow.

6. If successful, confirm with:
   ```
   Login complete for <account>. Token written to .core/storage/auth/<account>/google_token.json
   ```
   Do **not** print token contents, refresh tokens, client secrets, or .env values.

## Safety

- Never print token contents, refresh tokens, client secrets, or credential file contents.
- Never create or modify credentials files — only read them.
- If the helper raises a scope-mismatch error, surface it verbatim and instruct
  the user to run `/logout-google <account>` first.
- Do not launch OAuth for an unknown or missing account.
