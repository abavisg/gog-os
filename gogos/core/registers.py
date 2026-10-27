"""Registers: stateful items with a lifecycle under life/registers/<kind>/<slug>.md.

Spec 2 is the schema's home. Every item carries the base front matter (title,
type: register, status, area, created, updated, tags, optional sensitivity)
plus register, review_by, source, related and the fields of its kind:

  goal        active | achieved | paused | dropped
              kind: outcome|habit, priority: 1|2|3, target_per_week: int|none (habit only)
  commitment  open | kept | missed | dropped
              due: YYYY-MM-DD[THH:MM], goal: <slug>|none, nudge_count
  waiting     open | received | dropped
              owed_by, asked_on, channel: email|chat|in-person|other, nudge_count
  renewal     open | renewed | cancelled | expired
              expires, lead_days (60), provider, amount (review_by = expires - lead_days)
  occasion    open | done | skipped
              date: MM-DD (yearly) or YYYY-MM-DD (once), person, recurrence: yearly|once
  decision    pending | reviewed
              decision_date, confidence, success_signal, outcome, superseded_by
  parked      parked | revived | dropped
              revisit_by, origin

The first status of each kind is its open status. The body ends in a mandatory
`## History` section, one line per event, appended and never rewritten:

  - 2026-10-23T08:14:02Z created
  - 2026-10-23T09:00:00Z status open → kept (note)
  - 2026-10-23T09:00:00Z due 2026-10-24 → 2026-10-27 (moved)
  - 2026-10-23T09:00:00Z nudged (2)

Derived values are computed from history and never stored (derived()):
moved_count, days_overdue, renegotiate (open commitment moved twice or more),
ignored (open waiting item nudged twice; open overdue commitment nudged twice),
idle (active outcome goal with no open commitment) and at_risk (active habit
goal where kept_this_week < target and open_this_week < target - kept, over
the ISO week containing today).

Every write is tmp file + os.replace: a concurrent writer cannot leave a torn
file; on the same item the last writer wins. Register changes are journalled
as register.created and register.status events (see gogos.core.journal).

Entry points:
  load(kind=None) -> list[Item]                 parse + validate (RegisterError names path and field)
  load_item(path) -> Item
  create(kind, title, area, **fields) -> Path
  set_status(path, new_status, note="") -> bool
  set_field(path, field, value)
  nudge(path) -> int
  derived(item, items=None, today=None) -> dict
  index() -> Path                               registers/<kind>/_index.md + registers/_index.json
  validate_all() -> (count, [RegisterError])    every item checked; nothing written

  python -m gogos.core.registers index
  python -m gogos.core.registers validate [--life DIR]
  python -m gogos.core.registers list <kind>
  python -m gogos.core.registers create <kind> --title T --area A [--<field> V ...]
  python -m gogos.core.registers status <path> <status> [--note N]
  python -m gogos.core.registers set <path> <field> <value>
  python -m gogos.core.registers nudge <path>
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from gogos.core import frontmatter, journal, paths

AREAS = ("wellness", "finance", "growth", "family", "home", "work")

STATUSES: dict[str, tuple[str, ...]] = {
    "goal": ("active", "achieved", "paused", "dropped"),
    "commitment": ("open", "kept", "missed", "dropped"),
    "waiting": ("open", "received", "dropped"),
    "renewal": ("open", "renewed", "cancelled", "expired"),
    "occasion": ("open", "done", "skipped"),
    "decision": ("pending", "reviewed"),
    "parked": ("parked", "revived", "dropped"),
}
KINDS = tuple(STATUSES)

BASE_FIELDS = ("title", "type", "status", "area", "created", "updated", "tags",
               "sensitivity", "register", "review_by", "source", "related")

# Fields only the store itself changes; set_field refuses them.
MANAGED_FIELDS = frozenset({"type", "status", "created", "updated", "register",
                            "nudge_count", "review_by"})

RENEWAL_LEAD_DAYS = 60
# A waiting item is due a look a week after the ask unless review_by is given.
WAITING_REVIEW_DAYS = 7
RENEGOTIATE_MOVES = 2
IGNORED_NUDGES = 2

_REQUIRED = object()

# kind -> {field: default}; _REQUIRED means create() must be given it.
KIND_FIELDS: dict[str, dict] = {
    "goal": {"kind": "outcome", "priority": 2, "target_per_week": "none"},
    "commitment": {"due": _REQUIRED, "goal": "none", "nudge_count": 0},
    "waiting": {"owed_by": _REQUIRED, "asked_on": None, "channel": "other",
                "nudge_count": 0},
    "renewal": {"expires": _REQUIRED, "lead_days": RENEWAL_LEAD_DAYS,
                "provider": _REQUIRED, "amount": "unknown"},
    "occasion": {"date": _REQUIRED, "person": _REQUIRED, "recurrence": "yearly"},
    "decision": {"decision_date": None, "confidence": _REQUIRED,
                 "success_signal": _REQUIRED, "outcome": "pending",
                 "superseded_by": "none"},
    "parked": {"revisit_by": _REQUIRED, "origin": "none"},
}

_TS = "%Y-%m-%dT%H:%M:%SZ"
_HISTORY_LINE = re.compile(r"^- (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) (.+)$")
_MOVED = re.compile(r"^due \S+ → \S+ \(moved\)$")
_STATUS_EVENT = re.compile(r"^status (\S+) → (\S+)")
_DATE = re.compile(r"^\d{4}-\d\d-\d\d$")
_DUE = re.compile(r"^\d{4}-\d\d-\d\d(T\d\d:\d\d)?$")
_MMDD = re.compile(r"^\d\d-\d\d$")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class RegisterError(ValueError):
    """An invalid register file or operation; names the path and the field."""

    def __init__(self, path: Path | str, field: str, message: str) -> None:
        super().__init__(f"{path}: field '{field}': {message}")
        self.path = Path(path)
        self.field = field


@dataclass
class Item:
    path: Path
    kind: str
    meta: dict
    body: str
    history: list[tuple[str, str]] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.path.stem

    @property
    def ref(self) -> str:
        return paths.rel_ref(self.path)

    @property
    def status(self) -> str:
        return self.meta["status"]

    @property
    def is_open(self) -> bool:
        return self.meta["status"] == STATUSES[self.kind][0]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _is_date(v) -> bool:
    if not isinstance(v, str) or not _DATE.match(v):
        return False
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _is_due(v) -> bool:
    if not isinstance(v, str) or not _DUE.match(v):
        return False
    try:
        datetime.fromisoformat(v)
    except ValueError:
        return False
    return True


def _is_mmdd(v) -> bool:
    if not isinstance(v, str) or not _MMDD.match(v):
        return False
    try:
        date.fromisoformat(f"2000-{v}")  # a leap year, so 02-29 is valid
    except ValueError:
        return False
    return True


def _is_text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _is_count(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _check(path: Path, meta: dict, name: str, ok: bool, expected: str) -> None:
    if name not in meta:
        raise RegisterError(path, name, "missing")
    if not ok:
        raise RegisterError(path, name, f"expected {expected}, got {meta[name]!r}")


def _enum(meta: dict, name: str, values: tuple) -> bool:
    return meta.get(name) in values


def validate(path: Path, kind: str, meta: dict) -> None:
    """Raise RegisterError for the first invalid field; unknown extra fields pass."""
    m = meta
    _check(path, m, "title", _is_text(m.get("title")), "non-empty text")
    _check(path, m, "type", m.get("type") == "register", "'register'")
    _check(path, m, "register", m.get("register") == kind, f"'{kind}' (its directory)")
    _check(path, m, "status", _enum(m, "status", STATUSES[kind]),
           " | ".join(STATUSES[kind]))
    _check(path, m, "area", _enum(m, "area", (*AREAS, "none")),
           " | ".join((*AREAS, "none")))
    _check(path, m, "created", _is_date(m.get("created")), "YYYY-MM-DD")
    _check(path, m, "updated", _is_date(m.get("updated")), "YYYY-MM-DD")
    _check(path, m, "tags", isinstance(m.get("tags"), list), "a list")
    rb = m.get("review_by")
    _check(path, m, "review_by", rb == "none" or _is_date(rb), "YYYY-MM-DD or none")
    _check(path, m, "source", _is_text(m.get("source")), "a path, [[wikilink]] or none")
    _check(path, m, "related", isinstance(m.get("related"), list), "a list")
    if "sensitivity" in m:
        _check(path, m, "sensitivity", _is_text(m["sensitivity"]), "text")

    if kind == "goal":
        _check(path, m, "kind", _enum(m, "kind", ("outcome", "habit")), "outcome | habit")
        _check(path, m, "priority", _enum(m, "priority", (1, 2, 3)), "1 | 2 | 3")
        t = m.get("target_per_week")
        if m["kind"] == "habit":
            _check(path, m, "target_per_week",
                   t == "none" or (_is_count(t) and t > 0), "a positive int or none")
        else:
            _check(path, m, "target_per_week", t == "none", "none (habit goals only)")
    elif kind == "commitment":
        _check(path, m, "due", _is_due(m.get("due")), "YYYY-MM-DD or YYYY-MM-DDTHH:MM")
        g = m.get("goal")
        _check(path, m, "goal", g == "none" or (isinstance(g, str) and bool(_SLUG.match(g))),
               "a goal slug or none")
        _check(path, m, "nudge_count", _is_count(m.get("nudge_count")), "an int >= 0")
    elif kind == "waiting":
        _check(path, m, "owed_by", _is_text(m.get("owed_by")), "a name or [[people/x]]")
        _check(path, m, "asked_on", _is_date(m.get("asked_on")), "YYYY-MM-DD")
        _check(path, m, "channel", _enum(m, "channel", ("email", "chat", "in-person", "other")),
               "email | chat | in-person | other")
        _check(path, m, "nudge_count", _is_count(m.get("nudge_count")), "an int >= 0")
    elif kind == "renewal":
        _check(path, m, "expires", _is_date(m.get("expires")), "YYYY-MM-DD")
        _check(path, m, "lead_days", _is_count(m.get("lead_days")), "an int >= 0")
        _check(path, m, "provider", _is_text(m.get("provider")), "text")
        _check(path, m, "amount", _is_text(m.get("amount")), "text or unknown")
    elif kind == "occasion":
        _check(path, m, "recurrence", _enum(m, "recurrence", ("yearly", "once")),
               "yearly | once")
        if m["recurrence"] == "yearly":
            _check(path, m, "date", _is_mmdd(m.get("date")), "MM-DD for a yearly occasion")
        else:
            _check(path, m, "date", _is_date(m.get("date")), "YYYY-MM-DD for a one-off")
        _check(path, m, "person", _is_text(m.get("person")), "[[people/x]]")
    elif kind == "decision":
        _check(path, m, "decision_date", _is_date(m.get("decision_date")), "YYYY-MM-DD")
        _check(path, m, "confidence", _enum(m, "confidence", ("high", "medium", "low")),
               "high | medium | low")
        _check(path, m, "success_signal", _is_text(m.get("success_signal")), "text")
        _check(path, m, "outcome", _enum(m, "outcome", (
            "pending", "helped", "did-not-help", "inconclusive", "not-reviewed")),
            "pending | helped | did-not-help | inconclusive | not-reviewed")
        _check(path, m, "superseded_by", _is_text(m.get("superseded_by")), "a path or none")
    elif kind == "parked":
        _check(path, m, "revisit_by", _is_date(m.get("revisit_by")), "YYYY-MM-DD")
        _check(path, m, "origin", _is_text(m.get("origin")), "a path or none")


def _parse_history(path: Path, body: str) -> list[tuple[str, str]]:
    parts = re.split(r"^## History[ \t]*$", body, maxsplit=1, flags=re.M)
    if len(parts) < 2:
        raise RegisterError(path, "history", "missing '## History' section")
    section = re.split(r"^## ", parts[1], maxsplit=1, flags=re.M)[0]
    out = []
    for line in section.splitlines():
        if not line.strip():
            continue
        m = _HISTORY_LINE.match(line)
        if not m:
            raise RegisterError(path, "history",
                                f"line is not '- <UTC timestamp> <event>': {line!r}")
        out.append((m.group(1), m.group(2)))
    return out


def load_item(path: Path) -> Item:
    path = Path(path)
    kind = path.parent.name
    if kind not in STATUSES:
        raise RegisterError(path, "register", f"not under a register kind directory ({kind})")
    try:
        meta, body = frontmatter.split(path.read_text())
    except frontmatter.FrontMatterError as exc:
        raise RegisterError(path, exc.field or "front matter", str(exc)) from exc
    validate(path, kind, meta)
    return Item(path=path, kind=kind, meta=meta, body=body,
                history=_parse_history(path, body))


def _item_paths(kind: str) -> list[Path]:
    d = paths.registers_dir(kind)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md") if not p.name.startswith("_"))


def load(kind: str | None = None) -> list[Item]:
    """Every item of `kind` (or of all kinds), validated. Fails on the first bad file."""
    if kind is not None and kind not in STATUSES:
        raise ValueError(f"unknown register kind '{kind}' (one of {', '.join(KINDS)})")
    kinds = [kind] if kind else list(KINDS)
    return [load_item(p) for k in kinds for p in _item_paths(k)]


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _stamp() -> str:
    return paths.now_utc().strftime(_TS)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _ordered(kind: str, meta: dict) -> dict:
    keys = [*BASE_FIELDS, *KIND_FIELDS[kind]]
    out = {k: meta[k] for k in keys if k in meta}
    out.update({k: v for k, v in meta.items() if k not in out})
    return out


def _render(item_kind: str, meta: dict, body: str) -> str:
    return frontmatter.dump(_ordered(item_kind, meta)) + body


def _append_history(body: str, line: str) -> str:
    """Insert a history line at the end of the History section; nothing else moves."""
    m = re.search(r"^## History[ \t]*$", body, flags=re.M)
    nxt = re.search(r"^## ", body[m.end():], flags=re.M) if m else None
    if m is None or nxt is None:
        return body.rstrip("\n") + "\n" + line + "\n"
    cut = m.end() + nxt.start()
    head = body[:cut].rstrip("\n")
    return head + "\n" + line + "\n\n" + body[cut:]


def _save(item: Item, event: str) -> None:
    item.meta["updated"] = paths.today()
    validate(item.path, item.kind, item.meta)
    item.body = _append_history(item.body, f"- {_stamp()} {event}")
    _atomic_write(item.path, _render(item.kind, item.meta, item.body))


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "item"


def _coerce(value):
    """CLI values arrive as strings; ints become ints, everything else stays."""
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _days_before(day: str, n: int) -> str:
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()


def _default_review_by(kind: str, meta: dict) -> str:
    try:
        if kind == "commitment":
            return str(meta["due"])[:10]
        if kind == "waiting":
            return _days_before(meta["asked_on"], -WAITING_REVIEW_DAYS)
        if kind == "renewal":
            return _days_before(meta["expires"], int(meta["lead_days"]))
        if kind == "parked":
            return meta["revisit_by"]
    except (KeyError, TypeError, ValueError):
        return "none"  # validation reports the underlying field
    return "none"


def create(kind: str, title: str, area: str, /, **fields) -> Path:
    """Write a new item; slug from title, a collision gets -2, -3, ... Returns its path.

    kind, title and area are positional-only, so a goal's own `kind` field
    (outcome or habit) can be passed as a keyword.
    """
    if kind not in STATUSES:
        raise ValueError(f"unknown register kind '{kind}' (one of {', '.join(KINDS)})")
    body = fields.pop("body", "")
    fields = {k: _coerce(v) for k, v in fields.items()}

    base = slugify(title)
    d = paths.registers_dir(kind)
    path, n = d / f"{base}.md", 1
    while path.exists():
        n += 1
        path = d / f"{base}-{n}.md"

    today = paths.today()
    meta: dict = {
        "title": title, "type": "register", "status": STATUSES[kind][0],
        "area": area, "created": today, "updated": today,
        "tags": fields.pop("tags", []), "register": kind,
    }
    for name, default in KIND_FIELDS[kind].items():
        if name in fields:
            meta[name] = fields.pop(name)
        elif default is _REQUIRED:
            raise RegisterError(path, name, f"required to create a {kind}")
        elif default is None:
            meta[name] = today  # date fields defaulting to today
        else:
            meta[name] = default
    meta["review_by"] = fields.pop("review_by", None) or _default_review_by(kind, meta)
    meta["source"] = fields.pop("source", "none")
    meta["related"] = fields.pop("related", [])
    meta.update(fields)

    validate(path, kind, meta)
    text = (body.strip() + "\n\n" if body.strip() else "")
    text += f"## History\n\n- {_stamp()} created\n"
    _atomic_write(path, _render(kind, meta, "\n" + text))
    journal.append({"type": "register.created", "area": area, "text": f"{kind}: {title}",
                    "ref": paths.rel_ref(path), "source": "registers",
                    "meta": {"register": kind}})
    return path


def set_status(path: Path, new_status: str, note: str = "") -> bool:
    """Change status, appending a history line. False when already in that status."""
    item = load_item(path)
    if new_status not in STATUSES[item.kind]:
        raise RegisterError(item.path, "status",
                            f"'{new_status}' is not one of {' | '.join(STATUSES[item.kind])}")
    old = item.meta["status"]
    if old == new_status:
        return False
    item.meta["status"] = new_status
    _save(item, f"status {old} → {new_status}" + (f" ({note})" if note else ""))
    journal.append({"type": "register.status", "area": item.meta["area"],
                    "text": f"{item.kind}: {item.meta['title']} {old} → {new_status}",
                    "ref": item.ref, "source": "registers",
                    "meta": {"register": item.kind, "from": old, "to": new_status,
                             "note": note}})
    return True


def set_field(path: Path, name: str, value) -> None:
    """Change one field, appending "name old → new"; a commitment's due adds "(moved)"."""
    item = load_item(path)
    if name in MANAGED_FIELDS:
        raise RegisterError(item.path, name, "managed by the store; use status or nudge")
    value = _coerce(value)
    old = item.meta.get(name, "none")
    if old == value:
        return
    item.meta[name] = value
    validate(item.path, item.kind, item.meta)  # before review_by follows the new value
    if item.kind == "commitment" and name == "due":
        if item.meta["review_by"] == str(old)[:10]:
            item.meta["review_by"] = str(value)[:10]
    if item.kind == "renewal" and name in ("expires", "lead_days"):
        item.meta["review_by"] = _default_review_by("renewal", item.meta)
    moved = " (moved)" if item.kind == "commitment" and name == "due" else ""
    _save(item, f"{name} {old} → {value}{moved}")


