"""gogos.core.health: the LIFE half and S6, and the bridge to registers.py.

The bridge tests are spec 8's: L3 must be registers.validate_all() and the
bash script must not restate the register schema.
"""
from __future__ import annotations

import json
import os
import time

from gogos.core import health, paths, registers

SCRIPT = paths.REPO_ROOT / ".claude" / "scripts" / "health-check.sh"


def _page(life, rel, **meta):
    base = {"title": "Page", "type": "wiki", "status": "current", "area": "home",
            "created": "2026-10-01", "updated": "2026-10-01", "tags": "[]"}
    base.update(meta)
    p = life / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + "".join(f"{k}: {v}\n" for k, v in base.items() if v is not None)
                 + "---\n\nBody.\n")
    return p


def _codes(lines, level):
    return [(c, m) for lv, c, m in lines if lv == level]


# --- the bridge -----------------------------------------------------------------

def test_l3_is_registers_validate_all(life, monkeypatch):
    err = registers.RegisterError(life / "registers/goal/x.md", "kind", "synthetic")
    monkeypatch.setattr(registers, "validate_all", lambda: (1, [err]))
    lines, items = health.l3_registers()
    assert lines == [("WARN", "L3", str(err))]
    assert items == []


def test_health_script_calls_python_and_restates_no_schema():
    text = SCRIPT.read_text()
    assert "-m gogos.core.health life" in text
    assert "-m gogos.core.health areas" in text
    for kind, statuses in registers.STATUSES.items():
        assert " ".join(statuses) not in text, kind
        assert "|".join(statuses) not in text, kind
    for field in ("nudge_count", "target_per_week", "lead_days", "recurrence"):
        assert field not in text


def test_validate_all_reports_every_bad_file_and_writes_nothing(life, clock):
    clock("2026-10-24T09:00:00Z")
    registers.create("waiting", "Invoice", "finance", owed_by="Supplier")
    for slug in ("one", "two"):
        (life / "registers/goal" / f"{slug}.md").write_text("---\ntitle: x\n---\n")
    before = sorted(p.name for p in (life / "registers").rglob("*"))
    count, errors = registers.validate_all()
    assert count == 3
    assert sorted(e.path.name for e in errors) == ["one.md", "two.md"]
    assert sorted(p.name for p in (life / "registers").rglob("*")) == before


def test_validate_all_checks_goal_references(life, clock):
    clock("2026-10-24T09:00:00Z")
    registers.create("commitment", "Book lesson", "growth", due="2026-10-30", goal="no-such-goal")
    _, errors = registers.validate_all()
    assert [e.field for e in errors] == ["goal"]


def test_validate_cli(life, clock, capsys):
    clock("2026-10-24T09:00:00Z")
    registers.create("waiting", "Invoice", "finance", owed_by="Supplier")
    assert registers.main(["validate"]) == 0
    assert "1 register items valid" in capsys.readouterr().out
    (life / "registers/goal/bad.md").write_text("no front matter\n")
    assert registers.main(["validate", "--life", str(life)]) == 1
    assert "bad.md" in capsys.readouterr().err
    assert registers.main(["validate", "--root", str(life)]) == 2


# --- LIFE -------------------------------------------------------------------------

def test_life_on_an_empty_tree_is_quiet_except_journal_and_profile(life, clock):
    clock("2026-10-24T09:00:00Z")
    lines = health.life()
    assert {c for c, _ in _codes(lines, "PASS")} >= {"L1", "L2", "L3", "L4", "L5", "L8"}
    assert {c for c, _ in _codes(lines, "WARN")} == {"L6", "L7"}


def test_l1_flags_missing_fields_bad_status_area_and_future_date(life):
    _page(life, "wiki/home/a.md", tags=None)
    _page(life, "workspaces/w/_workspace.md", type="workspace", status="open")
    _page(life, "wiki/home/b.md", area="garden")
    _page(life, "wiki/home/c.md", updated="2026-12-01")
    (life / "wiki/home/d.md").write_text("no front matter\n")
    msgs = [m for _, m in _codes(health.l1_front_matter("2026-10-24"), "WARN")]
    assert any("a.md: missing tags" in m for m in msgs)
    assert any("_workspace.md: status 'open'" in m for m in msgs)
    assert any("b.md: area 'garden'" in m for m in msgs)
    assert any("c.md: updated 2026-12-01 is in the future" in m for m in msgs)
    assert any("d.md: no front matter" in m for m in msgs)


