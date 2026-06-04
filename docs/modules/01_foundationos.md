# Module Spec: FoundationOS

## Purpose

Create the reliable base for GogOS. No integrations yet.

## Build model

Claude Sonnet 4.6.

## Deliverables

- Python package skeleton.
- Config loader.
- Path helper.
- Setup check.
- Logging utility.
- Tests.
- `/setup-check` command.

## Acceptance criteria

- Setup check runs without Google credentials and reports missing optional integrations.
- Required directories are validated.
- Private paths are gitignored.