def nudge(path: Path) -> int:
    """nudge_count += 1 with a history line; returns the new count."""
    item = load_item(path)
    if "nudge_count" not in KIND_FIELDS[item.kind]:
        raise RegisterError(item.path, "nudge_count", f"a {item.kind} has no nudge_count")
    item.meta["nudge_count"] += 1
    _save(item, f"nudged ({item.meta['nudge_count']})")
    return item.meta["nudge_count"]


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------

def _local_date(ts: str) -> date:
    """A history timestamp (UTC) as the owner's local date."""
    utc = datetime.strptime(ts, _TS).replace(tzinfo=timezone.utc)
    return utc.astimezone(paths.local_tz()).date()


def moved_count(item: Item) -> int:
    return sum(1 for _, ev in item.history if _MOVED.match(ev))


def _deadline(item: Item) -> str | None:
    d = item.meta.get("due") if item.kind == "commitment" else item.meta.get("review_by")
    return str(d)[:10] if d and d != "none" else None


def _kept_on(item: Item) -> date | None:
    for ts, ev in reversed(item.history):
        m = _STATUS_EVENT.match(ev)
        if m and m.group(2) == "kept":
            return _local_date(ts)
    return None


def derived(item: Item, items: list[Item] | None = None, today: str | None = None) -> dict:
    """Values computed from history and the other items; never stored."""
    day = date.fromisoformat(today or paths.today())
    out = {"moved_count": moved_count(item), "days_overdue": None, "renegotiate": False,
           "ignored": False, "idle": False, "at_risk": False}

    deadline = _deadline(item)
    if deadline:
        out["days_overdue"] = max(0, (day - date.fromisoformat(deadline)).days) \
            if item.is_open else 0

    if item.kind == "commitment" and item.is_open:
        out["renegotiate"] = out["moved_count"] >= RENEGOTIATE_MOVES
        out["ignored"] = (out["days_overdue"] or 0) > 0 \
            and item.meta["nudge_count"] >= IGNORED_NUDGES
    elif item.kind == "waiting" and item.is_open:
        out["ignored"] = item.meta["nudge_count"] >= IGNORED_NUDGES
    elif item.kind == "goal" and item.is_open:
        if items is None:
            items = load()
        linked = [c for c in items if c.kind == "commitment"
                  and c.meta.get("goal") == item.slug]
        open_linked = [c for c in linked if c.is_open]
        if item.meta["kind"] == "outcome":
            out["idle"] = not open_linked
        elif isinstance(item.meta.get("target_per_week"), int):
            target = item.meta["target_per_week"]
            monday = day - timedelta(days=day.weekday())
            sunday = monday + timedelta(days=6)
            kept = sum(1 for c in linked if c.status == "kept"
                       and (k := _kept_on(c)) is not None and monday <= k <= sunday)
            scheduled = sum(1 for c in open_linked
                            if monday <= date.fromisoformat(str(c.meta["due"])[:10]) <= sunday)
            out["at_risk"] = kept < target and scheduled < target - kept
    return out


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _check_references(items: list[Item]) -> None:
    goals = {i.slug for i in items if i.kind == "goal"}
    for i in items:
        if i.kind == "commitment" and i.meta["goal"] != "none" and i.meta["goal"] not in goals:
            raise RegisterError(i.path, "goal", f"no goal '{i.meta['goal']}' in registers/goal/")


