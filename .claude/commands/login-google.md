# /login-google [account]

Model: Claude Sonnet 4.6

Purpose: authenticate a Google account using local OAuth desktop flow.

Inputs:

- account: personal or work.

Steps:

1. Validate account exists in config.
2. Validate credentials file exists.
3. Run OAuth helper with read-only Gmail and Calendar scopes.
4. Store token under `.core/storage/auth/{account}/google_token.json`.
5. Confirm success without printing secrets.

Safety:

- Do not print token contents.
- If scopes change, ask user to delete old token first.
