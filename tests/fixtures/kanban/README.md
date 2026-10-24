# Claude Code task list fixture

The real on-disk format of a Claude Code task list directory
(`~/.claude/tasks/<CLAUDE_CODE_TASK_LIST_ID>/`), captured on 2026-10-24 from
Claude Code 2.1.310. It was produced by a headless session with a throwaway
list id, using `TaskCreate` for two tasks (the second with
`metadata.gogos_ref`) and `TaskUpdate` to complete the first. The files were
copied as written; the subjects and descriptions were synthetic from the
start, so no anonymising was needed. The throwaway list was deleted afterwards.

What the capture shows:

- one `<id>.json` per task, ids are increasing integers as strings;
- an empty `.lock` file sits beside them;
- keys `id`, `subject`, `description`, `status`, `blocks`, `blockedBy` are always
  present; `metadata` appears only when set;
- `status` is `pending` or `completed` here (`in_progress` is the third value).

`tests/test_kanban.py` fails if a required key goes missing from these files.
To refresh after a Claude Code upgrade, repeat the capture and replace the files.