def validate_all() -> tuple[int, list[RegisterError]]:
    """Check every item and the goal references without writing anything.

    Unlike load(), it does not stop at the first bad file: the health check
    (L3) reports every finding in one run.
    """
    items: list[Item] = []
    errors: list[RegisterError] = []
    count = 0
    for kind in KINDS:
        for p in _item_paths(kind):
            count += 1
            try:
                items.append(load_item(p))
            except RegisterError as exc:
                errors.append(exc)
    try:
        _check_references(items)
    except RegisterError as exc:
        errors.append(exc)
    return count, errors


def _review_key(rec: dict) -> tuple:
    rb = rec["review_by"]
    return (rb == "none", rb, rec["ref"])


def _flags(d: dict) -> str:
    flags = []
    if d["days_overdue"]:
        flags.append(f"overdue {d['days_overdue']}d")
    if d["renegotiate"]:
        flags.append(f"renegotiate (moved {d['moved_count']}x)")
    for name in ("ignored", "idle"):
        if d[name]:
            flags.append(name)
    if d["at_risk"]:
        flags.append("at risk")
    return ", ".join(flags)


def _cell(text) -> str:
    return str(text).replace("|", "\\|")


def _kind_md(kind: str, open_recs: list[dict], closed_recs: list[dict],
             stamp: str, today: str) -> str:
    meta = {"title": f"{kind.title()} register index", "type": "register",
            "status": "index", "area": "none", "created": today, "updated": today,
            "tags": ["generated"], "register": kind}
    lines = [f"# {kind.title()} register", "",
             f"Generated by `python -m gogos.core.registers index` at {stamp}. "
             "Do not edit; edit the items.", "", "## Open, by review date", ""]
    if open_recs:
        lines += ["| Review by | Item | Status | Area | Flags |", "|---|---|---|---|---|"]
        lines += [f"| {r['review_by']} | [{_cell(r['title'])}]({r['slug']}.md) | "
                  f"{r['status']} | {r['area']} | {_flags(r['derived'])} |" for r in open_recs]
    else:
        lines.append("No open items.")
    lines += ["", "## Other", ""]
    if closed_recs:
        lines += ["| Updated | Item | Status | Area |", "|---|---|---|---|"]
        lines += [f"| {r['updated']} | [{_cell(r['title'])}]({r['slug']}.md) | "
                  f"{r['status']} | {r['area']} |" for r in closed_recs]
    else:
        lines.append("None.")
    return frontmatter.dump(meta) + "\n" + "\n".join(lines) + "\n"


