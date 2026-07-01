"""Tests for gogos.gmail.gmail_report — no network, no Gmail API."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import patch

FIXTURES = Path(__file__).parent / "fixtures"
RAW_SAMPLE = FIXTURES / "gmail_raw_sample.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload():
    import gogos.gmail.gmail_report as m
    importlib.reload(m)
    return m


def _slim_data() -> dict:
    """Build a normalised slim dict from the raw fixture."""
    import gogos.gmail.gmail_normalise as n
    importlib.reload(n)
    raw = json.loads(RAW_SAMPLE.read_text())
    return n.normalise_raw(raw)


def _triage_data(slim: dict | None = None) -> dict:
    if slim is None:
        slim = _slim_data()
    ids = [m["id"] for m in slim["messages"]]
    items = []
    categories = ["Action", "Review", "Action"]
    actions = [
        "Reply to confirm attendance",
        "Check when convenient",
        "Review and respond before Monday",
    ]
    for i, mid in enumerate(ids):
        items.append({
            "id": mid,
            "category": categories[i % len(categories)],
            "confidence": round(0.7 + i * 0.1, 2),
            "rationale": f"Test rationale {i}",
            "suggested_action": actions[i % len(actions)],
        })
    return {
        "generated_at": "2026-06-06T10:00:00+00:00",
        "account": "personal",
        "items": items,
    }


def _empty_triage() -> dict:
    return {
        "generated_at": "2026-06-06T10:00:00+00:00",
        "account": "personal",
        "items": [],
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# render_report — pure function
# ---------------------------------------------------------------------------

def test_report_contains_triage_source_citation(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "latest-triage.json"
    sp = tmp_path / "latest-slim.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert str(tp) in md, "Triage path must appear in report"


def test_report_contains_slim_source_citation(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "latest-triage.json"
    sp = tmp_path / "latest-slim.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert str(sp) in md, "Slim path must appear in report"


def test_report_contains_generation_timestamp(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    ts = "2026-06-06T12:00:00+01:00"
    md = m.render_report(triage, slim, tp, sp, generated_at=ts)
    assert ts in md, "Generation timestamp must appear in report"


def test_report_groups_by_category(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "Action" in md
    assert "Review" in md


def test_report_includes_sender(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    # Compact style extracts display name ("Alice Smith") not raw email address
    assert "Alice Smith" in md or "alice" in md.lower()


def test_report_includes_subject(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "Meeting tomorrow" in md


def test_report_includes_suggested_action(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "Reply to confirm attendance" in md


def test_report_does_not_show_raw_confidence_scores(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    # Confidence scores are internal; the readable styles don't expose them
    assert "0.7" not in md and "0.8" not in md


def test_empty_input_renders_nothing_to_triage(tmp_path):
    m = _reload()
    slim = {"account": "personal", "count": 0, "messages": [], "source": "gmail"}
    triage = _empty_triage()
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "No messages to triage" in md or "nothing to triage" in md.lower()


def test_empty_input_still_cites_sources(tmp_path):
    m = _reload()
    slim = {"account": "personal", "count": 0, "messages": [], "source": "gmail"}
    triage = _empty_triage()
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert str(tp) in md
    assert str(sp) in md


def test_no_html_in_output(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "<html" not in md.lower()
    assert "</html>" not in md.lower()
    assert "<body" not in md.lower()


def test_missing_sender_renders_placeholder(tmp_path):
    m = _reload()
    slim = {"account": "personal", "count": 1, "messages": [
        {"id": "abc", "from": "", "subject": "Test", "thread_id": "abc",
         "account": "personal", "to": "", "date": "", "snippet": "",
         "labels": [], "source": "gmail"}
    ], "source": "gmail"}
    triage = {
        "generated_at": "2026-06-06T10:00:00+00:00",
        "account": "personal",
        "items": [{"id": "abc", "category": "Review", "confidence": 0.5,
                   "rationale": "r", "suggested_action": "Check it"}],
    }
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "unknown sender" in md


def test_missing_subject_renders_placeholder(tmp_path):
    m = _reload()
    slim = {"account": "personal", "count": 1, "messages": [
        {"id": "abc", "from": "x@y.com", "subject": "", "thread_id": "abc",
         "account": "personal", "to": "", "date": "", "snippet": "",
         "labels": [], "source": "gmail"}
    ], "source": "gmail"}
    triage = {
        "generated_at": "2026-06-06T10:00:00+00:00",
        "account": "personal",
        "items": [{"id": "abc", "category": "Review", "confidence": 0.5,
                   "rationale": "r", "suggested_action": "Check it"}],
    }
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "no subject" in md


# ---------------------------------------------------------------------------
# report() I/O — writes dated file + alias
# ---------------------------------------------------------------------------

def test_io_writes_dated_file_and_alias(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest.md"

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    _write_json(slim_path, _slim_data())

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    with patch("subprocess.Popen"):
        rc = m.report("personal", triage_path, slim_path)

    assert rc == 0
    assert (dated_dir / "email-report.md").exists()
    assert alias_path.exists()


def test_io_alias_and_dated_file_identical(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()

    aliases: dict[str, Path] = {}

    def tracking_alias(d: Path, f: str) -> Path:
        p = tmp_path / f
        aliases[f] = p
        return p

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    _write_json(slim_path, _slim_data())

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", tracking_alias)

    with patch("subprocess.Popen"):
        m.report("personal", triage_path, slim_path)

    assert (dated_dir / "email-report.md").read_text() == aliases["latest.md"].read_text()


def test_io_uses_reports_storage_path(tmp_path, monkeypatch):
    """storage_path is called for the report (reports/email) and for the
    optional reconcile artefact lookup (gmail/<account>/reconcile)."""
    m = _reload()
    calls = []
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()

    def capturing_storage_path(module, account, kind, **kw):
        calls.append((module, account, kind))
        return dated_dir

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    _write_json(slim_path, _slim_data())

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", capturing_storage_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    with patch("subprocess.Popen"):
        m.report("personal", triage_path, slim_path)

    assert ("reports", "email", "personal") in calls
    assert ("gmail", "personal", "reconcile") in calls


def test_missing_triage_file_returns_nonzero(tmp_path, monkeypatch):
    m = _reload()
    slim_path = tmp_path / "latest-slim.json"
    _write_json(slim_path, _slim_data())
    missing = tmp_path / "no_such_triage.json"

    rc = m.report("personal", missing, slim_path)
    assert rc != 0


def test_missing_slim_file_returns_nonzero(tmp_path, monkeypatch):
    m = _reload()
    triage_path = tmp_path / "latest-triage.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    missing = tmp_path / "no_such_slim.json"

    rc = m.report("personal", triage_path, missing)
    assert rc != 0


def test_missing_triage_file_prints_clear_error(tmp_path, capsys):
    m = _reload()
    slim_path = tmp_path / "latest-slim.json"
    _write_json(slim_path, _slim_data())
    missing = tmp_path / "no_such_triage.json"

    m.report("personal", missing, slim_path)
    err = capsys.readouterr().err
    assert "triage" in err.lower() or "ERROR" in err


def test_html_file_produced(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    _write_json(slim_path, _slim_data())

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: dated_dir / f)

    with patch("subprocess.Popen"):
        m.report("personal", triage_path, slim_path)

    html_files = list(dated_dir.glob("*.html"))
    assert html_files, "Expected HTML file to be produced"
    assert "<!DOCTYPE html>" in html_files[0].read_text()


def test_empty_triage_io_exits_zero(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest.md"

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _empty_triage())
    _write_json(slim_path, {"account": "personal", "count": 0, "messages": [], "source": "gmail"})

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    with patch("subprocess.Popen"):
        rc = m.report("personal", triage_path, slim_path)
    assert rc == 0
    assert alias_path.exists()


def test_no_gmail_api_import(tmp_path):
    """gmail_report must not import googleapiclient or any write-path Gmail module."""
    import gogos.gmail.gmail_report as m
    import sys
    # If any google API client was imported by this module, it would be in sys.modules
    # We just verify the module itself doesn't carry a service or API object
    assert not hasattr(m, "build"), "gmail_report must not import googleapiclient.discovery.build"
    assert not hasattr(m, "_build_service"), "gmail_report must not define _build_service"


# ---------------------------------------------------------------------------
# Style: compact
# ---------------------------------------------------------------------------

def _render(style: str, detail_categories: list[str] | None = None) -> str:
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    config = {"style": style, "detail_categories": detail_categories or ["Action", "Events"]}
    from pathlib import Path
    return m.render_report(
        triage, slim,
        Path("/fake/triage.json"), Path("/fake/slim.json"),
        generated_at="2026-06-18T09:00:00+01:00",
        config=config,
    )


def test_compact_has_category_headers():
    md = _render("compact")
    assert "### " in md
    assert "Action" in md


def test_compact_collapses_newsletters_to_name_run():
    md = _render("compact")
    # Newsletters section should appear but not have individual → action lines
    lines = md.splitlines()
    newsletter_idx = next((i for i, l in enumerate(lines) if "Newsletters" in l), None)
    if newsletter_idx is not None:
        # The line after the header should be a name run (no "→" per item on its own line)
        section_lines = lines[newsletter_idx + 1: newsletter_idx + 4]
        assert not any(l.strip().startswith("→") for l in section_lines)


def test_compact_shows_arrow_action_for_action_category():
    md = _render("compact")
    assert "→" in md


def test_compact_includes_sender_and_subject():
    md = _render("compact")
    assert "Alice Smith" in md  # display name extracted from "Alice Smith <alice@example.com>"
    assert "Meeting tomorrow" in md


# ---------------------------------------------------------------------------
# Style: card
# ---------------------------------------------------------------------------

def test_card_has_bold_sender():
    md = _render("card")
    assert "**" in md


def test_card_shows_arrow_action():
    md = _render("card")
    assert "→" in md


def test_card_includes_subject():
    md = _render("card")
    assert "Meeting tomorrow" in md


def test_card_groups_by_category():
    md = _render("card")
    assert "Action" in md
    assert "Review" in md


# ---------------------------------------------------------------------------
# Style: summary
# ---------------------------------------------------------------------------

def test_summary_has_count_table():
    md = _render("summary", detail_categories=["Action"])
    assert "| Action" in md or "Action |" in md


def test_summary_expands_detail_categories():
    md = _render("summary", detail_categories=["Action"])
    assert "→" in md  # expanded Action items have → lines


def test_summary_collapses_non_detail_categories():
    md = _render("summary", detail_categories=["Action"])
    # Review is not in detail_categories — it must appear only in the collapsed footer line,
    # not as an expanded bullet point with subject + arrow.
    lines = md.splitlines()
    # Find lines that are expanded bullet points (start with "•")
    bullet_lines = [l for l in lines if l.strip().startswith("•")]
    # None of the bullet lines should belong to the Review category
    # (we can tell because Action items have subjects like "Meeting tomorrow" / "(no subject)")
    # The Review item has subject "Invoice #1234" — it must not appear as a bullet
    assert not any("Invoice #1234" in l for l in bullet_lines)


def test_summary_lists_collapsed_categories_at_footer():
    md = _render("summary", detail_categories=["Action"])
    assert "Review" in md  # still mentioned in collapsed footer


# ---------------------------------------------------------------------------
# Config: unknown style falls back to compact
# ---------------------------------------------------------------------------

def test_unknown_style_falls_back_to_compact():
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    from pathlib import Path
    md = m.render_report(
        triage, slim,
        Path("/fake/triage.json"), Path("/fake/slim.json"),
        generated_at="2026-06-18T09:00:00+01:00",
        config={"style": "nonexistent", "detail_categories": ["Action"]},
    )
    # Falls back to compact: category headers use ###
    assert "### " in md


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def test_load_report_config_returns_defaults_when_missing(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "_REPORT_CONFIG_PATH", tmp_path / "no_such_file.json")
    cfg = m._load_report_config()
    assert cfg["style"] == "compact"
    assert "Action" in cfg["detail_categories"]


def test_load_report_config_reads_file(tmp_path, monkeypatch):
    m = _reload()
    cfg_file = tmp_path / "report.json"
    cfg_file.write_text(json.dumps({"style": "card", "detail_categories": ["Events"]}))
    monkeypatch.setattr(m, "_REPORT_CONFIG_PATH", cfg_file)
    cfg = m._load_report_config()
    assert cfg["style"] == "card"
    assert cfg["detail_categories"] == ["Events"]


# ---------------------------------------------------------------------------
# Reconciliation extras (Phase 4.6 §8): learned rules + unsubscribe candidates
# ---------------------------------------------------------------------------

RECONCILE = {
    "learned": [{"sender": "promo.example.com", "category": "Review", "corrections": 3}],
    "rescue_suggestions": [{"sender": "keep.example.com", "rescues": 4}],
    "unsubscribe_candidates": [{
        "sender": "tldrnewsletter.com", "category": "Newsletters",
        "message_count": 2,
        "unsubscribe": "<https://tldr.example/unsub>, <mailto:unsub@tldr.example>",
    }],
}


def _paths(tmp_path):
    return tmp_path / "triage.json", tmp_path / "slim.json"


def test_report_shows_learned_rule_lines(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    md = m.render_report(_triage_data(), _slim_data(), tp, sp,
                         generated_at="2026-07-01T12:00:00+01:00",
                         reconcile_data=RECONCILE)
    assert "learned: **promo.example.com** → Review (3 corrections)" in md
    assert "keep.example.com** rescued to inbox 4×" in md


def test_report_shows_unsubscribe_link_preferring_https(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    md = m.render_report(_triage_data(), _slim_data(), tp, sp,
                         generated_at="2026-07-01T12:00:00+01:00",
                         reconcile_data=RECONCILE)
    assert "[unsubscribe](https://tldr.example/unsub)" in md
    assert "mailto:" not in md  # https preferred when both are offered


def test_report_without_reconcile_data_is_unchanged(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    md = m.render_report(_triage_data(), _slim_data(), tp, sp,
                         generated_at="2026-07-01T12:00:00+01:00")
    assert "Learned rules" not in md
    assert "Unsubscribe candidates" not in md


def test_html_report_shows_reconcile_section_with_link(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    html = m.render_html_report(_triage_data(), _slim_data(), tp, sp,
                                generated_at="2026-07-01T12:00:00+01:00",
                                reconcile_data=RECONCILE)
    assert "Reconciliation" in html
    assert '<a href="https://tldr.example/unsub">unsubscribe</a>' in html
    assert "GogOS sends nothing" in html


def test_unsubscribe_href_falls_back_to_mailto():
    m = _reload()
    assert m._unsubscribe_href("<mailto:unsub@x.com>") == "mailto:unsub@x.com"
    assert m._unsubscribe_href("") == ""
    assert m._unsubscribe_href("junk-no-brackets") == ""


# ---------------------------------------------------------------------------
# Digest header (Phase 4.6 §4): 3-line executive summary
# ---------------------------------------------------------------------------

def _item(mid: str, category: str, rationale: str) -> dict:
    return {"id": mid, "category": category, "confidence": 0.7,
            "rationale": rationale, "suggested_action": "x"}


def _digest_triage() -> dict:
    """3 Action (2 protected), 1 Review, 2 Events (1 invite), 1 Information,
    2 Newsletters, 3 Safe to Delete."""
    items = [
        _item("a1", "Action", "Financial: statement/bill/payment/renewal — review or pay."),
        _item("a2", "Action", "Security / account-safety alert — verify."),
        _item("a3", "Action", "User rule #1: linkedin.com → Action"),
        _item("r1", "Review", "Message from a real person — read; reply if needed."),
        _item("e1", "Events", "Calendar invitation / booking / appointment."),
        _item("e2", "Events", "Ticket reminder."),
        _item("i1", "Information", "Order / shipping / travel notice — record."),
        _item("n1", "Newsletters", "Subscribed newsletter / digest."),
        _item("n2", "Newsletters", "Long-tail automated mail — skim."),
        _item("s1", "Safe to Delete", "Social / notification noise."),
        _item("s2", "Safe to Delete", "Promotional / marketing."),
        _item("s3", "Safe to Delete", "Promotional / marketing."),
    ]
    return {"generated_at": "2026-07-01T10:00:00+00:00",
            "account": "personal", "items": items}


def test_digest_first_line_counts_attention_with_callouts():
    m = _reload()
    lines = m.build_digest(_digest_triage())
    assert lines[0] == "⚡ 3 Action (2 financial/security) · 📋 1 Review · 📅 2 Events (1 invite)"


def test_digest_second_line_counts_the_queue():
    m = _reload()
    lines = m.build_digest(_digest_triage())
    assert lines[1] == "ℹ️ 1 Information · 📰 2 Newsletters · 🗑 3 Safe to Delete queued"


def test_digest_third_line_only_with_reconcile_signals():
    m = _reload()
    assert len(m.build_digest(_digest_triage())) == 2
    lines = m.build_digest(_digest_triage(), reconcile_data=RECONCILE)
    assert lines[2] == "🎓 1 learned rule · 💡 1 rule suggestion · 🔕 1 unsubscribe candidate"


def test_digest_empty_reconcile_adds_no_third_line():
    m = _reload()
    empty = {"learned": [], "rescue_suggestions": [], "unsubscribe_candidates": []}
    assert len(m.build_digest(_digest_triage(), reconcile_data=empty)) == 2


def test_digest_empty_items_returns_no_lines():
    m = _reload()
    assert m.build_digest(_empty_triage()) == []


def test_digest_nothing_needs_action_fallback():
    m = _reload()
    triage = {"generated_at": "x", "account": "personal",
              "items": [_item("n1", "Newsletters", "Subscribed newsletter / digest.")]}
    lines = m.build_digest(triage)
    assert lines[0] == "✅ Nothing needs action"


def test_digest_unknown_category_lands_in_queue_line():
    m = _reload()
    triage = {"generated_at": "x", "account": "personal",
              "items": [_item("u1", "Mystery", "?")]}
    lines = m.build_digest(triage)
    assert "1 Mystery" in lines[1]


def test_report_renders_digest_as_blockquote_before_sections(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    md = m.render_report(_triage_data(), _slim_data(), tp, sp,
                         generated_at="2026-07-01T12:00:00+01:00")
    # Fixture triage: 2 Action, 1 Review — no call-outs (test rationales)
    assert "> ⚡ 2 Action · 📋 1 Review" in md
    assert md.index("> ⚡") < md.index("### ")


def test_report_empty_triage_has_no_digest(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    slim = {"account": "personal", "count": 0, "messages": [], "source": "gmail"}
    md = m.render_report(_empty_triage(), slim, tp, sp,
                         generated_at="2026-07-01T12:00:00+01:00")
    assert ">" not in md


def test_html_report_contains_digest_box(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    html = m.render_html_report(_triage_data(), _slim_data(), tp, sp,
                                generated_at="2026-07-01T12:00:00+01:00")
    assert '<div class="digest">' in html
    assert "⚡ 2 Action · 📋 1 Review" in html


def test_html_digest_appears_before_first_category_section(tmp_path):
    m = _reload()
    tp, sp = _paths(tmp_path)
    html = m.render_html_report(_triage_data(), _slim_data(), tp, sp,
                                generated_at="2026-07-01T12:00:00+01:00")
    assert html.index('<div class="digest">') < html.index('<section class="category">')
