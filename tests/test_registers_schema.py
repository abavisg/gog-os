"""Front matter parsing and register schema validation."""
from __future__ import annotations

import pytest

from gogos.core import frontmatter, registers


def _write(life, kind, slug, meta_lines, history="- 2026-10-23T08:00:00Z created"):
    path = life / "registers" / kind / f"{slug}.md"
    path.write_text("---\n" + "\n".join(meta_lines) + "\n---\n\nBody.\n\n## History\n\n"
                    + history + "\n")
    return path


def _commitment(**over):
    meta = {
        "title": "Pay deposit", "type": "register", "status": "open", "area": "home",
        "created": "2026-10-23", "updated": "2026-10-23", "tags": "[]",
        "register": "commitment", "review_by": "2026-10-24", "source": "none",
        "related": "[]", "due": "2026-10-24", "goal": "none", "nudge_count": "0",
    }
    meta.update(over)
    return [f"{k}: {v}" for k, v in meta.items() if v is not None]


# --- frontmatter ------------------------------------------------------------

def test_frontmatter_round_trip():
    meta = {"title": "Lease: car vs buy", "count": 3, "tags": ["a", "b c"],
            "person": "[[people/sam]]", "related": ["[[people/sam]]"], "none_val": "none",
            "due": "2026-10-29T17:30", "empty": []}
    text = frontmatter.dump(meta) + "\nBody\n"
    parsed, body = frontmatter.split(text)
    assert parsed == meta
    assert body == "\nBody\n"


def test_frontmatter_accepts_bare_lists_and_wikilinks():
    parsed, _ = frontmatter.split(
        "---\ntags: [a, b]\nperson: [[people/sam]]\nrelated: [[[people/sam]], x]\n---\n")
    assert parsed == {"tags": ["a", "b"], "person": "[[people/sam]]",
                      "related": ["[[people/sam]]", "x"]}


@pytest.mark.parametrize("text", ["no front matter\n", "---\ntitle: x\n", "---\nnot a pair\n---\n"])
def test_frontmatter_rejects_malformed(text):
    with pytest.raises(frontmatter.FrontMatterError):
        frontmatter.split(text)


# --- register validation ----------------------------------------------------

def test_valid_file_loads(life):
    _write(life, "commitment", "pay-deposit", _commitment(due="2026-10-24T09:30"))
    [item] = registers.load("commitment")
    assert item.slug == "pay-deposit"
    assert item.ref == "life/registers/commitment/pay-deposit.md"


@pytest.mark.parametrize("field,over", [
    ("due", {"due": None}),
    ("due", {"due": "Friday"}),
    ("status", {"status": "done"}),
    ("area", {"area": "hobbies"}),
    ("review_by", {"review_by": "soon"}),
    ("nudge_count", {"nudge_count": "-1"}),
    ("tags", {"tags": "x"}),
    ("register", {"register": "waiting"}),
    ("type", {"type": "wiki"}),
    ("title", {"title": None}),
])
def test_invalid_field_names_path_and_field(life, field, over):
    path = _write(life, "commitment", "bad", _commitment(**over))
    with pytest.raises(registers.RegisterError) as exc:
        registers.load("commitment")
    assert exc.value.path == path
    assert exc.value.field == field
    assert str(path) in str(exc.value) and field in str(exc.value)


def test_missing_history_section_fails(life):
    path = life / "registers" / "commitment" / "x.md"
    path.write_text("---\n" + "\n".join(_commitment()) + "\n---\n\nNo history.\n")
    with pytest.raises(registers.RegisterError) as exc:
        registers.load("commitment")
    assert exc.value.field == "history"


def test_malformed_history_line_fails(life):
    _write(life, "commitment", "x", _commitment(), history="- yesterday created")
    with pytest.raises(registers.RegisterError, match="history"):
        registers.load("commitment")


def test_unknown_extra_fields_are_kept(life):
    _write(life, "commitment", "x", _commitment(counts="[workout]"))
    [item] = registers.load("commitment")
    assert item.meta["counts"] == ["workout"]


def test_outcome_goal_cannot_carry_target(life, clock):
    clock("2026-10-23T08:00:00Z")
    with pytest.raises(registers.RegisterError, match="target_per_week"):
        registers.create("goal", "Ship the shed", "home", target_per_week=3)
    path = registers.create("goal", "Run", "wellness", kind="habit", target_per_week=3)
    assert registers.load_item(path).meta["target_per_week"] == 3


def test_occasion_date_shape_follows_recurrence(life, clock):
    clock("2026-10-23T08:00:00Z")
    registers.create("occasion", "Sam birthday", "family", date="02-29",
                     person="[[people/sam]]")
    registers.create("occasion", "Recital", "family", date="2026-11-14",
                     person="[[people/sam]]", recurrence="once")
    with pytest.raises(registers.RegisterError, match="date"):
        registers.create("occasion", "Bad", "family", date="2026-11-14",
                         person="[[people/sam]]")
    with pytest.raises(registers.RegisterError, match="date"):
        registers.create("occasion", "Bad", "family", date="11-14",
                         person="[[people/sam]]", recurrence="once")


@pytest.mark.parametrize("kind,fields", [
    ("goal", {}),
    ("commitment", {"due": "2026-10-24"}),
    ("waiting", {"owed_by": "[[people/sam]]", "channel": "email"}),
    ("renewal", {"expires": "2027-01-01", "provider": "Insurer", "amount": "120 GBP"}),
    ("occasion", {"date": "05-01", "person": "[[people/sam]]"}),
    ("decision", {"confidence": "medium", "success_signal": "fewer late fees"}),
    ("parked", {"revisit_by": "2027-01-01", "origin": "life/workspaces/x/_workspace.md"}),
])
def test_every_kind_creates_and_validates(life, clock, kind, fields):
    clock("2026-10-23T08:00:00Z")
    path = registers.create(kind, f"A {kind}", "home", **fields)
    item = registers.load_item(path)
    assert item.meta["status"] == registers.STATUSES[kind][0]
    assert item.is_open


def test_index_fails_on_malformed_file_naming_path_and_field(life, clock, capsys):
    clock("2026-10-23T08:00:00Z")
    registers.create("goal", "Fine", "growth")
    path = _write(life, "commitment", "broken", _commitment(status="maybe"))
    with pytest.raises(registers.RegisterError) as exc:
        registers.index()
    assert exc.value.path == path and exc.value.field == "status"

    assert registers.main(["index"]) == 1
    err = capsys.readouterr().err
    assert str(path) in err and "status" in err


def test_index_rejects_commitment_pointing_at_unknown_goal(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "X", "work", due="2026-10-24", goal="no-such-goal")
    with pytest.raises(registers.RegisterError) as exc:
        registers.index()
    assert exc.value.path == path and exc.value.field == "goal"
