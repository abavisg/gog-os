"""Tests for gogos.gmail.gmail_apply — no network, no live Gmail API.

The most important tests here prove the never-delete invariant: GogOS only ever
adds GSD/* labels and removes INBOX, never trashes/deletes/spams.
"""
from __future__ import annotations

import importlib

import pytest


def _reload():
    import gogos.gmail.gmail_apply as m
    importlib.reload(m)
    return m


# --- Fakes -----------------------------------------------------------------

class FakeMessages:
    def __init__(self, recorder):
        self._rec = recorder

    def modify(self, userId, id, body):
        self._rec.append({"id": id, "body": body})
        return _Exec(None)


class FakeLabels:
    def __init__(self, labels):
        self._labels = labels

    def list(self, userId):
        return _Exec({"labels": self._labels})


class FakeUsers:
    def __init__(self, labels, recorder):
        self._messages = FakeMessages(recorder)
        self._labels = FakeLabels(labels)

    def messages(self):
        return self._messages

    def labels(self):
        return self._labels


class FakeService:
    """Records every modify() call so tests can assert exactly what happened."""

    def __init__(self, labels):
        self.modify_calls: list[dict] = []
        self._users = FakeUsers(labels, self.modify_calls)

    def users(self):
        return self._users


class _Exec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


def _all_gsd_labels():
    return [
        {"id": "L_ACTION", "name": "GSD/Action"},
        {"id": "L_EVENTS", "name": "GSD/Events"},
        {"id": "L_INFO", "name": "GSD/Information"},
        {"id": "L_NEWS", "name": "GSD/Newsletters"},
        {"id": "L_REVIEW", "name": "GSD/Review"},
        {"id": "L_DELETE", "name": "GSD/Safe to Delete"},
        {"id": "INBOX", "name": "INBOX"},
        {"id": "TRASH", "name": "TRASH"},
    ]


def _plan(approved=True, moves=None):
    if moves is None:
        moves = [
            {"id": "m1", "category": "Action", "label_name": "GSD/Action"},
            {"id": "m2", "category": "Newsletters", "label_name": "GSD/Newsletters"},
        ]
    return {
        "generated_at": "2026-06-29T08:00:00+00:00",
        "account": "personal",
        "action": "move",
        "approved": approved,
        "moves": moves,
        "stale_ids": [],
        "categories": sorted({m["category"] for m in moves}),
    }


# --- Applied-result record (feeds /email-undo) -----------------------------

def test_apply_records_applied_result_for_undo(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "_approvals_dir", lambda account: tmp_path)
    svc = FakeService(_all_gsd_labels())
    m.apply_plan("personal", _plan(), svc)

    import json
    applied = json.loads((tmp_path / "gmail-applied.json").read_text())
    assert applied["moved_ids"] == ["m1", "m2"]
    assert {mv["category"] for mv in applied["moves"]} == {"Action", "Newsletters"}
    assert {mv["label_name"] for mv in applied["moves"]} == {"GSD/Action", "GSD/Newsletters"}


def test_apply_records_only_successful_moves(tmp_path, monkeypatch):
    """A move that fails must NOT appear in the applied result (undo won't over-reverse)."""
    m = _reload()
    monkeypatch.setattr(m, "_approvals_dir", lambda account: tmp_path)
    # GSD/Newsletters missing → resolve_destinations raises before any move, so
    # instead drop a category the plan doesn't need and force one modify to fail.
    svc = FakeService(_all_gsd_labels())
    orig_modify = m._modify

    def _flaky(service, message_id, add_label_ids, remove_label_ids, label_id_to_name):
        if message_id == "m2":
            raise RuntimeError("boom")
        return orig_modify(service, message_id, add_label_ids, remove_label_ids,
                           label_id_to_name)

    monkeypatch.setattr(m, "_modify", _flaky)
    result = m.apply_plan("personal", _plan(), svc)
    assert result["moved_count"] == 1 and result["failed_count"] == 1

    import json
    applied = json.loads((tmp_path / "gmail-applied.json").read_text())
    assert applied["moved_ids"] == ["m1"]  # m2 excluded


# --- Safety invariant: never delete ----------------------------------------

def test_apply_adds_gsd_label_and_removes_inbox_only():
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    result = m.apply_plan("personal", _plan(), svc)

    assert result["moved_count"] == 2
    assert result["failed_count"] == 0
    for call in svc.modify_calls:
        body = call["body"]
        # exactly one GSD label added, exactly INBOX removed
        assert body["removeLabelIds"] == ["INBOX"]
        assert len(body["addLabelIds"]) == 1
        assert body["addLabelIds"][0] in {"L_ACTION", "L_NEWS"}


def test_never_touches_trash_or_spam():
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    m.apply_plan("personal", _plan(), svc)
    for call in svc.modify_calls:
        body = call["body"]
        touched = set(body["addLabelIds"]) | set(body["removeLabelIds"])
        assert "TRASH" not in touched
        assert "SPAM" not in touched


