"""Tests for gogos.gmail.gmail_undo — no network, no live Gmail API.

The most important tests prove undo is the exact inverse of apply and preserves
the never-delete invariant: undo only ever removes GSD/* labels and adds INBOX.
"""
from __future__ import annotations

import importlib

import pytest

# Reuse the fake Gmail service from the apply tests.
from tests.test_gmail_apply import FakeService, _all_gsd_labels, _Exec


def _reload():
    """Reload the module and stub resolve_account (env has no 'personal' alias).

    The stub is applied AFTER reload so importlib.reload can't rebind it back to
    the real resolver.
    """
    import gogos.gmail.gmail_undo as m
    importlib.reload(m)
    m.resolve_account = lambda a: a
    return m


def _applied(moves=None):
    if moves is None:
        moves = [
            {"id": "m1", "category": "Action", "label_name": "GSD/Action"},
            {"id": "m2", "category": "Newsletters", "label_name": "GSD/Newsletters"},
        ]
    return {
        "applied_at": "2026-06-29T08:05:00+00:00",
        "account": "personal",
        "action": "move",
        "moves": moves,
        "moved_ids": [m["id"] for m in moves],
    }


# --- build_undo: inverse plan from applied result --------------------------

def test_build_undo_reverses_each_move():
    m = _reload()
    plan = m.build_undo("personal", applied=_applied())
    assert plan["action"] == "undo-move"
    assert {r["id"] for r in plan["reversals"]} == {"m1", "m2"}
    assert {r["label_name"] for r in plan["reversals"]} == {"GSD/Action", "GSD/Newsletters"}


def test_build_undo_empty_when_nothing_applied():
    m = _reload()
    plan = m.build_undo("personal", applied=_applied(moves=[]))
    assert plan["reversals"] == []


# --- apply_undo: mechanics -------------------------------------------------

def test_apply_undo_removes_gsd_and_adds_inbox_only():
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    plan = m.build_undo("personal", applied=_applied())
    result = m.apply_undo("personal", plan, svc)

    assert result["reversed_count"] == 2
    assert result["failed_count"] == 0
    for call in svc.modify_calls:
        body = call["body"]
        # exactly INBOX added, exactly one GSD label removed
        assert body["addLabelIds"] == ["INBOX"]
        assert len(body["removeLabelIds"]) == 1
        assert body["removeLabelIds"][0] in {"L_ACTION", "L_NEWS"}


def test_undo_never_touches_trash_or_spam():
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    plan = m.build_undo("personal", applied=_applied())
    m.apply_undo("personal", plan, svc)
    for call in svc.modify_calls:
        touched = set(call["body"]["addLabelIds"]) | set(call["body"]["removeLabelIds"])
        assert "TRASH" not in touched
        assert "SPAM" not in touched


def test_apply_undo_aborts_when_label_missing():
    m = _reload()
    # Label map without GSD/Newsletters → undo must abort before any mutation.
    labels = [lbl for lbl in _all_gsd_labels() if lbl["name"] != "GSD/Newsletters"]
    svc = FakeService(labels)
    plan = m.build_undo("personal", applied=_applied())
    with pytest.raises(ValueError, match="Missing Gmail label"):
        m.apply_undo("personal", plan, svc)
    assert svc.modify_calls == []  # nothing mutated


# --- inverse safety gate ---------------------------------------------------

def test_assert_safe_undo_rejects_adding_non_inbox():
    m = _reload()
    with pytest.raises(AssertionError, match="may only add INBOX"):
        m._assert_safe_undo(["L_ACTION"], ["L_ACTION"], {"L_ACTION": "GSD/Action"})


def test_assert_safe_undo_rejects_removing_non_gsd():
    m = _reload()
    with pytest.raises(AssertionError, match="non-GSD"):
        m._assert_safe_undo(["INBOX"], ["IMPORTANT"],
                            {"INBOX": "INBOX", "IMPORTANT": "IMPORTANT"})


def test_assert_safe_undo_rejects_forbidden_label():
    m = _reload()
    with pytest.raises(AssertionError, match="forbidden"):
        m._assert_safe_undo(["INBOX"], ["TRASH"], {"INBOX": "INBOX", "TRASH": "TRASH"})


