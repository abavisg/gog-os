from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def test_repo_root_and_storage_root():
    from gogos.paths import REPO_ROOT, STORAGE_ROOT

    assert (REPO_ROOT / "gogos").is_dir()
    assert STORAGE_ROOT == REPO_ROOT / ".core/storage"


def test_storage_path_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("GOGOS_TIMEZONE", "Europe/London")
    # Reload to pick up env change
    import importlib
    import gogos.paths as paths_mod
    importlib.reload(paths_mod)

    # Use a fixed date
    result = paths_mod.storage_path("gmail", "personal", "inbox", "2026-06-04")
    assert result == paths_mod.STORAGE_ROOT / "gmail" / "personal" / "inbox" / "2026-06-04"


def test_storage_path_creates_parents(tmp_path, monkeypatch):
    import importlib
    import gogos.paths as paths_mod
    importlib.reload(paths_mod)

    # Point STORAGE_ROOT at tmp_path for isolation
    monkeypatch.setattr(paths_mod, "STORAGE_ROOT", tmp_path)
    result = paths_mod.storage_path("gmail", "personal", "inbox", "2026-06-04")
    assert result.is_dir()


def test_storage_path_date_defaults_to_today(monkeypatch):
    import importlib
    import gogos.paths as paths_mod
    monkeypatch.setenv("GOGOS_TIMEZONE", "Europe/London")
    importlib.reload(paths_mod)

    tz = ZoneInfo("Europe/London")
    expected_date = datetime.now(tz=tz).strftime("%Y-%m-%d")
    result = paths_mod.storage_path("gmail", "personal", "inbox")
    assert result.name == expected_date


def test_storage_path_cwd_independence(tmp_path, monkeypatch):
    import importlib
    import gogos.paths as paths_mod
    importlib.reload(paths_mod)

    original_cwd = Path.cwd()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths_mod, "STORAGE_ROOT", tmp_path)
    try:
        result = paths_mod.storage_path("gmail", "personal", "inbox", "2026-06-04")
        assert result.is_dir()
        assert result.is_absolute()
    finally:
        monkeypatch.chdir(original_cwd)


def test_latest_alias():
    from gogos.paths import latest_alias
    from pathlib import Path

    dir_path = Path("/some/dir")
    result = latest_alias(dir_path, "latest-raw.json")
    assert result == Path("/some/dir/latest-raw.json")
    assert isinstance(result, Path)


# --- One today (spec 1 item 3) ------------------------------------------------

_SUMMER_2330_UTC = datetime(2026, 6, 29, 23, 30, tzinfo=ZoneInfo("UTC"))


def test_now_utc_is_timezone_aware_utc():
    from datetime import timedelta

    from gogos.paths import now_utc

    assert now_utc().utcoffset() == timedelta(0)


def test_today_honours_gogos_timezone(monkeypatch):
    import gogos.paths as paths_mod

    monkeypatch.setattr(paths_mod, "now_utc", lambda: _SUMMER_2330_UTC)
    monkeypatch.setenv("GOGOS_TIMEZONE", "Europe/London")
    assert paths_mod.today() == "2026-06-30"  # 00:30 BST
    monkeypatch.setenv("GOGOS_TIMEZONE", "UTC")
    assert paths_mod.today() == "2026-06-29"
    monkeypatch.setenv("GOGOS_TIMEZONE", "America/New_York")
    assert paths_mod.today() == "2026-06-29"


def test_storage_path_defaults_to_today(tmp_path, monkeypatch):
    import gogos.paths as paths_mod

    monkeypatch.setattr(paths_mod, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(paths_mod, "now_utc", lambda: _SUMMER_2330_UTC)
    monkeypatch.setenv("GOGOS_TIMEZONE", "Europe/London")
    assert paths_mod.storage_path("gmail", "personal", "inbox").name == "2026-06-30"


def test_approvals_dir_date_equals_storage_dir_date_at_2330_utc_in_summer(
        tmp_path, monkeypatch):
    """A run at 00:30 London (23:30 UTC) files approvals and storage under the
    same date; approvals used to take the UTC date (one day behind)."""
    import gogos.paths as paths_mod
    from gogos.gmail import gmail_apply

    monkeypatch.setattr(paths_mod, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(gmail_apply, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(paths_mod, "now_utc", lambda: _SUMMER_2330_UTC)
    monkeypatch.setenv("GOGOS_TIMEZONE", "Europe/London")

    approvals = gmail_apply._approvals_dir("me@x.com")
    storage = paths_mod.storage_path("gmail", "me@x.com", "inbox")
    assert approvals.name == storage.name == "2026-06-30"
