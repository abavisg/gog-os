"""The learning log: docs/LEARNINGS.md, newest entry first (spec 8).

The system records lessons and *proposes* changes; the owner approves before
anything behavioural changes. This module is the only writer /learn and
/health use, so a proposal can never edit the file it proposes to change:
add() touches LEARNINGS.md and nothing else.

Entry format (the header of LEARNINGS.md documents it too):

  ### YYYY-MM-DD: <short title>
  - **Status:** noted | proposed | applied | rejected
  - **Trigger:** what surfaced this
  - **Lesson:** the durable, reusable takeaway
  - **Proposed change:** exact file and edit (omitted when noted)
  - **Resolution:** filled when applied or rejected

Entry points:
  add(title, trigger, lesson, status="noted", proposed_change=None) -> str
  resolve(title, status, resolution) -> None      applied | rejected

  python -m gogos.core.learnings add --title T --trigger T --lesson L
                                     [--status noted|proposed|applied] [--change C]
  python -m gogos.core.learnings resolve --title T --status applied|rejected --resolution R
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

from gogos.core import paths

STATUSES = ("noted", "proposed", "applied", "rejected")
MARKER = "## Entries"


def learnings_file() -> Path:
    return paths.REPO_ROOT / "docs" / "LEARNINGS.md"


def _one_line(name: str, value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError(f"{name} is empty")
    return value


def _write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".learnings.")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _read() -> tuple[Path, str]:
    path = learnings_file()
    text = path.read_text()
    if f"\n{MARKER}\n" not in text:
        raise ValueError(f"{path} has no '{MARKER}' heading")
    return path, text


def add(title: str, trigger: str, lesson: str, status: str = "noted",
        proposed_change: str | None = None) -> str:
    """Insert an entry at the top of the entries; returns its heading."""
    if status not in ("noted", "proposed", "applied"):
        raise ValueError(f"status must be noted, proposed or applied, not '{status}'")
    if status == "proposed" and not proposed_change:
        raise ValueError("a proposed entry needs --change (the exact file and edit)")
    heading = f"### {paths.today()}: {_one_line('title', title)}"
    lines = [heading, f"- **Status:** {status}",
             f"- **Trigger:** {_one_line('trigger', trigger)}",
             f"- **Lesson:** {_one_line('lesson', lesson)}"]
    if proposed_change:
        lines.append(f"- **Proposed change:** {_one_line('change', proposed_change)}")
    if status == "applied":
        lines.append(f"- **Resolution:** applied {paths.today()}.")
    path, text = _read()
    head, _, rest = text.partition(f"\n{MARKER}\n")
    older = rest.strip("\n")
    entry = "\n".join(lines) + "\n"
    _write(path, f"{head}\n{MARKER}\n\n{entry}" + (f"\n{older}\n" if older else ""))
    return heading


def resolve(title: str, status: str, resolution: str) -> None:
    """Mark the newest entry with this title applied or rejected."""
    if status not in ("applied", "rejected"):
        raise ValueError("resolve sets applied or rejected")
    path, text = _read()
    m = re.search(rf"^### \d{{4}}-\d{{2}}-\d{{2}}: {re.escape(title.strip())}\n((?:- .*\n?)*)",
                  text, re.M)
    if not m:
        raise ValueError(f"no entry titled '{title}'")
    body = m.group(1)
    body = re.sub(r"^- \*\*Status:\*\* .*$", f"- **Status:** {status}", body, count=1, flags=re.M)
    body = re.sub(r"^- \*\*Resolution:\*\* .*\n?", "", body, flags=re.M)
    body = body.rstrip("\n") + f"\n- **Resolution:** {status} {paths.today()}: " \
        f"{_one_line('resolution', resolution)}\n"
    _write(path, text[:m.start(1)] + body + text[m.end(1):])


_USAGE = """usage:
  python -m gogos.core.learnings add --title T --trigger T --lesson L [--status S] [--change C]
  python -m gogos.core.learnings resolve --title T --status applied|rejected --resolution R"""


def _flags(args: list[str]) -> dict:
    out: dict = {}
    it = iter(args)
    for flag in it:
        if not flag.startswith("--"):
            raise ValueError(f"expected --flag value, got '{flag}'")
        try:
            out[flag[2:]] = next(it)
        except StopIteration:
            raise ValueError(f"{flag} needs a value") from None
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("add", "resolve"):
        print(_USAGE, file=sys.stderr)
        return 2
    try:
        f = _flags(args[1:])
        if args[0] == "add":
            missing = [k for k in ("title", "trigger", "lesson") if k not in f]
            if missing:
                print(f"ERROR add needs --{', --'.join(missing)}", file=sys.stderr)
                return 2
            heading = add(f["title"], f["trigger"], f["lesson"],
                          f.get("status", "noted"), f.get("change"))
            print(f"OK  {heading}")
        else:
            if not {"title", "status", "resolution"} <= set(f):
                print(_USAGE, file=sys.stderr)
                return 2
            resolve(f["title"], f["status"], f["resolution"])
            print(f"OK  {f['title']} → {f['status']}")
    except (ValueError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