def test_modify_undo_blocks_unsafe_call_before_api():
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    # Adding a GSD label (an apply-direction move) is illegal for undo.
    with pytest.raises(AssertionError):
        m._modify_undo(svc, "m1", ["L_ACTION"], ["INBOX"],
                       {"L_ACTION": "GSD/Action", "INBOX": "INBOX"})
    assert svc.modify_calls == []


# --- round-trip: apply then undo is a no-op on labels ----------------------

def test_apply_then_undo_is_label_noop():
    """apply moves m1→GSD/Action (−INBOX); undo must remove GSD/Action (+INBOX).
    Net effect on the two touched labels is zero."""
    import gogos.gmail.gmail_apply as apply_mod
    importlib.reload(apply_mod)
    undo_mod = _reload()

    svc = FakeService(_all_gsd_labels())
    apply_plan = {
        "account": "personal", "action": "move", "approved": True,
        "moves": [{"id": "m1", "category": "Action", "label_name": "GSD/Action"}],
        "stale_ids": [], "categories": ["Action"],
    }
    apply_mod.apply_plan("personal", apply_plan, svc)
    apply_call = svc.modify_calls[-1]["body"]

    undo_plan = undo_mod.build_undo("personal", applied=_applied(
        moves=[{"id": "m1", "category": "Action", "label_name": "GSD/Action"}]))
    undo_mod.apply_undo("personal", undo_plan, svc)
    undo_call = svc.modify_calls[-1]["body"]

    # Whatever apply added, undo removed; whatever apply removed, undo added.
    assert set(apply_call["addLabelIds"]) == set(undo_call["removeLabelIds"])
    assert set(apply_call["removeLabelIds"]) == set(undo_call["addLabelIds"])


# --- undo marks the batch undone (reconcile must skip it) -------------------

def _write_record(storage, date, hhmmss, applied_at, **extra):
    """Write a per-batch applied record under storage/approvals/me@x.com/<date>/."""
    import json

    d = storage / "approvals" / "me@x.com" / date
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"gmail-applied-{hhmmss}.json"
    rec = {**_applied(), "batch_id": path.stem, "applied_at": applied_at,
           "undone_at": None, **extra}
    path.write_text(json.dumps(rec))
    return path


def test_apply_undo_marks_applied_batch_undone(tmp_path, monkeypatch):
    """After undo, the applied record carries undone_at so gmail_reconcile
    never reads GogOS's own INBOX restorations as user corrections."""
    import json

    m = _reload()
    monkeypatch.setattr(m.gmail_apply, "STORAGE_ROOT", tmp_path)
    path = _write_record(tmp_path, "2026-06-29", "080500", "2026-06-29T08:05:00+00:00")

    svc = FakeService(_all_gsd_labels())
    plan = m.build_undo("me@x.com")
    m.apply_undo("me@x.com", plan, svc)

    assert json.loads(path.read_text())["undone_at"]


def test_load_applied_picks_newest_un_undone_across_dates(tmp_path, monkeypatch):
    """An undo after midnight still finds yesterday's batch; undone batches are skipped."""
    m = _reload()
    monkeypatch.setattr(m.gmail_apply, "STORAGE_ROOT", tmp_path)
    _write_record(tmp_path, "2026-06-28", "090000", "2026-06-28T09:00:00+00:00")
    _write_record(tmp_path, "2026-06-28", "230000", "2026-06-28T23:00:00+00:00")
    _write_record(tmp_path, "2026-06-29", "001000", "2026-06-29T00:10:00+00:00",
                  undone_at="2026-06-29T00:15:00+00:00")

    assert m.load_applied("me@x.com")["batch_id"] == "gmail-applied-230000"


def test_undo_sets_undone_at_on_one_record_only(tmp_path, monkeypatch):
    import json

    m = _reload()
    monkeypatch.setattr(m.gmail_apply, "STORAGE_ROOT", tmp_path)
    older = _write_record(tmp_path, "2026-06-29", "080000", "2026-06-29T08:00:00+00:00")
    newer = _write_record(tmp_path, "2026-06-29", "090000", "2026-06-29T09:00:00+00:00")

    plan = m.build_undo("me@x.com")
    assert plan["batch_id"] == "gmail-applied-090000"
    m.apply_undo("me@x.com", plan, FakeService(_all_gsd_labels()))

    assert json.loads(newer.read_text())["undone_at"]
    assert json.loads(older.read_text())["undone_at"] is None


