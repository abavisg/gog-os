"""Journal: append-only events in life/journal/YYYY-MM-DD.jsonl ("what happened").

One JSON object per line, the file dated by today() (local), the timestamp UTC:

  {"id":"01JB…","ts":"2026-10-23T08:14:02Z","type":"log.workout","area":"wellness",
   "text":"run 5k","value":30,"unit":"min","ref":null,"source":"cli","meta":{}}

`type` is dotted: log.<kind> for owner entries (LOG_KINDS) or one of
SYSTEM_TYPES. `ref` is a repo path (register item, report, approval record)
when the event is about a file. `id` is a ULID, generated here so there is no
dependency.

Appends use O_APPEND and a single write() call, so concurrent writers (two
Claude sessions, a hook) never interleave or tear a line. Lines are never
edited or removed.

The `log` CLI is the backend of the /log command. It infers the area where
the kind settles it (AREA_BY_KIND) and otherwise exits 3 with a question, so
the command can ask the owner and rerun. Two kinds have side effects:

  log waiting "X from Y"        also creates a waiting register item (owed_by Y)
  log commitment "X by Friday"  also creates a commitment with due parsed from
                                the text; anything ambiguous exits 3 to ask

Entry points:
  new_ulid() -> str
  append(event) -> id
  read(date=None) -> list[dict]
  read_range(start, end) -> list[dict]
  summarise(date=None) -> dict
  parse_due(text, today) -> (title, due)

  python -m gogos.core.journal log <type> <text> [--area A] [--value V --unit U] [--ref PATH]
                                   [--due D] [--owed-by X] [--channel C] [--goal SLUG]
  python -m gogos.core.journal read [date]
  python -m gogos.core.journal summarise [date]

Exit codes: 0 ok, 1 error, 2 usage, 3 needs an answer from the owner.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

from gogos.core import paths

AREAS = ("wellness", "finance", "growth", "family", "home", "work")

LOG_KINDS = ("activity", "decision", "learning", "note", "workout", "sleep", "weight",
             "energy", "meal", "waiting", "commitment")
SYSTEM_TYPES = ("register.created", "register.status", "apply.gmail",
                "artefact.written", "sync.run", "council.held")
AREA_BY_KIND = {"workout": "wellness", "sleep": "wellness", "weight": "wellness",
                "energy": "wellness", "meal": "wellness", "learning": "growth"}

EVENT_KEYS = ("id", "ts", "type", "area", "text", "value", "unit", "ref", "source", "meta")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TS = "%Y-%m-%dT%H:%M:%SZ"

EXIT_NEEDS_INPUT = 3


class JournalError(ValueError):
    """An event that does not fit the journal's shape."""


class NeedsInput(ValueError):
    """The owner must answer before the entry can be written (CLI exit 3)."""


# ---------------------------------------------------------------------------
# ULID
# ---------------------------------------------------------------------------

def new_ulid(ms: int | None = None, rand: int | None = None) -> str:
    """26-char Crockford base32: 48-bit millisecond time then 80 random bits."""
    if ms is None:
        ms = int(paths.now_utc().timestamp() * 1000)
    if rand is None:
        rand = secrets.randbits(80)
    n = (ms << 80) | rand
    return "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


def ulid_ms(ulid: str) -> int:
    """The millisecond timestamp encoded in a ULID."""
    n = 0
    for ch in ulid[:10]:
        n = (n << 5) | _CROCKFORD.index(ch)
    return n


# ---------------------------------------------------------------------------
# Append and read
# ---------------------------------------------------------------------------

def _validate(ev: dict) -> None:
    extra = set(ev) - set(EVENT_KEYS)
    if extra:
        raise JournalError(f"unknown event keys: {', '.join(sorted(extra))}")
    t = ev["type"]
    if t.startswith("log."):
        if t[4:] not in LOG_KINDS:
            raise JournalError(f"unknown log kind '{t[4:]}' (one of {', '.join(LOG_KINDS)})")
    elif t not in SYSTEM_TYPES:
        raise JournalError(f"unknown event type '{t}'")
    if ev["area"] not in (*AREAS, "none"):
        raise JournalError(f"unknown area '{ev['area']}'")
    v = ev["value"]
    if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
        raise JournalError(f"value must be a number, got {v!r}")
    if not isinstance(ev["meta"], dict):
        raise JournalError("meta must be an object")


