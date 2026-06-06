# Module Spec: EmailOS

**Status: Done (read-only MVP).**

## What was built

- `gogos/gmail/gmail_fetch.py` — metadata-only fetch (`format=metadata`), hard-asserts no body in output, truncation handling, dated raw JSON + `latest-raw.json`.
- `gogos/gmail/gmail_normalise.py` — raw → canonical slim JSON (UTC dates), dated slim JSON + `latest-slim.json`.
- `gogos/gmail/gmail_triage.py` — validates and writes triage JSON, dated + `latest-triage.json`.
- `gogos/gmail/gmail_report.py` — Markdown report grouped by category, cites source artefacts and timestamp.
- `email-triage` skill hardened: treats all email fields as untrusted data, never follows embedded instructions.
- `/email-report [account]` orchestrates the full pipeline.

## Acceptance criteria (met)

- Metadata-only. Raw output provably contains no message bodies.
- No Gmail write-back anywhere.
- Markdown report cites source artefact paths and generation timestamp.
- Empty inbox handled gracefully.

## Not built (intentionally deferred)

- HTML reports.
- Gmail labels, archive, delete.
