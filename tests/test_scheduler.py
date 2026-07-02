"""Tests for gogos.system.scheduler — no launchctl, no osascript, no Gmail.

The key tests prove the Phase 4.6 §7 acceptance criteria: the scheduler is
installable (plist correct, loaded via launchctl) and the scheduled run is
provably read-only — it cannot reach the apply engine, never opens a browser,
and never writes the /start-day panel (so the SessionStart nudge stays alive).
"""
from __future__ import annotations

import importlib
import plistlib
from pathlib import Path


def _reload():
    import gogos.system.scheduler as m
    importlib.reload(m)
    return m


def _result(alias: str, email: str, items: list[dict]) -> dict:
    return {
        "account": email,
        "alias": alias,
        "triage": {"account": email, "items": items},
        "slim": {"messages": []},
        "reconcile": {},
        "triage_path": Path(f"/tmp/{alias}-triage.json"),
        "slim_path": Path(f"/tmp/{alias}-slim.json"),
    }


# --- plist -------------------------------------------------------------------

def test_plist_runs_venv_python_from_repo_root_at_0800_by_default():
    m = _reload()
    data = plistlib.loads(m.plist_xml().encode())
    assert data["Label"] == "com.gogos.start-day"
    assert data["ProgramArguments"][0].endswith(".venv/bin/python")
    assert data["ProgramArguments"][1:] == ["-m", "gogos.system.scheduler", "run"]
    assert data["WorkingDirectory"] == str(m.REPO_ROOT)
    assert data["StartCalendarInterval"] == {"Hour": 8, "Minute": 0}
    assert data["RunAtLoad"] is False


def test_plist_honours_custom_time():
    m = _reload()
    data = plistlib.loads(m.plist_xml(6, 30).encode())
    assert data["StartCalendarInterval"] == {"Hour": 6, "Minute": 30}


def test_plist_logs_under_storage():
    m = _reload()
    data = plistlib.loads(m.plist_xml().encode())
    assert "/.core/storage/logs/scheduler/" in data["StandardOutPath"]
    assert "/.core/storage/logs/scheduler/" in data["StandardErrorPath"]


# --- install / uninstall / status ---------------------------------------------

def _fake_launchctl(calls, returncode=0):
    class _Done:
        def __init__(self):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def _run(*args, **kwargs):
        calls.append(args[0])
        return _Done()
    return _run


def test_install_writes_plist_and_loads_it(tmp_path, monkeypatch, capsys):
    m = _reload()
    plist = tmp_path / "LaunchAgents" / f"{m.LABEL}.plist"
    monkeypatch.setattr(m, "plist_path", lambda: plist)
    monkeypatch.setattr(m, "_VENV_PYTHON", tmp_path / "python")
    monkeypatch.setattr(m, "_LOG_DIR", tmp_path / "logs")
    (tmp_path / "python").write_text("")  # venv exists
    calls: list = []
    monkeypatch.setattr(m.subprocess, "run", _fake_launchctl(calls))

    assert m.install(7, 45) == 0
    assert plist.exists()
    assert plistlib.loads(plist.read_bytes())["StartCalendarInterval"] == {
        "Hour": 7, "Minute": 45}
    assert (tmp_path / "logs").is_dir()
    assert ["launchctl", "load", "-w", str(plist)] in calls
    assert "07:45" in capsys.readouterr().out


