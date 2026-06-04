# Module Spec: TaskOS

## Purpose

Local-first task capture and daily planning.

## Build model

Claude Sonnet 4.6.

## Commands

- `/task-add "task"`
- `/tasks-today`
- `/task-done [id]`

## Storage

`.core/storage/tasks/tasks.jsonl`

## Acceptance criteria

- Append-safe task creation.
- Status updates preserve history.
- Morning brief can read open tasks.
