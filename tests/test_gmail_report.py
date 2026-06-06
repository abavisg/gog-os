"""Tests for gogos.gmail.gmail_report — no network, no Gmail API."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

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
    # Two distinct categories: Action (2 items) and Review (1 item)
    assert "## Action" in md
    assert "## Review" in md


def test_report_includes_sender(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    assert "alice@example.com" in md


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


def test_report_includes_confidence(tmp_path):
    m = _reload()
    slim = _slim_data()
    triage = _triage_data(slim)
    tp = tmp_path / "tp.json"
    sp = tmp_path / "sp.json"
    md = m.render_report(triage, slim, tp, sp, generated_at="2026-06-06T12:00:00+01:00")
    # Confidence rendered as percentage
    assert "%" in md


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

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    rc = m.report("personal", triage_path, slim_path)

    assert rc == 0
    assert (dated_dir / "email-report.md").exists()
    assert alias_path.exists()


def test_io_alias_and_dated_file_identical(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest.md"

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    _write_json(slim_path, _slim_data())

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    m.report("personal", triage_path, slim_path)

    assert (dated_dir / "email-report.md").read_text() == alias_path.read_text()


def test_io_uses_reports_storage_path(tmp_path, monkeypatch):
    """storage_path must be called with module='reports', kind='email'."""
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

    monkeypatch.setattr(m, "storage_path", capturing_storage_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.report("personal", triage_path, slim_path)

    assert len(calls) == 1
    assert calls[0] == ("reports", "email", "personal")


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


def test_no_html_file_produced(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest.md"

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _triage_data(_slim_data()))
    _write_json(slim_path, _slim_data())

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    m.report("personal", triage_path, slim_path)

    html_files = list(dated_dir.glob("*.html")) + list(tmp_path.glob("*.html"))
    assert not html_files, f"Unexpected HTML files: {html_files}"


def test_empty_triage_io_exits_zero(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest.md"

    triage_path = tmp_path / "latest-triage.json"
    slim_path = tmp_path / "latest-slim.json"
    _write_json(triage_path, _empty_triage())
    _write_json(slim_path, {"account": "personal", "count": 0, "messages": [], "source": "gmail"})

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

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
