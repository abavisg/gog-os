"""gogos.core.journal: event shape, ULIDs, O_APPEND appends, read and summarise."""
from __future__ import annotations

import json
import multiprocessing

import pytest

from gogos.core import journal, paths, registers


def test_ulid_shape_and_time_prefix():
    a = journal.new_ulid(ms=1_700_000_000_000, rand=0)
    b = journal.new_ulid(ms=1_700_000_000_001, rand=2**80 - 1)
    assert len(a) == len(b) == 26
    assert set(a + b) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert a < b  # lexicographic order follows time
    assert journal.ulid_ms(a) == 1_700_000_000_000
    assert len({journal.new_ulid() for _ in range(1000)}) == 1000


def test_append_writes_the_spec_event_shape(life, clock):
    clock("2026-10-23T08:14:02Z")
    eid = journal.append({"type": "log.workout", "area": "wellness", "text": "run 5k",
                          "value": 30, "unit": "min"})
    lines = (life / "journal" / "2026-10-23.jsonl").read_text().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert list(ev) == list(journal.EVENT_KEYS)
    assert ev == {"id": eid, "ts": "2026-10-23T08:14:02Z", "type": "log.workout",
                  "area": "wellness", "text": "run 5k", "value": 30, "unit": "min",
                  "ref": None, "source": "cli", "meta": {}}
    assert journal.ulid_ms(eid) == int(paths.now_utc().timestamp() * 1000)


def test_file_date_is_local_today_not_utc(life, clock):
    # 23:30 UTC on the 23rd is already the 24th in a UTC+3 zone.
    clock("2026-10-23T23:30:00Z", "2026-10-24")
    journal.append({"type": "log.note", "text": "late"})
    assert (life / "journal" / "2026-10-24.jsonl").exists()


@pytest.mark.parametrize("event,msg", [
    ({"type": "log.dance"}, "unknown log kind"),
    ({"type": "made.up"}, "unknown event type"),
    ({"type": "log.note", "area": "hobbies"}, "unknown area"),
    ({"type": "log.weight", "value": "80"}, "number"),
    ({"type": "log.note", "colour": "red"}, "unknown event keys"),
    ({"text": "no type"}, "needs a type"),
])
def test_append_rejects_bad_events(life, clock, event, msg):
    clock("2026-10-23T08:00:00Z")
    with pytest.raises(journal.JournalError, match=msg):
        journal.append(event)
    assert not (life / "journal" / "2026-10-23.jsonl").exists()


def test_system_types_accepted(life, clock):
    clock("2026-10-23T08:00:00Z")
    for t in journal.SYSTEM_TYPES:
        journal.append({"type": t, "ref": "life/reports/x.md"})
    assert [e["type"] for e in journal.read("2026-10-23")] == list(journal.SYSTEM_TYPES)


def test_append_never_rewrites_existing_lines(life, clock):
    clock("2026-10-23T08:00:00Z")
    journal.append({"type": "log.note", "text": "one"})
    path = life / "journal" / "2026-10-23.jsonl"
    before = path.read_bytes()
    journal.append({"type": "log.note", "text": "two"})
    assert path.read_bytes().startswith(before)


def _hammer(n: int, tag: str, start) -> None:
    start.wait()
    for i in range(n):
        journal.append({"type": "log.note", "text": f"{tag}-{i}-" + "x" * 3000})


def test_concurrent_appends_produce_intact_lines(life, clock):
    """Acceptance: two concurrent appends produce two intact lines (stressed here)."""
    clock("2026-10-23T08:00:00Z")
    ctx = multiprocessing.get_context("fork")  # children inherit the tmp LIFE_ROOT
    start = ctx.Event()
    procs = [ctx.Process(target=_hammer, args=(200, tag, start)) for tag in ("a", "b")]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = (life / "journal" / "2026-10-23.jsonl").read_text().splitlines()
    assert len(lines) == 400
    events = [json.loads(line) for line in lines]  # every line parses whole
    assert len({e["id"] for e in events}) == 400
    for tag in ("a", "b"):
        assert sorted(int(e["text"].split("-")[1]) for e in events
                      if e["text"].startswith(tag + "-")) == list(range(200))


def test_two_concurrent_appends_two_lines(life, clock):
    clock("2026-10-23T08:00:00Z")
    ctx = multiprocessing.get_context("fork")
    start = ctx.Event()
    procs = [ctx.Process(target=_hammer, args=(1, tag, start)) for tag in ("a", "b")]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(timeout=30)
    events = journal.read("2026-10-23")
    assert sorted(e["text"][:4] for e in events) == ["a-0-", "b-0-"]


def test_read_skips_a_corrupt_line_with_a_warning(life, clock, capsys):
    clock("2026-10-23T08:00:00Z")
    journal.append({"type": "log.note", "text": "ok"})
    with open(life / "journal" / "2026-10-23.jsonl", "a") as fh:
        fh.write("{not json\n")
    assert [e["text"] for e in journal.read("2026-10-23")] == ["ok"]
    assert "2026-10-23.jsonl:2" in capsys.readouterr().err


def test_read_missing_day_is_empty(life):
    assert journal.read("2020-01-01") == []


def test_read_range_inclusive(life, clock):
    for day in ("2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"):
        clock(f"{day}T08:00:00Z")
        journal.append({"type": "log.note", "text": day})
    got = [e["text"] for e in journal.read_range("2026-10-22", "2026-10-23")]
    assert got == ["2026-10-22", "2026-10-23"]


def test_summarise_counts_and_aggregates(life, clock):
    clock("2026-10-23T08:00:00Z")
    journal.append({"type": "log.workout", "area": "wellness", "value": 30, "unit": "min"})
    journal.append({"type": "log.workout", "area": "wellness", "value": 45, "unit": "min"})
    journal.append({"type": "log.sleep", "area": "wellness", "value": 7.5, "unit": "h"})
    journal.append({"type": "log.learning", "area": "growth", "text": "chapter 3"})
    s = journal.summarise("2026-10-23")
    assert s["count"] == 4
    assert s["by_type"] == {"log.workout": 2, "log.sleep": 1, "log.learning": 1}
    assert s["by_area"] == {"wellness": 3, "growth": 1}
    assert s["values"]["log.workout"]["min"] == {"count": 2, "sum": 75, "min": 30,
                                                 "max": 45, "mean": 37.5}
    assert s["values"]["log.sleep"]["h"]["sum"] == 7.5
    assert "log.learning" not in s["values"]


def test_register_changes_are_journalled(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "Book MOT", "home", due="2026-10-30")
    registers.set_field(path, "due", "2026-10-31")
    registers.set_status(path, "kept", note="done early")
    events = journal.read("2026-10-23")
    assert [e["type"] for e in events] == ["register.created", "register.status"]
    assert all(e["ref"] == "life/registers/commitment/book-mot.md" for e in events)
    assert events[0]["area"] == "home"
    assert events[1]["meta"] == {"register": "commitment", "from": "open", "to": "kept",
                                 "note": "done early"}
