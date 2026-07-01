"""Tests for gogos.gmail.gmail_undo — no network, no live Gmail API.

The most important tests prove undo is the exact inverse of apply and preserves
the never-delete invariant: undo only ever removes GSD/* labels and adds INBOX.
"""
from __future__ import annotations

import importlib

import pytest

# Reuse the fake Gmail service from the apply tests.
from tests.test_gmail_apply import FakeService, _all_gsd_labels


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

def test_apply_undo_marks_applied_batch_undone(tmp_path, monkeypatch):
    """After undo, the applied record carries undone_at so gmail_reconcile
    never reads GogOS's own INBOX restorations as user corrections."""
    import json

    m = _reload()
    monkeypatch.setattr(m, "_approvals_dir", lambda account: tmp_path)
    applied = _applied()
    (tmp_path / "gmail-applied.json").write_text(json.dumps(applied))

    svc = FakeService(_all_gsd_labels())
    plan = m.build_undo("personal", applied=applied)
    m.apply_undo("personal", plan, svc)

    annotated = json.loads((tmp_path / "gmail-applied.json").read_text())
    assert "undone_at" in annotated
