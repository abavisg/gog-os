"""Tests for gogos.gmail.gmail_reconcile — no network, no live Gmail API.

The most important tests prove the §8 acceptance criteria: a manual move is
detected as a correction and attributed to its sender; after 3 corrections the
ledger auto-learns the corrected category (logged, revertible); auto-learn can
never make protected mail deletable; a rescued sender is excluded from
unsubscribe candidates while a never-rescued one is surfaced.
"""
from __future__ import annotations

import importlib

from gogos.gmail import gmail_ledger


def _reload():
    import gogos.gmail.gmail_reconcile as m
    importlib.reload(m)
    m.resolve_account = lambda a: a
    return m


def _applied(moves=None, **extra):
    if moves is None:
        moves = [
            {"id": "m1", "category": "Newsletters", "label_name": "GSD/Newsletters",
             "from": "TLDR <dan@tldrnewsletter.com>"},
            {"id": "m2", "category": "Safe to Delete", "label_name": "GSD/Safe to Delete",
             "from": "Promo <news@promo.example.com>"},
        ]
    return {"applied_at": "2026-06-30T08:00:00+00:00", "account": "me@x.com",
            "action": "move", "moves": moves,
            "moved_ids": [m["id"] for m in moves], **extra}


def _ledger(senders=None):
    return {"fingerprint": "", "senders": senders or {}}


# --- v1b: detect_corrections -------------------------------------------------

def test_rescue_to_inbox_is_a_correction_attributed_to_sender():
    """§8 acceptance: a message moved since apply is detected and attributed."""
    m = _reload()
    current = {"m1": ["INBOX"], "m2": ["GSD/Safe to Delete"]}
    corrections = m.detect_corrections(_applied(), current)
    assert len(corrections) == 1
    c = corrections[0]
    assert c["id"] == "m1"
    assert c["sender"] == "tldrnewsletter.com"
    assert c["from_category"] == "Newsletters"
    assert c["to"] == "INBOX"


def test_refile_to_other_gsd_names_the_corrected_category():
    m = _reload()
    current = {"m1": ["GSD/Review"], "m2": ["GSD/Safe to Delete"]}
    corrections = m.detect_corrections(_applied(), current)
    assert len(corrections) == 1
    assert corrections[0]["to"] == "Review"


def test_refile_wins_over_rescue_when_both_present():
    m = _reload()
    current = {"m1": ["INBOX", "GSD/Review"], "m2": ["GSD/Safe to Delete"]}
    corrections = m.detect_corrections(_applied(), current)
    assert corrections[0]["to"] == "Review"


def test_unmoved_messages_yield_no_corrections():
    m = _reload()
    current = {"m1": ["GSD/Newsletters"], "m2": ["GSD/Safe to Delete"]}
    assert m.detect_corrections(_applied(), current) == []


def test_deleted_message_is_never_a_correction():
    m = _reload()
    current = {"m1": None, "m2": ["GSD/Safe to Delete"]}
    assert m.detect_corrections(_applied(), current) == []


def test_label_removed_but_still_archived_is_ambiguous_and_skipped():
    m = _reload()
    current = {"m1": [], "m2": ["GSD/Safe to Delete"]}
    assert m.detect_corrections(_applied(), current) == []


def test_undone_batch_yields_no_corrections():
    """/email-undo restored INBOX itself — never read as user corrections."""
    m = _reload()
    applied = _applied(undone_at="2026-06-30T09:00:00+00:00")
    current = {"m1": ["INBOX"], "m2": ["INBOX"]}
    assert m.detect_corrections(applied, current) == []


# --- state: idempotent recording ----------------------------------------------

def test_recording_same_correction_twice_never_double_counts():
    m = _reload()
    state = {"corrections": {}}
    correction = {"id": "m1", "sender": "a.com", "from_category": "Newsletters",
                  "to": "INBOX", "detected_at": "t"}
    assert len(m.record_corrections(state, [correction])) == 1
    assert m.record_corrections(state, [correction]) == []
    assert m.sender_counts(state) == {"a.com": {"INBOX": 1}}


# --- v1c: auto-learn ------------------------------------------------------------

def _state_with(sender, to, n, from_category="Newsletters"):
    return {"corrections": {
        f"m{i}": {"sender": sender, "from_category": from_category,
                  "to": to, "detected_at": "t"}
        for i in range(n)
    }}


