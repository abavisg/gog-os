"""Tests for gogos.gmail.gmail_classify — pure, no network.

The most important tests prove the never-delete-the-important invariant: mail
that is financial, security-related, civic, or from a real person must NEVER be
classified as "Safe to Delete", regardless of other signals.
"""
from __future__ import annotations

import importlib

import pytest


def _reload():
    import gogos.gmail.gmail_classify as m
    importlib.reload(m)
    return m


# A self-contained config so tests don't depend on the shipped JSON.
CONFIG = {
    "bank_domains": ["natwest.com", "octopus.energy"],
    "newsletter_domains": ["substack.com", "tldrnewsletter.com"],
    "promo_domains": ["national-lottery.co.uk", "nespresso.com"],
    "info_domains": ["github.com", "ebay.com"],
    "event_domains": ["luma-mail.com"],
    "personal_patterns": ["@gmail.com"],
}


def _msg(frm, subject, mid="m1"):
    return {"id": mid, "from": frm, "subject": subject}


def _cat(m, frm, subject):
    return m.classify_one(_msg(frm, subject), CONFIG)[0]


# --- Safety invariant: protected mail never becomes Safe to Delete ----------

def test_bank_statement_is_action_not_deletable():
    m = _reload()
    assert _cat(m, "NatWest <x@natwest.com>", "Your latest card statement is now available") == "Action"


def test_bank_without_financial_ask_is_information():
    m = _reload()
    assert _cat(m, "NatWest <x@natwest.com>", "We've updated our app") == "Information"


def test_security_alert_is_action():
    m = _reload()
    assert _cat(m, "Google <no-reply@accounts.google.com>", "Security alert") == "Action"


def test_failed_payment_is_action():
    m = _reload()
    assert _cat(m, "Anthropic <billing@mail.anthropic.com>", "Your £15.00 payment was unsuccessful") == "Action"


def test_civic_is_action():
    m = _reload()
    assert _cat(m, "Electoral Services <x@richmond.gov.uk>", "Annual canvass") == "Action"


def test_real_person_is_review_never_deleted():
    m = _reload()
    assert _cat(m, "Kevin Galvin <kevin@gmail.com>", "Re: tournament on Saturday") == "Review"


def test_protected_signals_never_safe_to_delete():
    """Sweep: financial/security/civic/person subjects must never be deletable,
    even when the sender domain also looks promotional."""
    m = _reload()
    protected_cases = [
        ("billing@nespresso.com", "Please update your subscription payment method"),  # promo domain + payment
        ("noreply@national-lottery.co.uk", "Security alert: new login"),  # promo domain + security
        ("someone@gmail.com", "win a prize"),  # real person, spammy subject
    ]
    for frm, subj in protected_cases:
        assert m.classify_one(_msg(frm, subj), CONFIG)[0] != "Safe to Delete", (frm, subj)


# --- Each routing rule ------------------------------------------------------

def test_calendar_invitation_is_event():
    m = _reload()
    assert _cat(m, "Artemis <a@gmail.com>", "Invitation: ASSEMBLY @ Wed 15 Jul 2026") == "Events"


def test_event_platform_is_event():
    m = _reload()
    assert _cat(m, "Networx <x@user.luma-mail.com>", "You are invited to Networking Night") == "Events"


def test_linkedin_is_review():
    m = _reload()
    assert _cat(m, "LinkedIn Job Alerts <x@linkedin.com>", "CTO at Stealth Startup") == "Review"


def test_social_noise_is_safe_to_delete():
    m = _reload()
    assert _cat(m, "Nextdoor <x@rs.email.nextdoor.co.uk>", "Susannah reacted to your reply") == "Safe to Delete"


def test_order_notice_is_information():
    m = _reload()
    assert _cat(m, "eBay <ebay@ebay.com>", "We sent your payout") == "Information"


def test_promo_is_safe_to_delete():
    m = _reload()
    assert _cat(m, "The National Lottery <news@info.national-lottery.co.uk>", "Tonight's draw") == "Safe to Delete"


def test_newsletter_is_newsletters():
    m = _reload()
    assert _cat(m, "TLDR <dan@tldrnewsletter.com>", "Apple price hikes") == "Newsletters"


def test_unknown_longtail_defaults_to_newsletters():
    m = _reload()
    assert _cat(m, "Random <x@some-unknown-saas.io>", "Weekly update") == "Newsletters"