def test_assert_safe_rejects_removing_non_inbox():
    m = _reload()
    # Removing a non-INBOX, non-forbidden label (e.g. IMPORTANT) must be refused.
    with pytest.raises(AssertionError, match="Only INBOX"):
        m._assert_safe(["L_ACTION"], ["INBOX", "IMPORTANT"], {"L_ACTION": "GSD/Action"})


def test_assert_safe_rejects_adding_non_gsd_label():
    m = _reload()
    with pytest.raises(AssertionError, match="non-GSD"):
        m._assert_safe(["L_RANDOM"], ["INBOX"], {"L_RANDOM": "Important"})


def test_assert_safe_rejects_forbidden_label():
    m = _reload()
    with pytest.raises(AssertionError, match="forbidden"):
        m._assert_safe(["TRASH"], ["INBOX"], {"TRASH": "TRASH"})


def test_modify_helper_blocks_unsafe_call_before_api():
    """_modify must raise BEFORE calling the service if the op is unsafe."""
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    with pytest.raises(AssertionError):
        m._modify(
            svc, "m1",
            add_label_ids=["L_ACTION"],
            remove_label_ids=["INBOX", "TRASH"],
            label_id_to_name={"L_ACTION": "GSD/Action"},
        )
    assert svc.modify_calls == []  # nothing reached the API


# --- Approval gate ---------------------------------------------------------

def test_apply_refuses_unapproved_plan():
    m = _reload()
    svc = FakeService(_all_gsd_labels())
    with pytest.raises(PermissionError, match="not approved"):
        m.apply_plan("personal", _plan(approved=False), svc)
    assert svc.modify_calls == []


# --- Missing label: abort, never partial -----------------------------------

def test_apply_aborts_when_gsd_label_missing():
    m = _reload()
    labels = [
        {"id": "L_ACTION", "name": "GSD/Action"},
        {"id": "INBOX", "name": "INBOX"},
    ]  # Newsletters label deliberately absent
    svc = FakeService(labels)
    with pytest.raises(ValueError, match="Newsletters"):
        m.apply_plan("personal", _plan(), svc)
    # aborted during resolution, before any modify
    assert svc.modify_calls == []


def test_resolve_destinations_lists_all_missing():
    m = _reload()
    label_map = {"GSD/Action": "L_ACTION"}
    with pytest.raises(ValueError) as exc:
        m.resolve_destinations({"Action", "Events", "Review"}, label_map)
    msg = str(exc.value)
    assert "GSD/Events" in msg and "GSD/Review" in msg
    assert "GSD/Action" not in msg


# --- Plan building ---------------------------------------------------------

def test_build_plan_maps_categories_to_labels(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "_write_plan", lambda account, plan: tmp_path / "p.json")

    triage = {
        "account": "personal",
        "items": [
            {"id": "a", "category": "Action", "confidence": 0.9,
             "rationale": "x", "suggested_action": "reply"},
            {"id": "b", "category": "Events", "confidence": 0.8,
             "rationale": "y", "suggested_action": "add"},
        ],
    }
    slim = {"messages": [
        {"id": "a", "subject": "Pay invoice", "from": "acct@x.com",
         "date": "2026-06-29T07:00:00+00:00"},
        {"id": "b", "subject": "Invite", "from": "cal@x.com",
         "date": "2026-06-29T07:30:00+00:00"},
    ]}

    plan = m.build_plan("personal", triage=triage, slim=slim)

    assert plan["approved"] is False
    assert plan["action"] == "move"
    labels = {mv["id"]: mv["label_name"] for mv in plan["moves"]}
    assert labels == {"a": "GSD/Action", "b": "GSD/Events"}


def test_build_plan_flags_stale_emails(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "_write_plan", lambda account, plan: tmp_path / "p.json")
    # cutoff is yesterday-00:00 UTC; this date is far in the past => stale
    triage = {"account": "personal", "items": [
        {"id": "old", "category": "Review", "confidence": 0.5,
         "rationale": "x", "suggested_action": "review"},
    ]}
    slim = {"messages": [
        {"id": "old", "subject": "Ancient", "from": "x@x.com",
         "date": "2020-01-01T00:00:00+00:00"},
    ]}
    plan = m.build_plan("personal", triage=triage, slim=slim)
    assert plan["stale_ids"] == ["old"]


def test_gsd_label_name():
    m = _reload()
    assert m.gsd_label_name("Safe to Delete") == "GSD/Safe to Delete"
    assert m.gsd_label_name("Action") == "GSD/Action"


def test_is_gsd_destination():
    m = _reload()
    assert m._is_gsd_destination("GSD/Action")
    assert not m._is_gsd_destination("Action")
    assert not m._is_gsd_destination("GSD/Unknown")
    assert not m._is_gsd_destination("Other/Action")


def test_applied_result_keeps_sender_for_reconcile(tmp_path, monkeypatch):
    """gmail_reconcile attributes manual moves by sender — apply must keep it."""
    m = _reload()
    monkeypatch.setattr(m, "_approvals_dir", lambda account: tmp_path)
    svc = FakeService(_all_gsd_labels())
    m.apply_plan("personal", _plan(), svc)

    import json
    applied = json.loads((tmp_path / "gmail-applied.json").read_text())
    for mv in applied["moves"]:
        assert "from" in mv
