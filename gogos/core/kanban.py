"""Kanban: Claude Code's task list as a projection of open commitments (spec 2b).

The register is the truth; the task list is derived state. sync() writes
every open commitment as a task in the list directory named by
CLAUDE_CODE_TASK_LIST_ID (set to "gogos" in .claude/settings.json, so every
session shares one board), stamping the register ref into metadata.gogos_ref.
reconcile() reads the directory back: a task marked completed whose gogos_ref
points at an open commitment sets that commitment to kept, with a history
line noting "kanban". Tasks without a gogos_ref are returned as "inbox from
kanban" candidates for the next brief and never imported.

Run reconcile before sync: sync keeps a kanban-side completion it finds on a
still-open commitment, and drops tasks whose commitment is no longer open.
Deleting the list directory loses nothing; the next sync rebuilds it.

The on-disk format (one <id>.json per task) is internal to Claude Code. It is
pinned by tests/fixtures/kanban/, and every task read is checked for
REQUIRED_KEYS, so a format change fails loudly here and nowhere else.

Entry points:
  task_dir() -> Path
  sync() -> dict          {"dir", "created", "updated", "removed"}
  reconcile() -> dict     {"kept", "inbox_candidates"}

  python -m gogos.core.kanban sync
  python -m gogos.core.kanban reconcile
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from gogos.core import journal, paths, registers

REQUIRED_KEYS = ("id", "subject", "description", "status", "blocks", "blockedBy")
TASK_STATUSES = ("pending", "in_progress", "completed")
DEFAULT_LIST_ID = "gogos"


class KanbanFormatError(ValueError):
    """A task file no longer matches the format this module was built against."""


def task_dir() -> Path:
    """<claude config dir>/tasks/<CLAUDE_CODE_TASK_LIST_ID>; config dir defaults to ~/.claude."""
    config = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    list_id = os.environ.get("CLAUDE_CODE_TASK_LIST_ID") or DEFAULT_LIST_ID
    return Path(config) / "tasks" / list_id


def _read_tasks(d: Path) -> list[tuple[Path, dict]]:
    out = []
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.json")):
        try:
            task = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise KanbanFormatError(f"{path}: not JSON: {exc}") from exc
        missing = [k for k in REQUIRED_KEYS if k not in task]
        if missing:
            raise KanbanFormatError(
                f"{path}: missing key(s) {', '.join(missing)}; the Claude Code task "
                "format may have changed (see tests/fixtures/kanban/)")
        if task["status"] not in TASK_STATUSES:
            raise KanbanFormatError(f"{path}: unknown status {task['status']!r}")
        out.append((path, task))
    return out


def _ref(task: dict) -> str | None:
    meta = task.get("metadata")
    return meta.get("gogos_ref") if isinstance(meta, dict) else None


def _write_task(path: Path, task: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(task, indent=2, ensure_ascii=False))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _projection(item: registers.Item) -> tuple[str, str, dict]:
    due = str(item.meta["due"])
    subject = item.meta["title"]
    description = f"Due {due} ({item.meta['area']}). Register item: {item.ref}"
    return subject, description, {"gogos_ref": item.ref, "due": due,
                                  "area": item.meta["area"]}


def sync() -> dict:
    """Project every open commitment into the task list; returns counts."""
    d = task_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ".lock").touch(exist_ok=True)
    tasks = _read_tasks(d)
    by_ref = {ref: (p, t) for p, t in tasks if (ref := _ref(t))}
    next_id = 1 + max((int(t["id"]) for _, t in tasks if str(t["id"]).isdigit()), default=0)

    commitments = [i for i in registers.load("commitment") if i.is_open]
    commitments.sort(key=lambda i: (str(i.meta["due"]), i.ref))
    created = updated = removed = 0
    for item in commitments:
        subject, description, meta = _projection(item)
        if item.ref in by_ref:
            path, task = by_ref.pop(item.ref)
            # Keep the task's status: a kanban-side completion waits for reconcile().
            new = {**task, "subject": subject, "description": description,
                   "metadata": {**(task.get("metadata") or {}), **meta}}
            if new != task:
                _write_task(path, new)
                updated += 1
        else:
            task = {"id": str(next_id), "subject": subject, "description": description,
                    "status": "pending", "blocks": [], "blockedBy": [], "metadata": meta}
            _write_task(d / f"{next_id}.json", task)
            next_id += 1
            created += 1

    for path, _task in by_ref.values():  # commitment kept, missed, dropped or gone
        path.unlink()
        removed += 1

    result = {"dir": str(d), "created": created, "updated": updated, "removed": removed}
    journal.append({"type": "sync.run", "text": "kanban sync", "source": "kanban",
                    "meta": {k: v for k, v in result.items() if k != "dir"}})
    return result


def reconcile() -> dict:
    """Completed tasks keep their open commitments; untracked tasks become candidates."""
    commitment_dir = paths.registers_dir("commitment").resolve()
    kept: list[str] = []
    candidates: list[dict] = []
    for path, task in _read_tasks(task_dir()):
        ref = _ref(task)
        if not ref:
            candidates.append({k: task[k] for k in ("id", "subject", "description", "status")})
            continue
        if task["status"] != "completed":
            continue
        target = paths.resolve_ref(ref)
        if target.resolve().parent != commitment_dir or not target.exists():
            print(f"WARN  kanban: {path.name} points at {ref}, not a commitment; skipped",
                  file=sys.stderr)
            continue
        if registers.load_item(target).is_open:
            registers.set_status(target, "kept", note="kanban")
            kept.append(ref)
    return {"kept": kept, "inbox_candidates": candidates}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (["sync"], ["reconcile"]):
        print("usage: python -m gogos.core.kanban sync|reconcile", file=sys.stderr)
        return 2
    try:
        result = sync() if args[0] == "sync" else reconcile()
    except (KanbanFormatError, registers.RegisterError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
