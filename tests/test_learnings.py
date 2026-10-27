"""gogos.core.learnings and the /learn contract: propose, never apply."""
from __future__ import annotations

import pytest

from gogos.core import learnings, paths

HEADER = "# LEARNINGS.md\n\nIntro.\n\n## Entries\n"
OLDER = "### 2026-10-01: Older lesson\n- **Status:** noted\n- **Trigger:** t\n- **Lesson:** l\n"


@pytest.fixture
def log(tmp_path, monkeypatch, clock):
    clock("2026-10-27T09:00:00Z")
    f = tmp_path / "LEARNINGS.md"
    f.write_text(HEADER + "\n" + OLDER)
    monkeypatch.setattr(learnings, "learnings_file", lambda: f)
    return f


def _snapshot(root):
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_add_proposed_inserts_newest_first_and_touches_nothing_else(log, tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("original\n")
    before = _snapshot(tmp_path)
    heading = learnings.add("Fix the brief order", "owner correction", "Wellness goes first",
                            status="proposed", proposed_change="CLAUDE.md: move the line up")
    assert heading == "### 2026-10-27: Fix the brief order"
    text = log.read_text()
    assert text.index(heading) < text.index("Older lesson")
    assert "- **Status:** proposed\n" in text
    assert "- **Proposed change:** CLAUDE.md: move the line up\n" in text
    changed = {p for p, b in _snapshot(tmp_path).items() if before.get(p) != b}
    assert changed == {log}
    assert target.read_text() == "original\n"


def test_entries_keep_one_blank_line_between_them(log):
    learnings.add("A", "t", "l")
    learnings.add("B", "t", "l")
    text = log.read_text()
    assert "## Entries\n\n### 2026-10-27: B\n" in text
    assert "- **Lesson:** l\n\n### 2026-10-27: A\n" in text
    assert "- **Lesson:** l\n\n### 2026-10-01: Older lesson\n" in text


def test_add_validates(log):
    with pytest.raises(ValueError, match="needs --change"):
        learnings.add("T", "t", "l", status="proposed")
    with pytest.raises(ValueError, match="status must be"):
        learnings.add("T", "t", "l", status="rejected")
    with pytest.raises(ValueError, match="lesson is empty"):
        learnings.add("T", "t", "  ")


def test_values_are_one_line(log):
    learnings.add("Two\nlines", "t", "a\n  b")
    assert "### 2026-10-27: Two lines\n" in log.read_text()
    assert "- **Lesson:** a b\n" in log.read_text()


def test_resolve_marks_applied_with_resolution(log):
    learnings.add("Fix", "t", "l", status="proposed", proposed_change="x: y")
    learnings.resolve("Fix", "applied", "moved the line")
    text = log.read_text()
    entry = text[text.index("### 2026-10-27: Fix"):text.index("### 2026-10-01")]
    assert "- **Status:** applied\n" in entry
    assert entry.rstrip().endswith("- **Resolution:** applied 2026-10-27: moved the line")
    assert "Older lesson\n- **Status:** noted" in text


def test_resolve_unknown_title_and_bad_status(log):
    with pytest.raises(ValueError, match="no entry titled"):
        learnings.resolve("Missing", "applied", "r")
    with pytest.raises(ValueError, match="applied or rejected"):
        learnings.resolve("Older lesson", "noted", "r")


def test_cli(log, capsys):
    assert learnings.main(["add", "--title", "T", "--trigger", "t", "--lesson", "l"]) == 0
    assert "OK  ### 2026-10-27: T" in capsys.readouterr().out
    assert learnings.main(["add", "--title", "T"]) == 2
    assert learnings.main(["add", "--title", "T", "--trigger", "t", "--lesson", "l",
                           "--status", "proposed"]) == 1
    assert learnings.main(["resolve", "--title", "T", "--status", "rejected",
                           "--resolution", "not needed"]) == 0
    assert learnings.main([]) == 2


def test_real_log_has_the_entries_marker_and_format():
    text = (paths.REPO_ROOT / "docs" / "LEARNINGS.md").read_text()
    assert "\n## Entries\n" in text
    for status in learnings.STATUSES:
        assert status in text


def test_learn_command_can_only_write_through_the_script():
    text = (paths.REPO_ROOT / ".claude" / "commands" / "learn.md").read_text()
    front = text.split("---")[1]
    tools = next(line for line in front.splitlines() if line.startswith("allowed-tools:"))
    assert "Edit" not in tools and "Write" not in tools
    assert "Bash(.venv/bin/python -m gogos.core.learnings:*)" in tools
    assert "Do not apply it in this command" in text