# --- Coverage / structure ---------------------------------------------------

def test_classify_messages_covers_every_id_once():
    m = _reload()
    msgs = [_msg("a@natwest.com", "statement", "id1"),
            _msg("b@linkedin.com", "job", "id2"),
            _msg("c@tldrnewsletter.com", "news", "id3")]
    out = m.classify_messages(msgs, config=CONFIG, account="me@x.com")
    ids = [i["id"] for i in out["items"]]
    assert ids == ["id1", "id2", "id3"]
    assert out["account"] == "me@x.com"
    assert "generated_at" in out


def test_output_items_have_required_schema():
    """Output must match what gmail_triage.validate_triage requires."""
    m = _reload()
    out = m.classify_messages([_msg("a@natwest.com", "bill", "id1")], config=CONFIG)
    item = out["items"][0]
    for key in ("id", "category", "confidence", "rationale", "suggested_action"):
        assert key in item


def test_every_category_is_valid():
    m = _reload()
    valid = {"Action", "Review", "Events", "Information", "Newsletters", "Safe to Delete"}
    samples = [
        _msg("a@natwest.com", "statement"), _msg("b@linkedin.com", "job"),
        _msg("c@tldrnewsletter.com", "news"), _msg("d@info.national-lottery.co.uk", "draw"),
        _msg("e@user.luma-mail.com", "Invitation: event"), _msg("f@ebay.com", "your order"),
    ]
    out = m.classify_messages(samples, config=CONFIG)
    for item in out["items"]:
        assert item["category"] in valid


# --- User rules (Phase 4.6 §2) -----------------------------------------------

RULES = [
    {"match": {"domain": "tldrnewsletter.com"}, "category": "Review"},
    {"match": {"domain": "natwest.com"}, "category": "Safe to Delete"},  # must be refused
    {"match": {"sender": "linkedin jobs"}, "category": "Newsletters"},
]


def test_user_rule_overrides_builtin():
    m = _reload()
    out = m.classify_messages([_msg("TLDR <dan@tldrnewsletter.com>", "Apple price hikes")],
                              config=CONFIG, rules=RULES)
    item = out["items"][0]
    assert item["category"] == "Review"          # builtin says Newsletters
    assert "User rule" in item["rationale"]


def test_user_rule_can_never_push_protected_mail_to_safe_to_delete(capsys):
    """The never-delete invariant is absolute: a user rule targeting protected
    mail with Safe to Delete is refused, logged, and built-ins take over."""
    m = _reload()
    protected_cases = [
        ("NatWest <x@natwest.com>", "Your latest card statement is now available"),
        ("NatWest <x@natwest.com>", "Security alert: new login"),
        ("NatWest <x@natwest.com>", "We've updated our app"),  # bank domain alone
    ]
    for frm, subj in protected_cases:
        out = m.classify_messages([_msg(frm, subj)], config=CONFIG, rules=RULES)
        assert out["items"][0]["category"] != "Safe to Delete", (frm, subj)
    assert "refused" in capsys.readouterr().err


def test_user_rule_may_reroute_nonprotected_mail_to_safe_to_delete():
    m = _reload()
    rules = [{"match": {"domain": "some-unknown-saas.io"}, "category": "Safe to Delete"}]
    out = m.classify_messages([_msg("Random <x@some-unknown-saas.io>", "Weekly update")],
                              config=CONFIG, rules=rules)
    assert out["items"][0]["category"] == "Safe to Delete"


# --- is_protected -------------------------------------------------------------

def test_is_protected_covers_all_four_signals():
    m = _reload()
    assert m.is_protected(_msg("x@natwest.com", "hello"), CONFIG)            # bank domain
    assert m.is_protected(_msg("x@foo.io", "Security alert"), CONFIG)        # security
    assert m.is_protected(_msg("x@richmond.gov.uk", "Annual canvass"), CONFIG)  # civic
    assert m.is_protected(_msg("x@foo.io", "your invoice"), CONFIG)          # financial ask
    assert m.is_protected(_msg("kevin@gmail.com", "hi"), CONFIG)             # real person
    assert not m.is_protected(_msg("news@foo.io", "Weekly update"), CONFIG)


# --- Sender ledger (Phase 4.6 §3) ----------------------------------------------

