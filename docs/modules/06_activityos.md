# Module Spec: ActivityOS

## Purpose

Fast activity and decision logging.

## Build model

Claude Sonnet 4.6.

## Runtime model

Claude Haiku 4.5 for simple summaries.

## Command

`/log [type] [text]`

## Storage

`.core/storage/logs/YYYY-MM-DD/activity.jsonl`

## Acceptance criteria

- Append only.
- Timestamped.
- Typed entries.
- Consumable by ReflectionOS.