def test_load_applied_raises_when_nothing_left_to_undo(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m.gmail_apply, "STORAGE_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        m.load_applied("me@x.com")


# --- per-batch applied records: two applies in one day ----------------------

class _ApplyAndLabelsService:
    """Fake Gmail with modify (apply/undo) and messages.get (reconcile)."""

    def __init__(self, labels_by_msg):
        self.modify_calls: list[dict] = []
        self._by_msg = labels_by_msg
        self._labels = _all_gsd_labels()

    def users(self):
        return self

    def labels(self):
        return self

    def list(self, userId):
        return _Exec({"labels": self._labels})

    def messages(self):
        return self

    def modify(self, userId, id, body):
        self.modify_calls.append({"id": id, "body": body})
        return _Exec(None)

    def get(self, userId, id, format):
        return _Exec({"labelIds": self._by_msg.get(id, [])})


def _batch(*moves):
    return {
        "generated_at": "2026-06-29T08:00:00+00:00",
        "account": "me@x.com",
        "action": "move",
        "approved": True,
        "moves": [
            {"id": mid, "category": cat, "label_name": f"GSD/{cat}", "from": sender}
            for mid, cat, sender in moves
        ],
        "stale_ids": [],
        "categories": sorted({cat for _, cat, _ in moves}),
    }


def test_two_applies_in_one_day_undo_second_then_first_reconcile_learns_both(
        tmp_path, monkeypatch):
    """Spec 1 item 2: each apply writes its own record; undo walks back newest
    first; reconcile learns from every unreconciled record, not just the last."""
    import json
    from datetime import datetime, timezone

    import gogos.gmail.gmail_apply as apply_mod
    import gogos.gmail.gmail_reconcile as rec_mod
    from gogos.gmail import gmail_ledger

    importlib.reload(apply_mod)
    undo_mod = _reload()
    importlib.reload(rec_mod)
    monkeypatch.setattr(rec_mod, "resolve_account", lambda a: a)

    storage = tmp_path / "storage"
    monkeypatch.setattr(apply_mod, "STORAGE_ROOT", storage)
    monkeypatch.setattr(rec_mod, "STORAGE_ROOT", storage)
    monkeypatch.setattr(gmail_ledger, "STORAGE_ROOT", storage)
    monkeypatch.setattr(gmail_ledger, "resolve_account", lambda a: a)
    monkeypatch.setattr(rec_mod, "_load_latest", lambda account, kind, filename: {})

    def fake_storage_path(module, account, kind, date=None):
        d = storage / module / account / kind / "2026-06-29"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(rec_mod, "storage_path", fake_storage_path)

    clock = iter([
        datetime(2026, 6, 29, 8, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 29, 9, 30, 0, tzinfo=timezone.utc),
    ])
    monkeypatch.setattr(apply_mod, "_utcnow", lambda: next(clock))
    import gogos.paths as paths_mod
    monkeypatch.setattr(paths_mod, "now_utc",
                        lambda: datetime(2026, 6, 29, 10, 0, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(apply_mod, "_approvals_dir", lambda account: (
        storage / "approvals" / account / "2026-06-29"))
    (storage / "approvals" / "me@x.com" / "2026-06-29").mkdir(parents=True)

    sender = "Promo <news@promo.example.com>"
    # The user later re-files m1, m2 (batch 1) and m3 (batch 2) into Review.
    svc = _ApplyAndLabelsService({
        "m1": ["L_REVIEW"], "m2": ["L_REVIEW"], "m3": ["L_REVIEW"],
        "m4": ["L_NEWS"],
    })

    apply_mod.apply_plan("me@x.com", _batch(
        ("m1", "Safe to Delete", sender), ("m2", "Safe to Delete", sender)), svc)
    apply_mod.apply_plan("me@x.com", _batch(
        ("m3", "Safe to Delete", sender),
        ("m4", "Newsletters", "TLDR <dan@tldrnewsletter.com>")), svc)

    day = storage / "approvals" / "me@x.com" / "2026-06-29"
    first, second = day / "gmail-applied-080000.json", day / "gmail-applied-093000.json"
    assert sorted(p.name for p in day.glob("gmail-applied*.json")) == [
        first.name, second.name]
    for path in (first, second):
        rec = json.loads(path.read_text())
        assert rec["batch_id"] == path.stem
        assert rec["undone_at"] is None

    # Reconcile learns from both records: 3 corrections across two batches
    # cross the auto-learn threshold for the sender.
    assert rec_mod.reconcile("me@x.com", service=svc) == 0
    artefact = json.loads((fake_storage_path("gmail", "me@x.com", "reconcile")
                           / "latest-reconcile.json").read_text())
    assert sorted(c["id"] for c in artefact["new_corrections"]) == ["m1", "m2", "m3"]
    assert artefact["learned"] == [
        {"sender": "promo.example.com", "category": "Review", "corrections": 3}]
    for path in (first, second):
        assert json.loads(path.read_text())["last_reconciled_at"]

    # Undo reverses the second batch first, marking only that record.
    plan = undo_mod.build_undo("me@x.com")
    assert {r["id"] for r in plan["reversals"]} == {"m3", "m4"}
    undo_mod.apply_undo("me@x.com", plan, svc)
    assert json.loads(second.read_text())["undone_at"]
    assert json.loads(first.read_text())["undone_at"] is None

    # Then the first.
    plan = undo_mod.build_undo("me@x.com")
    assert {r["id"] for r in plan["reversals"]} == {"m1", "m2"}
    undo_mod.apply_undo("me@x.com", plan, svc)
    assert json.loads(first.read_text())["undone_at"]

    # Nothing left to undo.
    with pytest.raises(FileNotFoundError):
        undo_mod.build_undo("me@x.com")


# --- legacy gmail-applied.json (R2): batches applied before per-batch records --

def _write_legacy(storage, date, applied_at, **extra):
    import json

    d = storage / "approvals" / "me@x.com" / date
    d.mkdir(parents=True, exist_ok=True)
    path = d / "gmail-applied.json"
    path.write_text(json.dumps({**_applied(), "applied_at": applied_at, **extra}))
    return path


def test_legacy_applied_record_is_undoable(tmp_path, monkeypatch):
    import json

    m = _reload()
    monkeypatch.setattr(m.gmail_apply, "STORAGE_ROOT", tmp_path)
    legacy = _write_legacy(tmp_path, "2026-06-28", "2026-06-28T08:00:00+00:00")

    applied = m.load_applied("me@x.com")
    assert applied["batch_id"] == "legacy"
    assert applied["undone_at"] is None

    plan = m.build_undo("me@x.com")
    assert plan["batch_id"] == "legacy"
    m.apply_undo("me@x.com", plan, FakeService(_all_gsd_labels()))
    assert json.loads(legacy.read_text())["undone_at"]
    with pytest.raises(FileNotFoundError):
        m.load_applied("me@x.com")


def test_legacy_record_keeps_its_undone_at_and_sorts_by_applied_at(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m.gmail_apply, "STORAGE_ROOT", tmp_path)
    _write_legacy(tmp_path, "2026-06-28", "2026-06-28T08:00:00+00:00",
                  undone_at="2026-06-28T09:00:00+00:00")
    _write_legacy(tmp_path, "2026-06-29", "2026-06-29T08:00:00+00:00")
    _write_record(tmp_path, "2026-06-29", "070000", "2026-06-29T07:00:00+00:00")

    records = m.gmail_apply.applied_records("me@x.com")
    assert [r["applied_at"] for _, r in records] == [
        "2026-06-29T08:00:00+00:00", "2026-06-29T07:00:00+00:00",
        "2026-06-28T08:00:00+00:00"]
    assert records[-1][1]["undone_at"] == "2026-06-28T09:00:00+00:00"
    assert m.load_applied("me@x.com")["batch_id"] == "legacy"
