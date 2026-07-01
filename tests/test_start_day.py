"""Tests for gogos.system.start_day — no network, no Gmail API.

The key tests prove the Phase 4.6 §5/§6 acceptance criteria: the merged panel
account-tags every item; /start-day runs read-only across accounts and never
moves (it cannot even reach gmail_apply); one failing account doesn't kill the
morning run; the SessionStart nudge only offers, never acts.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path


def _reload():
    import gogos.system.start_day as m
    importlib.reload(m)
    return m


def _result(alias: str, email: str, items: list[dict], msgs: list[dict],
            reconcile: dict | None = None) -> dict:
    return {
        "account": email,
        "alias": alias,
        "triage": {"account": email, "items": items},
        "slim": {"messages": msgs},
        "reconcile": reconcile or {},
        "triage_path": Path(f"/tmp/{alias}-triage.json"),
        "slim_path": Path(f"/tmp/{alias}-slim.json"),
    }


def _two_accounts():
    personal = _result(
        "personal", "me@gmail.com",
        [{"id": "p1", "category": "Action", "suggested_action": "Pay"},
         {"id": "p2", "category": "Newsletters"}],
        [{"id": "p1", "from": "HSBC <no-reply@hsbc.com>", "subject": "Statement ready"},
         {"id": "p2", "from": "TLDR <dan@tldrnewsletter.com>", "subject": "Daily digest"}],
        reconcile={"learned": [{"sender": "a.com", "category": "Review", "corrections": 3}]},
    )
    work = _result(
        "work", "me@work.com",
        [{"id": "w1", "category": "Review", "suggested_action": "Reply"},
         {"id": "w2", "category": "Safe to Delete"}],
        [{"id": "w1", "from": "Jane Doe <jane@client.com>", "subject": "Re: contract"},
         {"id": "w2", "from": "Promo <news@promo.example.com>", "subject": "Sale!"}],
    )
    return [personal, work]


# --- merge (§5) --------------------------------------------------------------

def test_merge_combines_items_and_reconcile_lists():
    m = _reload()
    triage, reconcile = m.merge_results(_two_accounts())
    assert len(triage["items"]) == 4
    assert len(reconcile["learned"]) == 1
    assert reconcile["rescue_suggestions"] == []


def test_panel_account_tags_every_item():
    """§5 acceptance: one merged panel, each item account-tagged."""
    m = _reload()
    panel = m.render_panel(_two_accounts(), generated_at="2026-07-01T08:00:00+01:00")
    # Attention items carry their account tag
    assert "**[personal]** ⚡ HSBC — Statement ready → Pay" in panel
    assert "**[work]** 📋 Jane Doe — Re: contract → Reply" in panel
    # Queue counts are tagged per account too
    assert "**[personal]** 📰 1 Newsletters" in panel
    assert "**[work]** 🗑 1 Safe to Delete" in panel


def test_panel_digest_counts_are_merged_across_accounts():
    m = _reload()
    panel = m.render_panel(_two_accounts(), generated_at="2026-07-01T08:00:00+01:00")
    assert "⚡ 1 Action" in panel
    assert "📋 1 Review" in panel
    assert "🎓 1 learned rule" in panel


def test_panel_cites_sources_per_account_and_states_read_only():
    m = _reload()
    panel = m.render_panel(_two_accounts(), generated_at="2026-07-01T08:00:00+01:00")
    assert "Sources [personal]: `/tmp/personal-triage.json`" in panel
    assert "Sources [work]:" in panel
    assert "Read-only — nothing was moved" in panel


def test_panel_flags_a_skipped_account_loudly():
    m = _reload()
    m.alias_for = lambda e: e.split("@")[0]
    panel = m.render_panel(_two_accounts()[:1], errors={"me@work.com": "fetch failed"},
                           generated_at="2026-07-01T08:00:00+01:00")
    assert "⚠️ **[me]** skipped: fetch failed" in panel


# --- read-only (§6) ----------------------------------------------------------

def test_module_never_references_gmail_apply():
    """§6 acceptance: /start-day never moves. The module cannot even reach the
    write-back layer — it has no reference to gmail_apply at all."""
    m = _reload()
    source = Path(m.__file__).read_text()
    assert "gmail_apply" not in source


def test_run_writes_dated_panel_and_latest_alias(tmp_path, monkeypatch, capsys):
    import gogos.paths as paths
    m = _reload()
    monkeypatch.setattr(paths, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(m, "run_account", lambda a, w: _two_accounts()[0])
    monkeypatch.setattr(m, "known_accounts", lambda: ["me@gmail.com"])

    assert m.run() == 0

    dated = list((tmp_path / "storage" / "reports" / "start-day" / "all").iterdir())
    assert len(dated) == 1
    assert (dated[0] / "start-day.md").exists()
    assert (dated[0] / "latest.md").exists()
    assert "Start Day" in capsys.readouterr().out


def test_run_continues_past_a_failing_account(tmp_path, monkeypatch, capsys):
    """One expired token must not kill the whole morning run."""
    import gogos.paths as paths
    m = _reload()
    monkeypatch.setattr(paths, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "alias_for", lambda e: e.split("@")[0])

    def _fake(account, window):
        if account == "me@work.com":
            raise RuntimeError("fetch failed")
        return _two_accounts()[0]

    monkeypatch.setattr(m, "run_account", _fake)
    assert m.run(["me@gmail.com", "me@work.com"]) == 0

    out = capsys.readouterr()
    assert "skipped: fetch failed" in out.out       # loud in the panel
    assert "[me@work.com] fetch failed" in out.err  # loud on stderr


def test_run_fails_when_every_account_fails(tmp_path, monkeypatch, capsys):
    import gogos.paths as paths
    m = _reload()
    monkeypatch.setattr(paths, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(m, "resolve_account", lambda a: a)

    def _boom(account, window):
        raise RuntimeError("fetch failed")

    monkeypatch.setattr(m, "run_account", _boom)
    assert m.run(["me@gmail.com"]) == 1
    assert "every account failed" in capsys.readouterr().err


def test_run_with_no_accounts_is_an_error(monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "known_accounts", lambda: [])
    assert m.run() == 1
    assert "no accounts registered" in capsys.readouterr().err


# --- SessionStart nudge ------------------------------------------------------

def _nudge_env(m, tmp_path, monkeypatch, accounts=("me@gmail.com",)):
    monkeypatch.setattr(m, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(m, "known_accounts", lambda: list(accounts))
    monkeypatch.setattr(m, "_today", lambda: "2026-07-01")


def test_nudge_plain_offer_when_nothing_ran_today(tmp_path, monkeypatch, capsys):
    m = _reload()
    _nudge_env(m, tmp_path, monkeypatch)
    assert m.nudge() == 0
    assert "Run /start-day" in capsys.readouterr().out


def test_nudge_shows_counts_from_todays_triage(tmp_path, monkeypatch, capsys):
    m = _reload()
    _nudge_env(m, tmp_path, monkeypatch)
    triage_dir = tmp_path / "storage" / "gmail" / "me@gmail.com" / "triage" / "2026-07-01"
    triage_dir.mkdir(parents=True)
    (triage_dir / "latest-triage.json").write_text(json.dumps({"items": [
        {"id": "1", "category": "Action"},
        {"id": "2", "category": "Newsletters"},
        {"id": "3", "category": "Action"},
    ]}))
    assert m.nudge() == 0
    assert "3 triaged this morning, 2 need action" in capsys.readouterr().out


def test_nudge_is_quiet_once_todays_panel_exists(tmp_path, monkeypatch, capsys):
    m = _reload()
    _nudge_env(m, tmp_path, monkeypatch)
    panel_dir = tmp_path / "storage" / "reports" / "start-day" / "all" / "2026-07-01"
    panel_dir.mkdir(parents=True)
    (panel_dir / "start-day.md").write_text("# Start Day")
    assert m.nudge() == 0
    assert capsys.readouterr().out == ""


def test_nudge_never_creates_directories(tmp_path, monkeypatch):
    """The hook must be side-effect free: reads only, no storage scaffolding."""
    m = _reload()
    _nudge_env(m, tmp_path, monkeypatch)
    m.nudge()
    assert not (tmp_path / "storage").exists()
