# Security and Privacy Requirements

## Baseline stance

GogOS handles private email, calendar, health, learning, and personal logs. Treat all generated data as sensitive.

## Rules

- Local-first by default.
- No secrets in git.
- No tokens in prompts unless explicitly required and redacted.
- No destructive or external write action without explicit approval.
- Read-only OAuth scopes for MVP.
- Store raw private data under `.core/storage`, which should be gitignored.
- Prefer generated summaries over exposing full raw email/calendar data to Claude.

## Gitignore requirements

The following must be ignored:

```text
.env
.core/config/secrets/
.core/storage/
*.token.json
credentials.json
.DS_Store
__pycache__/
.venv/
```

## Approval gates

State-changing actions must use a two-step flow:

1. Generate proposed action file.
2. Apply action only after explicit user confirmation.

## OAuth safety

Use one Google OAuth desktop client for local development. Use read-only scopes first.

If scopes change, delete the token and re-authenticate.