def test_three_corrections_auto_learn_the_corrected_category(capsys):
    """§8 acceptance: after 3 corrections the ledger updates and it is logged."""
    m = _reload()
    ledger = _ledger({"promo.example.com": {"category": "Newsletters", "source": "builtin"}})
    learned, suggestions = m.auto_learn(_state_with("promo.example.com", "Review", 3), ledger)

    assert learned == [{"sender": "promo.example.com", "category": "Review", "corrections": 3}]
    assert suggestions == []
    entry = ledger["senders"]["promo.example.com"]
    assert entry["category"] == "Review"
    assert entry["source"] == "learned"
    assert "re-learned" in capsys.readouterr().err  # logged, never silent


def test_two_corrections_learn_nothing():
    m = _reload()
    ledger = _ledger()
    learned, suggestions = m.auto_learn(_state_with("a.com", "Review", 2), ledger)
    assert learned == [] and suggestions == []
    assert ledger["senders"] == {}


def test_repeated_rescues_suggest_a_user_rule_but_never_pin():
    m = _reload()
    ledger = _ledger()
    learned, suggestions = m.auto_learn(_state_with("a.com", "INBOX", 3), ledger)
    assert learned == []
    assert suggestions == [{"sender": "a.com", "rescues": 3}]
    assert ledger["senders"] == {}  # no pin that would re-archive rescued mail


def test_auto_learn_is_idempotent_across_runs():
    m = _reload()
    state = _state_with("a.com", "Review", 3)
    ledger = _ledger()
    learned1, _ = m.auto_learn(state, ledger)
    learned2, _ = m.auto_learn(state, ledger)
    assert len(learned1) == 1
    assert learned2 == []  # already learned — not re-reported


def test_learned_pin_can_never_make_protected_mail_deletable():
    """§8 acceptance: auto-learn never routes an important mail to Safe to
    Delete — protected mail ignores ledger pins entirely (slice 3)."""
    import gogos.gmail.gmail_classify as classify_mod
    importlib.reload(classify_mod)
    from tests.test_gmail_classify import CONFIG

    ledger = _ledger({"natwest.com": {"category": "Safe to Delete", "source": "learned"}})
    out = classify_mod.classify_messages(
        [{"id": "m1", "from": "NatWest <x@natwest.com>",
          "subject": "Your latest card statement is now available"}],
        config=CONFIG, ledger=ledger)
    assert out["items"][0]["category"] == "Action"


# --- v1d: unsubscribe candidates -------------------------------------------------

SLIM = {"messages": [
    {"id": "n1", "from": "TLDR <dan@tldrnewsletter.com>", "subject": "news",
     "unsubscribe": "<https://tldr.example/unsub>, <mailto:unsub@tldr.example>"},
    {"id": "n2", "from": "TLDR <dan@tldrnewsletter.com>", "subject": "more news",
     "unsubscribe": "<https://tldr.example/unsub>"},
    {"id": "p1", "from": "Promo <news@promo.example.com>", "subject": "sale",
     "unsubscribe": "<https://promo.example/unsub>"},
    {"id": "b1", "from": "NatWest <x@natwest.com>", "subject": "statement",
     "unsubscribe": "<https://natwest.example/unsub>"},
    {"id": "q1", "from": "Quiet <x@quiet.example.com>", "subject": "hello",
     "unsubscribe": ""},
]}
TRIAGE = {"items": [
    {"id": "n1", "category": "Newsletters"},
    {"id": "n2", "category": "Newsletters"},
    {"id": "p1", "category": "Safe to Delete"},
    {"id": "b1", "category": "Action"},
    {"id": "q1", "category": "Newsletters"},
]}


def test_never_rescued_sender_with_header_is_a_candidate():
    m = _reload()
    candidates = m.unsubscribe_candidates(SLIM, TRIAGE, {"corrections": {}})
    senders = {c["sender"] for c in candidates}
    assert "tldrnewsletter.com" in senders
    assert "promo.example.com" in senders
    tldr = next(c for c in candidates if c["sender"] == "tldrnewsletter.com")
    assert tldr["message_count"] == 2
    assert "https://tldr.example/unsub" in tldr["unsubscribe"]


def test_rescued_sender_is_excluded_from_candidates():
    """§8 acceptance: a sender you rescue gets re-learned, never unsubscribed."""
    m = _reload()
    state = {"corrections": {"n9": {
        "sender": "tldrnewsletter.com", "from_category": "Newsletters",
        "to": "INBOX", "detected_at": "t"}}}
    senders = {c["sender"] for c in m.unsubscribe_candidates(SLIM, TRIAGE, state)}
    assert "tldrnewsletter.com" not in senders
    assert "promo.example.com" in senders  # never rescued — still surfaced


