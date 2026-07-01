"""User classification rules — ordered overrides for gmail_classify (Phase 4.6 §2).

Rules live in `.core/config/gmail/rules.json` as an ordered list; each rule is
`{match, category}` where `match` targets the sender by exactly one of:
  domain     substring of the sender's domain (same semantics as classify.json)
  sender     substring of the full From field (case-insensitive)
  pattern    regex tested against the full From field

User rules are checked FIRST and win over built-in rules — with one absolute
exception enforced by the caller (gmail_classify): a user rule can never route
financial/security/civic/real-person mail into "Safe to Delete". Such a match
is refused, logged to stderr, and falls through to the next rule / built-ins.

No new folders or labels: `category` must be one of the existing six (a
`GSD/` prefix, as in the label names, is accepted and stripped). Invalid rules
are skipped with a warning, never silently.

Entry points:
  load_rules([path])           -> validated, ordered list of rules
  match_rule(message, rules)   -> (category, rationale) or None

This module is pure config/matching; it never touches the network or storage.
"""
from __future__ import annotations

import json
import re
import sys

from gogos.paths import REPO_ROOT

RULES_PATH = REPO_ROOT / ".core/config/gmail/rules.json"

VALID_CATEGORIES = {
    "Action", "Review", "Events", "Information", "Newsletters", "Safe to Delete",
}
_MATCH_KEYS = {"domain", "sender", "pattern"}


def _warn(msg: str) -> None:
    print(f"WARN  rules: {msg}", file=sys.stderr)


def _normalise_category(raw: str) -> str | None:
    """Accept 'GSD/Review' or 'Review'; return the bare category or None."""
    category = raw.removeprefix("GSD/").strip()
    return category if category in VALID_CATEGORIES else None


def _validate_rule(rule: dict, index: int) -> dict | None:
    """Return a cleaned rule or None (with a warning) if it is malformed."""
    match = rule.get("match")
    if not isinstance(match, dict) or set(match) - _MATCH_KEYS or len(match) != 1:
        _warn(f"rule {index}: 'match' must have exactly one of {sorted(_MATCH_KEYS)} — skipped")
        return None

    key, value = next(iter(match.items()))
    if not isinstance(value, str) or not value.strip():
        _warn(f"rule {index}: match.{key} must be a non-empty string — skipped")
        return None
    if key == "pattern":
        try:
            re.compile(value)
        except re.error as exc:
            _warn(f"rule {index}: invalid pattern {value!r} ({exc}) — skipped")
            return None

    category = _normalise_category(str(rule.get("category", "")))
    if category is None:
        _warn(f"rule {index}: category {rule.get('category')!r} is not one of "
              f"{sorted(VALID_CATEGORIES)} — skipped")
        return None

    return {"match": {key: value.strip()}, "category": category}


def load_rules(path=None) -> list[dict]:
    """Load and validate user rules. Missing file / no rules -> empty list."""
    path = RULES_PATH if path is None else path
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        _warn(f"cannot parse {path}: {exc} — ignoring user rules")
        return []

    raw_rules = data.get("rules", []) if isinstance(data, dict) else []
    rules = []
    for i, rule in enumerate(raw_rules):
        cleaned = _validate_rule(rule, i)
        if cleaned is not None:
            rules.append(cleaned)
    return rules


def _rule_matches(rule: dict, frm: str, domain: str) -> bool:
    key, value = next(iter(rule["match"].items()))
    if key == "domain":
        return value.lower() in domain
    if key == "sender":
        return value.lower() in frm.lower()
    return re.search(rule["match"]["pattern"], frm, re.I) is not None


def match_rule(message: dict, rules: list[dict],
               *, refuse: set[str] | None = None) -> tuple[str, str] | None:
    """First user rule matching the message -> (category, rationale), else None.

    `refuse` is the set of categories this message must not be routed to
    (the caller's safety cap). A matching rule with a refused category is
    logged and skipped — later rules and built-ins still apply.
    """
    from gogos.gmail.gmail_classify import _domain  # shared sender-domain parsing

    frm = message.get("from", "")
    domain = _domain(frm)
    refuse = refuse or set()

    for rule in rules:
        if not _rule_matches(rule, frm, domain):
            continue
        key, value = next(iter(rule["match"].items()))
        if rule["category"] in refuse:
            _warn(
                f"refused rule {key}={value!r} -> {rule['category']!r} for "
                f"protected mail from {frm!r} — never-delete invariant holds"
            )
            continue
        return rule["category"], f"User rule: {key} '{value}' → {rule['category']}."
    return None