def index() -> Path:
    """Validate every item, then write each kind's _index.md and registers/_index.json."""
    items = load()
    _check_references(items)
    today = paths.today()
    stamp = _stamp()

    records = []
    for i in items:
        # The kind is the `register` field; a goal's own `kind` is outcome | habit.
        records.append({"ref": i.ref, "slug": i.slug, **i.meta,
                        "open": i.is_open, "derived": derived(i, items, today)})
    open_recs = sorted((r for r in records if r["open"]), key=_review_key)
    closed_recs = sorted((r for r in records if not r["open"]),
                         key=lambda r: (r["updated"], r["ref"]), reverse=True)

    for kind in KINDS:
        _atomic_write(paths.registers_dir(kind) / "_index.md", _kind_md(
            kind, [r for r in open_recs if r["register"] == kind],
            [r for r in closed_recs if r["register"] == kind], stamp, today))

    out = paths.registers_dir() / "_index.json"
    _atomic_write(out, json.dumps({
        "generated_at": stamp, "today": today,
        "open": open_recs, "closed": closed_recs,
    }, indent=2, ensure_ascii=False) + "\n")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve(arg: str) -> Path:
    return paths.resolve_ref(arg)


def _parse_flags(args: list[str]) -> dict:
    out: dict = {}
    it = iter(args)
    for flag in it:
        if not flag.startswith("--"):
            raise ValueError(f"expected --field value, got '{flag}'")
        try:
            out[flag[2:].replace("-", "_")] = next(it)
        except StopIteration:
            raise ValueError(f"{flag} needs a value") from None
    return out


