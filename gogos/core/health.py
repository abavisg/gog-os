"""Health checks that need the memory code: the LIFE half and check S6.

.claude/scripts/health-check.sh owns the report and the exit code; this
module answers the questions that need the front matter parser or the
register schema, so the bash script never restates either (spec 8).

  life   L1 to L8, advisory. Each line is "PASS <code> <msg>" or
         "WARN <code> <msg>". Always exits 0.
  areas  S6: me/areas.json ids match registers.AREAS and every `area:`
         value used under life/. Lines are "PASS S6 ..." or "ISSUE S6 ...";
         exits 1 on any issue.

L3 is registers.validate_all(), so register rules live in one place. L8
records a sha256 of each final report the first time it sees it (in
.core/storage/reports/final.sha256) and warns when the text before any
`## Amendment` heading later changes.

  python -m gogos.core.health life  [--root DIR]
  python -m gogos.core.health areas [--root DIR]

--root points at a repo root holding life/, me/ and .core/storage/ (the
bash tests use a synthetic one); it defaults to this repo.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from gogos.core import frontmatter, paths, registers

BASE_REQUIRED = ("title", "type", "status", "area", "created", "updated", "tags")
TYPES = ("wiki", "register", "workspace", "report", "profile")
# Status sets spec 2 fixes per type. Wiki pages have none yet; registers are L3's.
TYPE_STATUSES = {
    "workspace": ("active", "review", "archived"),
    "report": ("draft", "review", "final"),
}
CONTENT_DIRS = ("wiki", "registers", "workspaces", "reports")
INBOX_MAX_DAYS = 3
JOURNAL_WINDOW_DAYS = 14

_WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
_AMENDMENT = re.compile(r"^## Amendment \d{4}-\d{2}-\d{2}", re.M)

Line = tuple[str, str, str]  # (PASS | WARN | ISSUE, code, message)


def _storage_root(root: Path | None) -> Path:
    return (root / ".core" / "storage") if root else paths.STORAGE_ROOT


def _rel(p: Path) -> str:
    try:
        return paths.rel_ref(p)
    except ValueError:
        return str(p)


def _content_files() -> list[Path]:
    out: list[Path] = []
    for d in CONTENT_DIRS:
        base = paths.LIFE_ROOT / d
        if base.is_dir():
            out.extend(sorted(base.rglob("*.md")))
    return out


def _area_ids() -> list[str] | None:
    f = paths.ME_ROOT / "areas.json"
    try:
        data = json.loads(f.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    rows = data.get("areas", data) if isinstance(data, dict) else data
    return [r["id"] for r in rows if isinstance(r, dict) and "id" in r]


# ---------------------------------------------------------------------------
# LIFE
# ---------------------------------------------------------------------------

def l1_front_matter(today: str) -> list[Line]:
    areas = set(_area_ids() or registers.AREAS) | {"none"}
    out: list[Line] = []
    files = _content_files()
    for f in files:
        try:
            meta, _ = frontmatter.split(f.read_text())
        except (OSError, frontmatter.FrontMatterError) as exc:
            out.append(("WARN", "L1", f"{_rel(f)}: {exc}"))
            continue
        missing = [k for k in BASE_REQUIRED if k not in meta]
        if missing:
            out.append(("WARN", "L1", f"{_rel(f)}: missing {', '.join(missing)}"))
            continue
        t = meta["type"]
        if t not in TYPES:
            out.append(("WARN", "L1", f"{_rel(f)}: type '{t}' is not one of {', '.join(TYPES)}"))
        allowed = TYPE_STATUSES.get(t)
        if allowed and meta["status"] not in allowed:
            out.append(("WARN", "L1", f"{_rel(f)}: status '{meta['status']}' "
                                      f"is not one of {'|'.join(allowed)}"))
        if meta["area"] not in areas:
            out.append(("WARN", "L1", f"{_rel(f)}: area '{meta['area']}' is not in me/areas.json"))
        if str(meta["updated"]) > today:
            out.append(("WARN", "L1", f"{_rel(f)}: updated {meta['updated']} is in the future"))
    if not out:
        out.append(("PASS", "L1", f"front matter valid on {len(files)} content files"))
    return out


def _link_targets() -> tuple[set[str], set[str]]:
    """(basenames, life-relative paths without .md) of every linkable page."""
    names: set[str] = set()
    rels: set[str] = set()
    for sub in ("wiki", "registers"):
        base = paths.LIFE_ROOT / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            if p.name.startswith("_"):
                continue
            names.add(p.stem)
            rels.add(p.relative_to(paths.LIFE_ROOT).with_suffix("").as_posix())
            rels.add(p.relative_to(base).with_suffix("").as_posix())
    return names, rels


def l2_wikilinks() -> list[Line]:
    names, rels = _link_targets()
    missing: dict[str, str] = {}
    for f in _content_files():
        if f.name.startswith("_"):
            continue
        try:
            text = f.read_text()
        except OSError:
            continue
        for raw in _WIKILINK.findall(text):
            target = raw.split("|", 1)[0].rstrip("\\").strip()
            if target.endswith(".md"):
                target = target[:-3]
            ok = target in rels if "/" in target else target in names
            if not ok:
                missing.setdefault(target, _rel(f))
    if not missing:
        return [("PASS", "L2", "all wikilinks resolve")]
    return [("WARN", "L2", f"unresolved [[{t}]] (first seen in {src})")
            for t, src in sorted(missing.items())]


def l3_registers() -> tuple[list[Line], list[registers.Item]]:
    count, errors = registers.validate_all()
    if errors:
        return [("WARN", "L3", str(e)) for e in errors], []
    return [("PASS", "L3", f"{count} register items valid")], registers.load()


def l4_review(items: list[registers.Item], today: str) -> list[Line]:
    overdue: dict[str, int] = {}
    lapsed: list[str] = []
    for i in items:
        if not i.is_open:
            continue
        rb = str(i.meta.get("review_by", "none"))
        if rb != "none" and rb < today:
            overdue[i.kind] = overdue.get(i.kind, 0) + 1
        if i.kind == "renewal" and str(i.meta["expires"]) < today:
            lapsed.append(i.slug)
    out: list[Line] = [("WARN", "L4", f"{n} open {kind} item(s) past review_by")
                       for kind, n in sorted(overdue.items())]
    if lapsed:
        out.append(("WARN", "L4", f"renewal(s) past expires and still open: {', '.join(lapsed)}"))
    return out or [("PASS", "L4", "nothing past review_by")]


def l5_inbox(now: float) -> list[Line]:
    d = paths.inbox_dir()
    files = [p for p in d.rglob("*") if p.is_file() and not p.name.startswith(".")] \
        if d.is_dir() else []
    if not files:
        return [("PASS", "L5", "inbox is empty")]
    oldest = (now - min(p.stat().st_mtime for p in files)) / 86400
    msg = f"{len(files)} item(s) in life/inbox/, oldest {oldest:.0f} day(s)"
    if oldest > INBOX_MAX_DAYS:
        return [("WARN", "L5", f"{msg} (older than {INBOX_MAX_DAYS} days)")]
    return [("PASS", "L5", msg)]


def l6_journal(today: str) -> list[Line]:
    end = date.fromisoformat(today)
    empty = []
    for n in range(JOURNAL_WINDOW_DAYS):
        day = (end - timedelta(days=n)).isoformat()
        f = paths.journal_file(day)
        try:
            has = any(line.strip() for line in f.read_text().splitlines())
        except OSError:
            has = False
        if not has:
            empty.append(day)
    if not empty:
        return [("PASS", "L6", f"journal has events on each of the last {JOURNAL_WINDOW_DAYS} days")]
    return [("WARN", "L6", f"{len(empty)} of the last {JOURNAL_WINDOW_DAYS} days have no journal events")]


def l7_profile(today: str) -> list[Line]:
    f = paths.ME_ROOT / "profile.md"
    try:
        meta, body = frontmatter.split(f.read_text())
    except (OSError, frontmatter.FrontMatterError) as exc:
        return [("WARN", "L7", f"me/profile.md: {exc}")]
    provisional = sum(1 for line in body.splitlines()
                      if line.startswith("|") and "| provisional |" in line)
    last = str(meta.get("last_validated", "none"))
    if last == "none":
        age = "never validated"
    else:
        try:
            age = f"last validated {(date.fromisoformat(today) - date.fromisoformat(last)).days} day(s) ago"
        except ValueError:
            return [("WARN", "L7", f"me/profile.md: last_validated '{last}' is not a date")]
    msg = f"{provisional} provisional claim(s); {age}"
    return [("WARN" if provisional or last == "none" else "PASS", "L7", msg)]


def _report_digest(text: str) -> str:
    # Trailing blank lines are not content: appending an amendment adds one.
    m = _AMENDMENT.search(text)
    return hashlib.sha256((text[:m.start()] if m else text).rstrip("\n").encode()).hexdigest()


def l8_final_reports(storage: Path) -> list[Line]:
    base = paths.LIFE_ROOT / "reports"
    finals: dict[str, str] = {}
    for f in sorted(base.rglob("*.md")) if base.is_dir() else []:
        try:
            text = f.read_text()
            meta, _ = frontmatter.split(text)
        except (OSError, frontmatter.FrontMatterError):
            continue
        if meta.get("status") == "final":
            finals[_rel(f)] = _report_digest(text)
    if not finals:
        return [("PASS", "L8", "no final reports yet")]

    ledger = storage / "reports" / "final.sha256"
    known: dict[str, str] = {}
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            digest, _, ref = line.partition("  ")
            if ref:
                known[ref] = digest
    out: list[Line] = []
    new = []
    for ref, digest in finals.items():
        if ref not in known:
            new.append(f"{digest}  {ref}\n")
        elif known[ref] != digest:
            out.append(("WARN", "L8", f"{ref} changed after it was finalised; "
                                      "add a dated '## Amendment' section or a superseding file"))
    if new:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a") as fh:
            fh.writelines(new)
    return out or [("PASS", "L8", f"{len(finals)} final report(s) unchanged"
                                  + (f" ({len(new)} newly recorded)" if new else ""))]


def life(root: Path | None = None) -> list[Line]:
    today = paths.today()
    lines = l1_front_matter(today) + l2_wikilinks()
    l3, items = l3_registers()
    lines += l3 + l4_review(items, today) + l5_inbox(time.time()) + l6_journal(today)
    lines += l7_profile(today) + l8_final_reports(_storage_root(root))
    return lines


# ---------------------------------------------------------------------------
# S6
# ---------------------------------------------------------------------------

def areas() -> list[Line]:
    ids = _area_ids()
    if ids is None:
        return [("ISSUE", "S6", "me/areas.json is missing or not valid JSON")]
    out: list[Line] = []
    if sorted(ids) != sorted(registers.AREAS):
        out.append(("ISSUE", "S6", f"me/areas.json ids ({', '.join(ids)}) differ from "
                                   f"registers.AREAS ({', '.join(registers.AREAS)})"))
    allowed = set(ids) | {"none"}
    for f in _content_files():
        try:
            meta, _ = frontmatter.split(f.read_text())
        except (OSError, frontmatter.FrontMatterError):
            continue  # L1 reports it
        a = meta.get("area")
        if a is not None and a not in allowed:
            out.append(("ISSUE", "S6", f"{_rel(f)}: area '{a}' is not in me/areas.json"))
    return out or [("PASS", "S6", f"{len(ids)} areas agree across me/areas.json, "
                                  "registers.py and life/")]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_USAGE = """usage:
  python -m gogos.core.health life  [--root DIR]
  python -m gogos.core.health areas [--root DIR]"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("life", "areas") or len(args) not in (1, 3) \
            or (len(args) == 3 and args[1] != "--root"):
        print(_USAGE, file=sys.stderr)
        return 2
    root = Path(args[2]).resolve() if len(args) == 3 else None
    if root:
        paths.LIFE_ROOT, paths.ME_ROOT = root / "life", root / "me"
    lines = life(root) if args[0] == "life" else areas()
    for level, code, msg in lines:
        print(f"{level} {code} {msg}")
    return 1 if any(level == "ISSUE" for level, _, _ in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