def _ledger():
    from gogos.gmail import gmail_ledger
    return {"fingerprint": gmail_ledger.config_fingerprint(), "senders": {}}


def test_no_sender_splits_two_ways_in_a_run():
    """The §3 acceptance test: subjects that would classify differently still
    land in one category per (non-protected) sender within a run."""
    m = _reload()
    msgs = [
        _msg("Notify <x@notify.foo.io>", "Susannah reacted to your reply", "id1"),  # -> Safe to Delete
        _msg("Notify <x@notify.foo.io>", "Weekly update", "id2"),                   # alone -> Newsletters
    ]
    out = m.classify_messages(msgs, config=CONFIG, ledger=_ledger())
    cats = {i["category"] for i in out["items"]}
    assert len(cats) == 1, f"sender split two ways in one run: {cats}"


def test_ledger_pins_sender_across_runs():
    m = _reload()
    ledger = _ledger()
    out1 = m.classify_messages(
        [_msg("Notify <x@notify.foo.io>", "Susannah reacted to your reply")],
        config=CONFIG, ledger=ledger)
    assert out1["items"][0]["category"] == "Safe to Delete"

    # Next run, same ledger: a subject that alone would be Newsletters follows the pin.
    out2 = m.classify_messages(
        [_msg("Notify <x@notify.foo.io>", "Weekly update")],
        config=CONFIG, ledger=ledger)
    item = out2["items"][0]
    assert item["category"] == "Safe to Delete"
    assert "ledger" in item["rationale"].lower()


def test_protected_mail_is_never_ledger_pinned():
    """A ledger entry can't drag a bank statement away from Action, and
    protected senders never enter the ledger at all."""
    m = _reload()
    ledger = _ledger()
    ledger["senders"]["natwest.com"] = {"category": "Information", "source": "builtin"}

    out = m.classify_messages(
        [_msg("NatWest <x@natwest.com>", "Your latest card statement is now available"),
         _msg("Kevin <kevin@gmail.com>", "Re: Saturday", "id2")],
        config=CONFIG, ledger=ledger)
    assert out["items"][0]["category"] == "Action"       # not the pinned Information
    assert out["items"][1]["category"] == "Review"
    assert "gmail.com" not in ledger["senders"]          # real person never ledgered


def test_user_rule_updates_ledger_deliberately():
    m = _reload()
    ledger = _ledger()
    ledger["senders"]["tldrnewsletter.com"] = {"category": "Newsletters", "source": "builtin"}
    m.classify_messages([_msg("TLDR <dan@tldrnewsletter.com>", "news")],
                        config=CONFIG, rules=RULES, ledger=ledger)
    entry = ledger["senders"]["tldrnewsletter.com"]
    assert entry["category"] == "Review"
    assert entry["source"] == "user-rule"


def test_relearn_recomputes_pins_and_logs(capsys):
    """Config change (relearn=True): prior pins are ignored, the fresh decision
    overwrites the entry, and the change is logged — never silent drift."""
    m = _reload()
    ledger = _ledger()
    ledger["senders"]["some-unknown-saas.io"] = {"category": "Safe to Delete", "source": "builtin"}

    out = m.classify_messages([_msg("Random <x@some-unknown-saas.io>", "Weekly update")],
                              config=CONFIG, ledger=ledger, relearn=True)
    assert out["items"][0]["category"] == "Newsletters"  # fresh builtin, not the pin
    assert ledger["senders"]["some-unknown-saas.io"]["category"] == "Newsletters"
    assert "re-learned" in capsys.readouterr().err


def test_relearn_run_still_keeps_one_category_per_sender():
    m = _reload()
    msgs = [
        _msg("Notify <x@notify.foo.io>", "Susannah reacted to your reply", "id1"),
        _msg("Notify <x@notify.foo.io>", "Weekly update", "id2"),
    ]
    out = m.classify_messages(msgs, config=CONFIG, ledger=_ledger(), relearn=True)
    assert len({i["category"] for i in out["items"]}) == 1


def test_no_ledger_no_rules_behaves_as_before():
    """Backwards compatibility: bare classify_messages is untouched."""
    m = _reload()
    out = m.classify_messages([_msg("TLDR <dan@tldrnewsletter.com>", "news")], config=CONFIG)
    item = out["items"][0]
    assert item["category"] == "Newsletters"
    assert item["confidence"] == 0.7
