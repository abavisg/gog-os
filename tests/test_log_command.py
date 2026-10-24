"""The /log backend: python -m gogos.core.journal log|read|summarise (run in-process).

2026-10-21 is a Wednesday, so "by Friday" is 2026-10-23.
"""
from __future__ import annotations

import json

import pytest

from gogos.core import journal, registers

WED = "2026-10-21T08:00:00Z"


def _events(day="2026-10-21"):
    return journal.read(day)


def test_log_workout_appends_one_line(life, clock, capsys):
    """Acceptance: /log workout "run 5k" --value 30 --unit min appends one line."""
    clock(WED)
    rc = journal.main(["log", "workout", "run 5k", "--value", "30", "--unit", "min"])
    assert rc == 0
    [ev] = _events()
    assert (ev["type"], ev["area"], ev["text"], ev["value"], ev["unit"]) == \
        ("log.workout", "wellness", "run 5k", 30, "min")
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["OK  log.workout [wellness] run 5k 30 min"]


def test_unquoted_text_words_are_joined(life, clock):
    clock(WED)
    assert journal.main(["log", "note", "called", "the", "school", "--area", "family"]) == 0
    assert _events()[0]["text"] == "called the school"


@pytest.mark.parametrize("kind,area", [("workout", "wellness"), ("sleep", "wellness"),
                                       ("weight", "wellness"), ("energy", "wellness"),
                                       ("meal", "wellness"), ("learning", "growth")])
def test_area_inferred_where_unambiguous(life, clock, kind, area):
    clock(WED)
    assert journal.main(["log", kind, "x"]) == 0
    assert _events()[0]["area"] == area


@pytest.mark.parametrize("kind", ["activity", "decision", "note", "waiting", "commitment"])
def test_area_asked_otherwise(life, clock, capsys, kind):
    clock(WED)
    assert journal.main(["log", kind, "x by Friday from Y"]) == journal.EXIT_NEEDS_INPUT
    assert "which area" in capsys.readouterr().err
    assert _events() == []


def test_explicit_area_overrides_inference(life, clock):
    clock(WED)
    journal.main(["log", "learning", "first aid course", "--area", "family"])
    assert _events()[0]["area"] == "family"


def test_log_waiting_creates_register_item_and_sets_ref(life, clock, capsys):
    """Acceptance: /log waiting "invoice from Acme" creates the item; the event refs it."""
    clock(WED)
    rc = journal.main(["log", "waiting", "invoice from Acme", "--area", "work"])
    assert rc == 0
    path = life / "registers" / "waiting" / "invoice-from-acme.md"
    item = registers.load_item(path)
    assert item.meta["owed_by"] == "Acme"
    assert item.meta["asked_on"] == "2026-10-21"
    assert item.meta["channel"] == "other"
    assert item.meta["source"] == "life/journal/2026-10-21.jsonl"

    log_ev = [e for e in _events() if e["type"] == "log.waiting"]
    assert len(log_ev) == 1
    assert log_ev[0]["ref"] == "life/registers/waiting/invoice-from-acme.md"
    assert capsys.readouterr().out.strip().endswith(
        "→ life/registers/waiting/invoice-from-acme.md")


def test_log_waiting_without_from_asks(life, clock, capsys):
    clock(WED)
    rc = journal.main(["log", "waiting", "the invoice", "--area", "work"])
    assert rc == journal.EXIT_NEEDS_INPUT and "owed-by" in capsys.readouterr().err
    assert journal.main(["log", "waiting", "the invoice", "--area", "work",
                         "--owed-by", "Acme", "--channel", "email"]) == 0
    item = registers.load_item(life / "registers" / "waiting" / "the-invoice.md")
    assert (item.meta["owed_by"], item.meta["channel"]) == ("Acme", "email")


def test_log_commitment_parses_due(life, clock):
    clock(WED)
    rc = journal.main(["log", "commitment", "Send the forms by Friday", "--area", "family"])
    assert rc == 0
    item = registers.load_item(life / "registers" / "commitment" / "send-the-forms.md")
    assert item.meta["due"] == "2026-10-23"
    assert item.meta["title"] == "Send the forms"
    [ev] = [e for e in _events() if e["type"] == "log.commitment"]
    assert ev["ref"] == "life/registers/commitment/send-the-forms.md"
    assert ev["text"] == "Send the forms by Friday"


@pytest.mark.parametrize("text,title,due", [
    ("Call the bank today", "Call the bank", "2026-10-21"),
    ("Call the bank by tomorrow", "Call the bank", "2026-10-22"),
    ("Pay the deposit by Mon", "Pay the deposit", "2026-10-26"),
    ("Review the due diligence by Friday", "Review the due diligence", "2026-10-23"),
    ("Submit form by 2026-11-03", "Submit form", "2026-11-03"),
    ("Ring the GP on Thursday at 9:05", "Ring the GP", "2026-10-22T09:05"),
    ("Ring the GP by 2026-10-29T14:30", "Ring the GP", "2026-10-29T14:30"),
])
def test_parse_due(text, title, due):
    assert journal.parse_due(text, "2026-10-21") == (title, due)


@pytest.mark.parametrize("text", [
    "Send the forms",                 # no date at all
    "Send the forms by Wednesday",    # today or a week today?
    "Send the forms by next Friday",  # some mean +7
    "Send the forms by 24/10",        # day/month order
    "Send the forms by soon",
    "Send the forms by 2026-02-30",
    "Send the forms by Friday at 25:00",
])
def test_ambiguous_due_asks_and_writes_nothing(life, clock, capsys, text):
    clock(WED)
    rc = journal.main(["log", "commitment", text, "--area", "family"])
    assert rc == journal.EXIT_NEEDS_INPUT
    assert capsys.readouterr().err.startswith("ASK")
    assert _events() == []
    assert list((life / "registers" / "commitment").glob("*.md")) == []


def test_explicit_due_answers_the_question(life, clock):
    clock(WED)
    rc = journal.main(["log", "commitment", "Send the forms by next Friday",
                       "--area", "family", "--due", "2026-10-30"])
    assert rc == 0
    item = registers.load_item(life / "registers" / "commitment" / "send-the-forms.md")
    assert item.meta["due"] == "2026-10-30"


def test_log_commitment_links_goal(life, clock):
    clock(WED)
    registers.create("goal", "Fitness", "wellness", kind="habit", target_per_week=3)
    rc = journal.main(["log", "commitment", "Gym by Friday", "--area", "wellness",
                       "--goal", "fitness"])
    assert rc == 0
    item = registers.load_item(life / "registers" / "commitment" / "gym.md")
    assert item.meta["goal"] == "fitness"


def test_unknown_kind_and_bad_value(life, clock, capsys):
    clock(WED)
    assert journal.main(["log", "dance", "tango", "--area", "growth"]) == 1
    assert journal.main(["log", "weight", "x", "--value", "heavy"]) == 1
    assert journal.main(["log", "weight", "x", "--colour", "red"]) == 2
    assert journal.main(["log", "weight"]) == 2
    assert _events() == []


def test_read_and_summarise_cli(life, clock, capsys):
    clock(WED)
    journal.main(["log", "sleep", "slept ok", "--value", "7.5", "--unit", "h"])
    capsys.readouterr()
    assert journal.main(["read", "2026-10-21"]) == 0
    [line] = capsys.readouterr().out.strip().splitlines()
    assert json.loads(line)["value"] == 7.5
    assert journal.main(["summarise"]) == 0
    assert json.loads(capsys.readouterr().out)["by_type"] == {"log.sleep": 1}
