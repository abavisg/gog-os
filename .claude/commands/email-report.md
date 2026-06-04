# /email-report [account]

Implementation model: Claude Sonnet 4.6
Runtime triage model: Claude Sonnet 4.6
Runtime report model: Claude Haiku 4.5

Purpose: generate a safe Gmail triage report.

Steps:

1. Run Gmail metadata fetch for account.
2. Store raw and normalised JSON under dated storage.
3. Invoke email-triage skill using normalised JSON, categories, and rubric.
4. Write triage JSON.
5. Generate Markdown and HTML report.
6. Open the HTML report if local environment supports it.

Safety:

- Read-only only.
- No labels.
- No archive.
- No delete.
- No full-body fetch unless explicitly requested.