def append(event: dict) -> str:
    """Append one event to today's journal in a single O_APPEND write; returns its id."""
    now = paths.now_utc()
    ev = {"id": None, "ts": now.strftime(_TS), "type": None, "area": "none", "text": "",
          "value": None, "unit": None, "ref": None, "source": "cli", "meta": {}}
    ev.update(event)
    if not ev["type"]:
        raise JournalError("event needs a type")
    ev["id"] = ev["id"] or new_ulid(int(now.timestamp() * 1000))
    _validate(ev)

    data = (json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    path = paths.journal_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(fd, data)
    finally:
        os.close(fd)
    if written != len(data):
        raise OSError(f"short write to {path}: {written} of {len(data)} bytes")
    return ev["id"]


def _read_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"WARN  journal: skipping {path}:{n}: {exc}", file=sys.stderr)
    return out


def read(day: str | None = None) -> list[dict]:
    """Every event in one day's file (default today), in append order."""
    return _read_file(paths.journal_file(day))


def read_range(start: str, end: str) -> list[dict]:
    """Every event from start to end inclusive (YYYY-MM-DD), day by day."""
    d, last = date.fromisoformat(start), date.fromisoformat(end)
    out: list[dict] = []
    while d <= last:
        out += read(d.isoformat())
        d += timedelta(days=1)
    return out


def summarise(day: str | None = None) -> dict:
    """Counts by type and area, numeric values aggregated per type and unit."""
    events = read(day)
    by_type: dict[str, int] = {}
    by_area: dict[str, int] = {}
    values: dict[str, dict[str, dict]] = {}
    for ev in events:
        by_type[ev["type"]] = by_type.get(ev["type"], 0) + 1
        by_area[ev["area"]] = by_area.get(ev["area"], 0) + 1
        v = ev.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            unit = ev.get("unit") or ""
            s = values.setdefault(ev["type"], {}).setdefault(
                unit, {"count": 0, "sum": 0, "min": v, "max": v})
            s["count"] += 1
            s["sum"] += v
            s["min"], s["max"] = min(s["min"], v), max(s["max"], v)
    for per_unit in values.values():
        for s in per_unit.values():
            s["mean"] = round(s["sum"] / s["count"], 2)
    return {"date": day or paths.today(), "count": len(events),
            "by_type": by_type, "by_area": by_area, "values": values}


# ---------------------------------------------------------------------------
# /log parsing
# ---------------------------------------------------------------------------

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Greedy title: the last by/on/before/due starts the date ("due diligence by Friday").
_DUE_PHRASE = re.compile(r"^(?P<title>.+)\s+(?:by|on|before|due)\s+(?P<when>.+?)\s*$",
                         re.IGNORECASE)
_BARE_DAY = re.compile(r"^(?P<title>.+)\s+(?P<when>today|tonight|tomorrow)\s*$", re.IGNORECASE)
_TIME = re.compile(r"^(?P<day>.+?)(?:\s+at\s+|\s*T|\s+)(?P<hh>\d{1,2}):(?P<mm>\d\d)$",
                   re.IGNORECASE)


def _weekday(word: str) -> int | None:
    w = word.lower()
    for i, name in enumerate(_WEEKDAYS):
        if len(w) >= 3 and name.startswith(w):
            return i
    return None


def _day(when: str, today: date) -> date:
    w = when.strip().lower()
    if w in ("today", "tonight"):
        return today
    if w == "tomorrow":
        return today + timedelta(days=1)
    if re.fullmatch(r"\d{4}-\d\d-\d\d", w):
        try:
            return date.fromisoformat(w)
        except ValueError:
            raise NeedsInput(f"'{when}' is not a real date") from None
    wd = _weekday(w)
    if wd is not None:
        if wd == today.weekday():
            raise NeedsInput(f"'{when}' could mean today or a week today; which date?")
        return today + timedelta(days=(wd - today.weekday()) % 7)
    raise NeedsInput(f"cannot read a due date from '{when}'; which date (YYYY-MM-DD)?")


def parse_due(text: str, today: str) -> tuple[str, str]:
    """"X by Friday" -> ("X", "2026-10-23"); a time gives YYYY-MM-DDTHH:MM.

    Understands today, tonight, tomorrow, a weekday (the next one, never
    today), and YYYY-MM-DD, each optionally followed by HH:MM. Anything else,
    including "next Friday" or 24/10, raises NeedsInput: the command asks.
    """
    m = _DUE_PHRASE.match(text.strip()) or _BARE_DAY.match(text.strip())
    if not m:
        raise NeedsInput(f"no due date in '{text}'; when is it due (YYYY-MM-DD)?")
    title, when = m.group("title"), m.group("when")
    hhmm = ""
    t = _TIME.match(when)
    if t:
        hh, mm = int(t.group("hh")), int(t.group("mm"))
        if hh > 23 or mm > 59:
            raise NeedsInput(f"'{when}' has an impossible time")
        when, hhmm = t.group("day"), f"T{hh:02d}:{mm:02d}"
    due = _day(when, date.fromisoformat(today))
    return title, due.isoformat() + hhmm


