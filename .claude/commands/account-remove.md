# /account-remove <alias-or-email>

Purpose: remove an account from the registry. Does NOT delete any stored data on disk.

## Steps

1. Parse `alias-or-email` from `$ARGUMENTS`. If missing, print usage and stop.

2. Run `python -m gogos.auth.account_mgmt list` to confirm the account exists and show
   what will be removed. If the account is not found, print the error and stop.

3. Ask the user for explicit confirmation:
   ```
   Remove account '<alias>' (<email>) from the registry?
   Note: stored data under .core/storage/ is NOT deleted.
   Type 'yes' to confirm:
   ```
   If the user does not type exactly `yes`, print "Aborted." and stop.

4. Run:
   ```
   python -m gogos.auth.account_mgmt remove <alias-or-email>
   ```
   Report the output verbatim.

5. Remind the user:
   ```
   Registry entry removed. Token and stored data at:
     .core/storage/auth/<email>/
     .core/storage/gmail/<email>/
     .core/storage/calendar/<email>/
   are still on disk. Delete manually if no longer needed.
   ```

## Safety

- Never deletes storage files automatically.
- Requires explicit `yes` confirmation before any change.
