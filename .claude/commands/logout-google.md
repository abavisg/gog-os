# /logout-google [account]

Model: Claude Sonnet 4.6

Purpose: remove stored local Google token for the selected account.

Steps:

1. Locate token path.
2. Ask for explicit confirmation before deletion.
3. Delete only the selected token file.
4. Report success or missing token.

Safety:

- Never delete credentials file.
- Never delete full storage folders.
