"""Tests for gogos.gmail.gmail_loop — no network. The batch read pipeline and
the Gmail service are stubbed so we exercise the loop control flow only.
"""
from __future__ import annotations

import importlib

import pytest


def _reload():
    import gogos.gmail.gmail_loop as m
    importlib.reload(m)
    return m


class FakeService:
    """Reports a shrinking inbox count via labels().get."""
    def __init__(self, counts):
        self._counts = list(counts)
        self.idx = 0

    def users(self):
        return self

    def labels(self):
        return self

    def get(self, userId, id):
        return _Exec(self._counts)

    def execute(self):  # not used directly
        return {}


class _Exec:
    def __init__(self, counts_ref):
        self._counts = counts_ref

    def execute(self):
        # pop the next count each call
        return {"messagesTotal": self._counts.pop(0) if self._counts else 0}


@pytest.fixture
def patched(monkeypatch):
    """Patch resolve_account, the batch-read step, and build/apply so the loop
    runs with no network. Returns a dict of controllable knobs."""
    m = _reload()
    monkeypatch.setattr(m, "resolve_account", lambda a: a)

    state = {"batch_sizes": [], "applied": [], "fail_on": None}

    def fake_batch_read(account):
        return state["batch_sizes"].pop(0) if state["batch_sizes"] else 0
    monkeypatch.setattr(m, "_run_batch_read", fake_batch_read)

    def fake_build_plan(account):
        # plan size mirrors whatever the last batch read reported
        return {"account": account, "approved": False,
                "moves": [{"id": f"x{i}"} for i in range(state.get("_last", 0))]}
    # capture the batch size for plan size
    orig = fake_batch_read
    def wrapped(account):
        n = orig(account)
        state["_last"] = n
        return n
    monkeypatch.setattr(m, "_run_batch_read", wrapped)
    monkeypatch.setattr(m.gmail_apply, "build_plan", fake_build_plan)

    def fake_apply(account, plan, service):
        n = len(plan["moves"])
        failed = n if state["fail_on"] == len(state["applied"]) + 1 else 0
        state["applied"].append(n)
        return {"account": account, "moved_count": n - failed,
                "failed_count": failed, "moved_ids": [], "failed": []}
    monkeypatch.setattr(m.gmail_apply, "apply_plan", fake_apply)

    return m, state


def test_default_stops_for_approval(patched):
    """Without --yes, the loop builds one plan then stops awaiting approval."""
    m, state = patched
    state["batch_sizes"] = [50]
    result = m.run_loop("me@x.com", auto_apply=False, service=FakeService([50, 0]))
    assert result["status"] == "awaiting_approval"
    assert result["pending_plan_size"] == 50
    assert state["applied"] == []  # nothing applied


def test_auto_apply_drains_until_empty(patched):
    """With auto_apply, loop runs batches until a batch read returns 0."""
    m, state = patched
    state["batch_sizes"] = [200, 200, 37, 0]
    result = m.run_loop("me@x.com", auto_apply=True, service=FakeService([437, 237, 37, 0]))
    assert result["status"] == "empty"
    assert result["iterations"] == 3
    assert [b["moved"] for b in result["batches"]] == [200, 200, 37]


def test_auto_apply_single_batch_when_under_cap(patched):
    m, state = patched
    state["batch_sizes"] = [12, 0]
    result = m.run_loop("me@x.com", auto_apply=True, service=FakeService([12, 0]))
    assert result["status"] == "empty"
    assert result["iterations"] == 1


def test_max_iterations_bound(patched):
    """Loop must not run forever if the inbox never drains."""
    m, state = patched
    state["batch_sizes"] = [100] * 50  # never returns 0
    result = m.run_loop("me@x.com", auto_apply=True, max_iterations=3,
                        service=FakeService([100] * 60))
    assert result["status"] == "max_iterations_reached"
    assert result["iterations"] == 3


def test_stops_on_failures(patched):
    m, state = patched
    state["batch_sizes"] = [100, 100, 0]
    state["fail_on"] = 1  # first apply reports failures
    result = m.run_loop("me@x.com", auto_apply=True, service=FakeService([100, 100]))
    assert result["status"] == "failures"
    assert result["iterations"] == 1
