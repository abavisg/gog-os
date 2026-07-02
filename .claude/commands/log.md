# /log [type] [text]

> **Stub** — backing module (ActivityOS, Phase 7) not built yet.

Implementation model: Sonnet (default — unpinned); runtime rendering may pin Haiku when built (per the model policy in CLAUDE.md).

Purpose: append a structured activity log entry.

Supported types:

- activity
- decision
- learning
- workout
- content
- note

Safety:

- Append only.
- Never rewrite previous logs.
