"""Deterministic email classifier — slim JSON -> triage JSON, no model, no network.

Replaces hand/script triage so the pipeline can run unattended (e.g. a scheduled
morning routine). Pure, ordered, first-match-wins rules. Output matches the
schema gmail_triage validates.

Safety invariant (enforced by rule ORDER, not by data):
  Anything financial, security-related, civic/legal, or from a real person is
  matched BEFORE the promo/newsletter rules, so it can never fall into
  "Safe to Delete". Tested in test_gmail_classify.

Entry points:
  classify_messages(messages)        -> triage dict (pure)
  classify(account[, slim_path])     -> exit code (I/O wrapper)

  python -m gogos.gmail.gmail_classify <account> [<slim_json_path>]
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.paths import REPO_ROOT, latest_alias, storage_path

_CONFIG_PATH = REPO_ROOT / ".core/config/gmail/classify.json"

# Subject/sender regexes (compiled once). These encode the high-priority,
# protect-from-deletion signals.
_SECURITY = re.compile(
    r"security alert|new login|new sign-?in|new sign in|password|verify your|"
    r"data exposure|dark web|payment.*(failed|unsuccessful)|"
    r"(failed|unsuccessful).*payment|confirm your .* payment|"
    r"update your .*payment|update .*payment method|payment method.*(expir|update)|"
    r"could not be processed|card expires|expir(ing|es) (soon|in)",
    re.I,
)
_CIVIC = re.compile(r"electoral|canvass|police|hmrc|council tax|jury", re.I)
_FINANCIAL = re.compile(
    r"\b(statement|bill|invoice|receipt|payment|premium|renew|renewal|overdue|"
    r"tax certificate|consolidated tax|ebill|direct debit)\b"
    r"|λογαριασμ|πληρωμ|ασφαλιστ",
    re.I,
)
_INVITE = re.compile(r"invitation:|@ (mon|tue|wed|thu|fri|sat|sun|\d)", re.I)
_EVENT_CONFIRM = re.compile(
    r"booking (is )?confirmed|your booking|appointment|reservation|"
    r"eye test|cancelled:|order confirmation",
    re.I,
)
_SOCIAL = re.compile(
    r"reacted to|commented on|new comment|just messaged you on|liked your|"
    r"shared video|opened your|new follower",
    re.I,
)
_ORDER = re.compile(
    r"order|delivery|dispatch|shipped|payout|tracking|boarding|check-?in|itinerary",
    re.I,
)

_SUGGESTED = {
    "Action": "Review / pay / verify",
    "Events": "Add to calendar / note",
    "Review": "Review",
    "Information": "Keep as record",
    "Newsletters": "Read or skim",
    "Safe to Delete": "Ignore",
}


def _load_config() -> dict:
    """Load sender lists. Returns empty lists if the config file is absent."""
    if not _CONFIG_PATH.exists():
        return {k: [] for k in (
            "bank_domains", "newsletter_domains", "promo_domains",
            "info_domains", "event_domains", "personal_patterns",
        )}
    return json.loads(_CONFIG_PATH.read_text())


def _domain(from_field: str) -> str:
    if "@" not in from_field:
        return from_field.lower()
    return from_field.split("@")[-1].rstrip(">").strip().lower()


def _matches(domain: str, needles: list[str]) -> bool:
    return any(n in domain for n in needles)


def classify_one(message: dict, config: dict) -> tuple[str, str]:
    """Classify a single normalised message -> (category, rationale).

    Ordered, first-match-wins. High-priority/protected rules come first so that
    financial, security, civic, and real-person mail can never reach Safe to
    Delete.
    """
    frm = message.get("from", "")
    subject = message.get("subject", "") or ""
    domain = _domain(frm)

    banks = config.get("bank_domains", [])
    newsletters = config.get("newsletter_domains", [])
    promos = config.get("promo_domains", [])
    infos = config.get("info_domains", [])
    events = config.get("event_domains", [])
    people = config.get("personal_patterns", [])

    # 1. Calendar invitations / bookings -> Events
    if (_INVITE.search(subject) or _EVENT_CONFIRM.search(subject)) and "lottery" not in domain:
        return "Events", "Calendar invitation / booking / appointment."

    # 2. Security / account-safety -> Action (verify)
    if _SECURITY.search(subject):
        return "Action", "Security / account-safety alert — verify."

    # 3. Civic / legal -> Action
    if _CIVIC.search(subject) or _CIVIC.search(frm):
        return "Action", "Civic / legal — may require response."

    # 4. Known banks / insurers / utilities
    if _matches(domain, banks):
        if _FINANCIAL.search(subject):
            return "Action", "Financial: statement/bill/payment/renewal — review or pay."
        return "Information", "Financial institution notice — record."

    # 5. Real people -> Review
    if any(p in frm.lower() for p in people):
        return "Review", "Message from a real person — read; reply if needed."

    # 6. Social / notification noise -> Safe to Delete
    if _SOCIAL.search(subject):
        return "Safe to Delete", "Social / notification noise."

    # 7. LinkedIn -> Review (never deleted; may be a real message)
    if "linkedin.com" in domain:
        return "Review", "LinkedIn job alert or message — review if job-seeking."

    # 8. Event-platform invites -> Events
    if _matches(domain, events):
        return "Events", "Event invitation."

    # 9. Order / shipping / travel notices -> Information
    if _ORDER.search(subject):
        return "Information", "Order / shipping / travel notice — record."

    # 10. Genuine financial language -> Action. Excludes newsletters (digests
    # mention "payment"/"renewal" as topics, not as a real ask) but NOT promo
    # domains: a real "statement ready" / "update payment method" from a
    # promo-ish sender is still an account action, not deletable.
    if _FINANCIAL.search(subject) and not _matches(domain, newsletters):
        return "Action", "Payment/renewal/statement language — review."

    # 11. Promo / marketing -> Safe to Delete
    if _matches(domain, promos):
        return "Safe to Delete", "Promotional / marketing."

    # 12. Info-platform notices (dev tools, orders, scores, Google) -> Information
    if _matches(domain, infos):
        return "Information", "Service / platform notice — record."

    # 13. Newsletter domains -> Newsletters
    if _matches(domain, newsletters):
        return "Newsletters", "Subscribed newsletter / digest."

    # 14. Default: long-tail automated mail. Everything important was caught
    # above, so the remainder is overwhelmingly promo/newsletter — route to
    # Newsletters (skim; reversible), never delete by default.
    return "Newsletters", "Long-tail automated mail — skim."


def classify_messages(messages: list[dict], config: dict | None = None,
                      account: str = "") -> dict:
    """Pure function: list of normalised messages -> triage dict."""
    if config is None:
        config = _load_config()
    items = []
    for m in messages:
        category, rationale = classify_one(m, config)
        items.append({
            "id": m.get("id", ""),
            "category": category,
            "confidence": 0.7,
            "rationale": rationale,
            "suggested_action": _SUGGESTED[category],
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "items": items,
    }


def classify(account: str, slim_path: Path | None = None) -> int:
    """I/O wrapper: read latest slim JSON, classify, write triage JSON. Exit code."""
    account = resolve_account(account)

    if slim_path is None:
        slim_path = latest_alias(storage_path("gmail", account, "inbox"), "latest-slim.json")
    try:
        slim = json.loads(slim_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read slim file {slim_path}: {exc}", file=sys.stderr)
        return 1

    triage = classify_messages(slim.get("messages", []), account=account)

    dated_dir = storage_path("gmail", account, "triage")
    (dated_dir / "triage.json").write_text(json.dumps(triage, indent=2))
    alias = latest_alias(dated_dir, "latest-triage.json")
    alias.write_text(json.dumps(triage, indent=2))

    print(f"OK  Classified {len(triage['items'])} message(s) to {alias}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python -m gogos.gmail.gmail_classify <account> [slim_json_path]",
            file=sys.stderr,
        )
        sys.exit(1)
    _slim = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    sys.exit(classify(sys.argv[1], _slim))