def test_install_fails_clearly_without_venv(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_VENV_PYTHON", tmp_path / "missing-python")
    assert m.install() == 1
    assert "venv python not found" in capsys.readouterr().err


def test_install_fails_when_launchctl_load_fails(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "plist_path", lambda: tmp_path / "a.plist")
    monkeypatch.setattr(m, "_VENV_PYTHON", tmp_path / "python")
    monkeypatch.setattr(m, "_LOG_DIR", tmp_path / "logs")
    (tmp_path / "python").write_text("")
    monkeypatch.setattr(m.subprocess, "run", _fake_launchctl([], returncode=1))
    assert m.install() == 1
    assert "launchctl load failed" in capsys.readouterr().err


def test_uninstall_unloads_and_removes(tmp_path, monkeypatch, capsys):
    m = _reload()
    plist = tmp_path / f"{m.LABEL}.plist"
    plist.write_text("x")
    monkeypatch.setattr(m, "plist_path", lambda: plist)
    calls: list = []
    monkeypatch.setattr(m.subprocess, "run", _fake_launchctl(calls))

    assert m.uninstall() == 0
    assert not plist.exists()
    assert ["launchctl", "unload", "-w", str(plist)] in calls


def test_uninstall_is_graceful_when_not_installed(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "plist_path", lambda: tmp_path / "missing.plist")
    calls: list = []
    monkeypatch.setattr(m.subprocess, "run", _fake_launchctl(calls))
    assert m.uninstall() == 0
    assert calls == []  # no launchctl churn
    assert "Nothing to uninstall" in capsys.readouterr().out


def test_status_reports_installed_time(tmp_path, monkeypatch, capsys):
    m = _reload()
    plist = tmp_path / f"{m.LABEL}.plist"
    plist.write_bytes(plistlib.dumps(m.plist_dict(9, 15)))
    monkeypatch.setattr(m, "plist_path", lambda: plist)
    monkeypatch.setattr(m.subprocess, "run", _fake_launchctl([]))
    assert m.status() == 0
    assert "09:15" in capsys.readouterr().out


def test_status_reports_not_installed(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "plist_path", lambda: tmp_path / "missing.plist")
    assert m.status() == 0
    assert "NOT INSTALLED" in capsys.readouterr().out


# --- the scheduled run: read-only, notify, stop --------------------------------

def test_module_never_references_write_back():
    """§7 acceptance: the scheduled run is provably read-only. The module has
    no reference to the apply/undo/loop write-back layer at all."""
    m = _reload()
    source = Path(m.__file__).read_text()
    assert "gmail_apply" not in source
    assert "gmail_undo" not in source
    assert "gmail_loop" not in source


def test_run_scheduled_notifies_merged_counts_and_never_opens_browser(monkeypatch):
    m = _reload()
    reports: list[dict] = []
    notifications: list[str] = []
    monkeypatch.setattr(m, "known_accounts", lambda: ["me@gmail.com", "me@work.com"])
    monkeypatch.setattr(m.start_day, "run_account", lambda a, w: _result(
        a.split("@")[0], a,
        [{"id": "1", "category": "Action"}, {"id": "2", "category": "Newsletters"}]))
    monkeypatch.setattr(m.gmail_report, "report",
                        lambda *a, **kw: reports.append(kw) or 0)
    monkeypatch.setattr(m, "_notify", notifications.append)

    assert m.run_scheduled() == 0
    assert len(reports) == 2
    assert all(kw.get("auto_open") is False for kw in reports)
    assert notifications == ["4 emails triaged, 2 need action. Run /start-day."]


def test_run_scheduled_never_writes_the_start_day_panel(tmp_path, monkeypatch):
    """The nudge goes quiet once today's panel exists — so the scheduled run
    must leave the panel to /start-day itself."""
    import gogos.paths as paths
    m = _reload()
    monkeypatch.setattr(paths, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(m, "known_accounts", lambda: ["me@gmail.com"])
    monkeypatch.setattr(m.start_day, "run_account",
                        lambda a, w: _result("personal", a, []))
    monkeypatch.setattr(m.gmail_report, "report", lambda *a, **kw: 0)
    monkeypatch.setattr(m, "_notify", lambda msg: None)

    assert m.run_scheduled() == 0
    assert not (tmp_path / "storage" / "reports" / "start-day").exists()


def test_run_scheduled_continues_past_a_failing_account(monkeypatch, capsys):
    m = _reload()
    notifications: list[str] = []
    monkeypatch.setattr(m, "known_accounts", lambda: ["me@gmail.com", "me@work.com"])

    def _fake(account, window):
        if account == "me@work.com":
            raise RuntimeError("fetch failed")
        return _result("personal", account, [{"id": "1", "category": "Action"}])

    monkeypatch.setattr(m.start_day, "run_account", _fake)
    monkeypatch.setattr(m.gmail_report, "report", lambda *a, **kw: 0)
    monkeypatch.setattr(m, "_notify", notifications.append)

    assert m.run_scheduled() == 0
    assert "[me@work.com] fetch failed" in capsys.readouterr().err
    assert "1 account(s) failed" in notifications[0]


def test_run_scheduled_fails_and_notifies_when_every_account_fails(monkeypatch):
    m = _reload()
    notifications: list[str] = []
    monkeypatch.setattr(m, "known_accounts", lambda: ["me@gmail.com"])

    def _boom(account, window):
        raise RuntimeError("token expired")

    monkeypatch.setattr(m.start_day, "run_account", _boom)
    monkeypatch.setattr(m, "_notify", notifications.append)

    assert m.run_scheduled() == 1
    assert "failed for every account" in notifications[0]


def test_run_scheduled_fails_without_accounts(monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "known_accounts", lambda: [])
    assert m.run_scheduled() == 1
    assert "no accounts registered" in capsys.readouterr().err


def test_notification_failure_never_fails_the_run(monkeypatch, capsys):
    m = _reload()

    def _broken_osascript(*args, **kwargs):
        raise OSError("osascript missing")

    monkeypatch.setattr(m.subprocess, "run", _broken_osascript)
    m._notify("hello")  # must not raise
    assert "notification failed" in capsys.readouterr().err


def test_notify_escapes_quotes(monkeypatch):
    m = _reload()
    calls: list[list[str]] = []
    monkeypatch.setattr(m.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd))
    m._notify('say "hi" \\ there')
    script = calls[0][2]
    assert '\\"hi\\"' in script
    assert "\\\\" in script
