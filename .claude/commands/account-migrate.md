# /account-migrate

Purpose: one-time helper to migrate legacy `personal`/`work` style accounts to the
alias→email system. Run this if you have existing data under `.core/storage/auth/personal/`
or similar short-name directories.

## Steps

1. List subdirectories under `.core/storage/auth/` that do not look like email addresses
   (i.e. do not contain `@`):
   ```
   ls .core/storage/auth/
   ```

2. For each legacy directory found (e.g. `personal`, `work`):
   - Print: `Found legacy account '<name>'. What email address does this correspond to?`
   - Wait for the user to provide an email address.
   - Ask for an alias: `Alias for this account (or Enter to use '<name>' as the alias):`
   - Run: `python -m gogos.auth.account_mgmt add <alias> <email>`
   - Report result.

3. After all accounts are registered, instruct:
   ```
   Migration complete. Run /login-google <alias> for each account to re-authenticate.
   Old directories under .core/storage/auth/<name>/ remain on disk. You can delete
   them manually once you've confirmed the new tokens work.
   ```

## Notes

- This does NOT move or rename any storage directories.
- Old data under `personal/`, `work/` etc. will no longer be read by the new code.
  New fetches write to `<email>/` directories.
- Safe to run multiple times — already-registered aliases are skipped.
