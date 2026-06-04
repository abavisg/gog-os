# /setup-check

Model: Claude Sonnet 4.6

Purpose: validate GogOS local environment.

Steps:

1. Run the setup check script once implemented.
2. Verify Python version is 3.11+.
3. Verify required folders exist.
4. Verify `.env` exists or instruct user to copy `.env.example`.
5. Verify Google credentials file exists if Google modules are enabled.
6. Report missing items clearly.

Never create credentials or tokens.