_USAGE = """usage:
  python -m gogos.core.registers index
  python -m gogos.core.registers validate [--life DIR]
  python -m gogos.core.registers list <kind>
  python -m gogos.core.registers create <kind> --title T --area A [--<field> V ...]
  python -m gogos.core.registers status <path> <status> [--note N]
  python -m gogos.core.registers set <path> <field> <value>
  python -m gogos.core.registers nudge <path>"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd, rest = args[0], args[1:]
    try:
        if cmd == "index":
            print(f"OK  {paths.rel_ref(index())}")
        elif cmd == "validate" and len(rest) in (0, 2):
            if rest:
                if rest[0] != "--life":
                    print(_USAGE, file=sys.stderr)
                    return 2
                paths.LIFE_ROOT = Path(rest[1]).resolve()
            count, errors = validate_all()
            for exc in errors:
                print(f"ERROR {exc}", file=sys.stderr)
            if errors:
                return 1
            print(f"OK  {count} register items valid")
        elif cmd == "list" and len(rest) == 1:
            if rest[0] not in STATUSES:
                print(f"ERROR unknown register kind '{rest[0]}' "
                      f"(one of {', '.join(KINDS)})", file=sys.stderr)
                return 2
            for i in sorted(load(rest[0]), key=lambda i: (not i.is_open, i.slug)):
                print(f"{i.status:<9} {i.meta['review_by']:<10} {i.slug}  {i.meta['title']}")
        elif cmd == "create" and rest:
            kind, flags = rest[0], _parse_flags(rest[1:])
            if kind not in STATUSES:
                print(f"ERROR unknown register kind '{kind}'", file=sys.stderr)
                return 2
            title, area = flags.pop("title", None), flags.pop("area", None)
            if not title or not area:
                print("ERROR create needs --title and --area", file=sys.stderr)
                return 2
            print(f"OK  created {paths.rel_ref(create(kind, title, area, **flags))}")
        elif cmd == "status" and len(rest) >= 2:
            flags = _parse_flags(rest[2:])
            changed = set_status(_resolve(rest[0]), rest[1], note=flags.get("note", ""))
            print(f"OK  {rest[0]} {'→ ' + rest[1] if changed else 'already ' + rest[1]}")
        elif cmd == "set" and len(rest) == 3:
            set_field(_resolve(rest[0]), rest[1], rest[2])
            print(f"OK  {rest[0]} {rest[1]} = {rest[2]}")
        elif cmd == "nudge" and len(rest) == 1:
            print(f"OK  {rest[0]} nudged ({nudge(_resolve(rest[0]))})")
        else:
            print(_USAGE, file=sys.stderr)
            return 2
    except (RegisterError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