def test_l2_resolves_names_paths_and_labels(life):
    _page(life, "wiki/people/sam.md", section="people")
    p = _page(life, "wiki/home/boiler.md")
    p.write_text(p.read_text() + "[[sam]] [[people/sam|Sam]] [[wiki/people/sam]] [[nobody]]\n")
    assert _codes(health.l2_wikilinks(), "WARN") == [
        ("L2", "unresolved [[nobody]] (first seen in life/wiki/home/boiler.md)")]


def test_l4_counts_overdue_and_lapsed_renewals(life, clock):
    clock("2026-10-01T09:00:00Z")
    registers.create("waiting", "Invoice", "finance", owed_by="Supplier", asked_on="2026-10-01")
    registers.create("renewal", "Insurance", "home", expires="2026-10-10",
                     provider="Insurer", amount="none")
    items = registers.load()
    msgs = [m for _, m in _codes(health.l4_review(items, "2026-10-20"), "WARN")]
    assert "1 open renewal item(s) past review_by" in msgs
    assert "1 open waiting item(s) past review_by" in msgs
    assert "renewal(s) past expires and still open: insurance" in msgs


def test_l5_flags_items_older_than_three_days(life):
    f = life / "inbox" / "gmail-digest.md"
    f.write_text("digest\n")
    (life / "inbox" / ".ledger").write_text("hidden\n")
    now = time.time()
    assert health.l5_inbox(now)[0][0] == "PASS"
    os.utime(f, (now - 5 * 86400, now - 5 * 86400))
    level, _, msg = health.l5_inbox(now)[0]
    assert level == "WARN" and msg.startswith("1 item(s)")


def test_l6_counts_days_without_events(life):
    (life / "journal" / "2026-10-24.jsonl").write_text('{"type": "log.note"}\n')
    (life / "journal" / "2026-10-23.jsonl").write_text("\n")
    assert health.l6_journal("2026-10-24") == [
        ("WARN", "L6", "13 of the last 14 days have no journal events")]


def test_l7_counts_provisional_rows_and_age(life):
    (paths.ME_ROOT / "profile.md").write_text(
        "---\ntitle: P\ntype: profile\nlast_validated: 2026-10-14\n---\n"
        "| 1 | a | b | provisional | x | y |\n| 2 | a | b | confirmed | x | y |\n")
    assert health.l7_profile("2026-10-24") == [
        ("WARN", "L7", "1 provisional claim(s); last validated 10 day(s) ago")]


def test_l8_records_then_detects_edits_and_accepts_amendments(life, tmp_path):
    storage = tmp_path / "storage"
    r = _page(life, "reports/weekly/2026-10-19/weekly.md", type="report", status="final",
              area="none")
    assert "newly recorded" in health.l8_final_reports(storage)[0][2]
    assert (storage / "reports" / "final.sha256").read_text().endswith(
        "  life/reports/weekly/2026-10-19/weekly.md\n")
    r.write_text(r.read_text() + "\n## Amendment 2026-10-25\n\nCorrected a figure.\n")
    assert health.l8_final_reports(storage)[0][0] == "PASS"
    r.write_text(r.read_text().replace("Body.", "Rewritten."))
    assert health.l8_final_reports(storage)[0][0] == "WARN"


# --- S6 -----------------------------------------------------------------------------

def test_areas_pass_on_matching_ids(life):
    assert health.areas()[0][0] == "PASS"


def test_areas_flag_drift_in_json_and_in_life(life):
    rows = json.loads((paths.ME_ROOT / "areas.json").read_text())[:-1]
    (paths.ME_ROOT / "areas.json").write_text(json.dumps(rows))
    _page(life, "wiki/home/x.md", area="garden")
    msgs = [m for _, m in _codes(health.areas(), "ISSUE")]
    assert any("differ from registers.AREAS" in m for m in msgs)
    assert any("area 'garden'" in m for m in msgs)
    assert health.main(["areas"]) == 1


def test_cli_root_and_usage(tmp_path, life, capsys):
    assert health.main(["life", "--root", str(tmp_path)]) == 0
    assert "L3" in capsys.readouterr().out
    assert health.main(["nope"]) == 2