def _owed_by(text: str) -> str:
    head, sep, tail = text.rpartition(" from ")
    if not sep or not head.strip() or not tail.strip():
        raise NeedsInput(f"who owes '{text}'? (pass --owed-by)")
    return tail.strip()


def _number(raw: str) -> int | float:
    try:
        v = float(raw)
    except ValueError:
        raise JournalError(f"--value must be a number, got '{raw}'") from None
    return int(v) if v.is_integer() else v


def log(kind_or_type: str, text: str, *, area: str | None = None,
        value: str | None = None, unit: str | None = None, ref: str | None = None,
        due: str | None = None, owed_by: str | None = None, channel: str | None = None,
        goal: str | None = None, source: str = "cli") -> dict:
    """The /log backend: validate, infer area, run side effects, append. Returns the event."""
    type_ = kind_or_type if "." in kind_or_type else f"log.{kind_or_type}"
    kind = type_[4:] if type_.startswith("log.") else None
    if kind is not None and kind not in LOG_KINDS:
        raise JournalError(f"unknown log kind '{kind}' (one of {', '.join(LOG_KINDS)})")
    area = area or AREA_BY_KIND.get(kind or "")
    if area is None:
        raise NeedsInput(f"which area for this {kind or type_}? (one of {', '.join(AREAS)})")
    if area not in (*AREAS, "none"):
        raise JournalError(f"unknown area '{area}' (one of {', '.join(AREAS)})")

    if kind in ("waiting", "commitment"):
        from gogos.core import registers

        source_ref = paths.rel_ref(paths.journal_file())
        if kind == "waiting":
            fields = {"owed_by": owed_by or _owed_by(text), "source": source_ref}
            if channel:
                fields["channel"] = channel
            path = registers.create("waiting", text, area, **fields)
        else:
            if due:
                m = _DUE_PHRASE.match(text.strip())
                title = m.group("title") if m else text
            else:
                title, due = parse_due(text, paths.today())
            fields = {"due": due, "source": source_ref}
            if goal:
                fields["goal"] = goal
            path = registers.create("commitment", title, area, **fields)
        ref = paths.rel_ref(path)

    event = {"type": type_, "area": area, "text": text, "ref": ref, "source": source,
             "value": _number(value) if value is not None else None, "unit": unit}
    event["id"] = append(event)
    return event


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_USAGE = """usage:
  python -m gogos.core.journal log <type> <text> [--area A] [--value V --unit U] [--ref PATH]
                                   [--due D] [--owed-by X] [--channel C] [--goal SLUG]
  python -m gogos.core.journal read [date]
  python -m gogos.core.journal summarise [date]"""

_LOG_FLAGS = ("area", "value", "unit", "ref", "due", "owed_by", "channel", "goal")


def _confirmation(ev: dict) -> str:
    amount = f" {ev['value']}{' ' + ev['unit'] if ev['unit'] else ''}" if ev["value"] is not None else ""
    linked = f" → {ev['ref']}" if ev["ref"] else ""
    return f"OK  {ev['type']} [{ev['area']}] {ev['text']}{amount}{linked}"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd, rest = args[0], args[1:]
    try:
        if cmd == "log":
            words, flags = [], {}
            it = iter(rest)
            for tok in it:
                if tok.startswith("--"):
                    name = tok[2:].replace("-", "_")
                    if name not in _LOG_FLAGS:
                        print(f"ERROR unknown flag {tok}", file=sys.stderr)
                        return 2
                    try:
                        flags[name] = next(it)
                    except StopIteration:
                        print(f"ERROR {tok} needs a value", file=sys.stderr)
                        return 2
                else:
                    words.append(tok)
            if len(words) < 2:
                print(_USAGE, file=sys.stderr)
                return 2
            print(_confirmation(log(words[0], " ".join(words[1:]), **flags)))
        elif cmd == "read" and len(rest) <= 1:
            for ev in read(rest[0] if rest else None):
                print(json.dumps(ev, ensure_ascii=False))
        elif cmd == "summarise" and len(rest) <= 1:
            print(json.dumps(summarise(rest[0] if rest else None), indent=2))
        else:
            print(_USAGE, file=sys.stderr)
            return 2
    except NeedsInput as exc:
        print(f"ASK   {exc}", file=sys.stderr)
        return EXIT_NEEDS_INPUT
    except (JournalError, ValueError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