def test_action_mail_and_headerless_senders_are_never_candidates():
    m = _reload()
    senders = {c["sender"] for c in
               m.unsubscribe_candidates(SLIM, TRIAGE, {"corrections": {}})}
    assert "natwest.com" not in senders        # Action — not an unsub category
    assert "quiet.example.com" not in senders  # no List-Unsubscribe header


# --- fetch_current_labels (fake service; labelIds only) --------------------------

class _Exec:
    def __init__(self, value, error=None):
        self._value, self._error = value, error

    def execute(self):
        if self._error:
            raise self._error
        return self._value


class FakeLabelService:
    """messages.get(format=minimal) + labels.list — read-only fake."""

    def __init__(self, labels_by_msg):
        self._by_msg = labels_by_msg

    def users(self):
        return self

    def labels(self):
        return self

    def list(self, userId):
        return _Exec({"labels": [
            {"id": "L_NEWS", "name": "GSD/Newsletters"},
            {"id": "L_REVIEW", "name": "GSD/Review"},
            {"id": "L_DELETE", "name": "GSD/Safe to Delete"},
            {"id": "INBOX", "name": "INBOX"},
        ]})

    def messages(self):
        return self

    def get(self, userId, id, format):
        assert format == "minimal"  # labels only — nothing heavier
        if id not in self._by_msg:
            return _Exec(None, error=RuntimeError("404"))
        return _Exec({"labelIds": self._by_msg[id]})


def test_fetch_current_labels_maps_ids_to_names_and_none_for_missing():
    m = _reload()
    svc = FakeLabelService({"m1": ["INBOX"], "m2": ["L_REVIEW"]})
    out = m.fetch_current_labels(svc, ["m1", "m2", "gone"])
    assert out == {"m1": ["INBOX"], "m2": ["GSD/Review"], "gone": None}


# --- load_latest_applied: newest batch across dates -------------------------------

def test_load_latest_applied_scans_dates_newest_first(tmp_path, monkeypatch):
    """Corrections happen days after an apply — reconcile must find the most
    recent applied batch, not just today's (unlike undo, which is today-only)."""
    import json

    m = _reload()
    monkeypatch.setattr(m, "STORAGE_ROOT", tmp_path)
    root = tmp_path / "approvals" / "me@x.com"
    (root / "2026-06-28").mkdir(parents=True)
    (root / "2026-06-30").mkdir(parents=True)
    (root / "2026-07-01").mkdir(parents=True)  # plan only, no applied file
    (root / "2026-06-28" / "gmail-applied.json").write_text(json.dumps({"tag": "old"}))
    (root / "2026-06-30" / "gmail-applied.json").write_text(json.dumps({"tag": "new"}))

    assert m.load_latest_applied("me@x.com")["tag"] == "new"


def test_load_latest_applied_empty_when_nothing_applied(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "STORAGE_ROOT", tmp_path)
    assert m.load_latest_applied("me@x.com") == {}


# --- end-to-end reconcile() -------------------------------------------------------

def test_reconcile_end_to_end_writes_artefact(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "STORAGE_ROOT", tmp_path / "storage")

    def fake_storage_path(module, account, kind, date=None):
        d = tmp_path / "storage" / module / account / kind / "2026-07-01"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(m, "storage_path", fake_storage_path)
    monkeypatch.setattr(gmail_ledger, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(gmail_ledger, "resolve_account", lambda a: a)

    monkeypatch.setattr(m, "load_latest_applied", lambda account: _applied())
    monkeypatch.setattr(m, "_load_latest", lambda account, kind, filename:
                        SLIM if kind == "inbox" else TRIAGE)

    # m1 was rescued to inbox; m2 sits where it was filed (Safe to Delete).
    svc = FakeLabelService({"m1": ["INBOX"], "m2": ["L_DELETE"]})
    assert m.reconcile("me@x.com", service=svc) == 0

    import json
    artefact = json.loads(
        (fake_storage_path("gmail", "me@x.com", "reconcile") / "latest-reconcile.json")
        .read_text())
    assert [c["id"] for c in artefact["new_corrections"]] == ["m1"]
    assert artefact["sender_counts"] == {"tldrnewsletter.com": {"INBOX": 1}}
    # rescued this run -> excluded from unsubscribe candidates
    senders = {c["sender"] for c in artefact["unsubscribe_candidates"]}
    assert "tldrnewsletter.com" not in senders
    assert "promo.example.com" in senders

    # State persisted: running again detects nothing new.
    assert m.reconcile("me@x.com", service=svc) == 0
    artefact2 = json.loads(
        (fake_storage_path("gmail", "me@x.com", "reconcile") / "latest-reconcile.json")
        .read_text())
    assert artefact2["new_corrections"] == []
