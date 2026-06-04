# /logout-google [account]

Model: Claude Sonnet 4.6

Purpose: delete the stored local Google token for the selected account, after explicit confirmation.

## Steps

1. Read the `account` argument from `$ARGUMENTS`. If it is empty, print:
   ```
   Usage: /logout-google <account>   (e.g. personal or work)
   ```
   and stop.

2. Ask the user for explicit confirmation before doing anything:
   ```
   Delete token for '<account>' at .core/storage/auth/<account>/google_token.json? [y/N]
   ```
   If the answer is not `y` or `yes` (case-insensitive), print:
   ```
   Aborted. Token for '<account>' was not deleted.
   ```
   and stop.

3. Run the following Python command and report its output verbatim:
   ```
   python -c "
   import sys
   from dotenv import load_dotenv
   load_dotenv()
   from gogos.auth.logout import logout
   account = sys.argv[1]
   sys.exit(logout(account, confirmed=True))
   " <account>
   ```

4. If the exit code is non-zero, surface the error and stop.

5. If successful, confirm:
   ```
   Token for '<account>' has been deleted.
   Re-authenticate with /login-google <account> when needed.
   ```

## Safety

- Never print token contents, refresh tokens, client secrets, or credential file contents.
- Never delete the credentials file (`GOOGLE_CREDENTIALS_PATH`).
- Never delete any directory — only the single token file.
- Never delete anything outside `.core/storage/auth/<account>/`.
- Deletion only happens after the user explicitly confirms with `y` or `yes`.
