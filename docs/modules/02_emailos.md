# Module Spec: EmailOS

## Purpose

Generate a safe Gmail triage report.

## Build model

Claude Sonnet 4.6.

## Runtime models

- Classification: Claude Sonnet 4.6 initially.
- Report rendering: Claude Haiku 4.5.

## Inputs

- Gmail read-only OAuth token.
- Gmail categories config.
- Triage rubric.

## Outputs

- Raw Gmail metadata JSON.
- Normalised email JSON.
- Triage JSON.
- Markdown report.
- HTML report.

## Acceptance criteria

- Metadata-only by default.
- No Gmail write-back.
- Conservative classification.
- Dated artefacts preserved.
