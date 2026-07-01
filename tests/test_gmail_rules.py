"""Tests for gogos.gmail.gmail_rules — pure config parsing and matching."""
from __future__ import annotations

import json

from gogos.gmail import gmail_rules


def _msg(frm, subject="hello"):
    return {"id": "m1", "from": frm, "subject": subject}


def _write_rules(tmp_path, rules):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": rules}))
    return path


# --- load_rules ---------------------------------------------------------------

def test_missing_file_means_no_rules(tmp_path):
    assert gmail_rules.load_rules(tmp_path / "absent.json") == []


def test_invalid_json_is_ignored_with_warning(tmp_path, capsys):
    path = tmp_path / "rules.json"
    path.write_text("{not json")
    assert gmail_rules.load_rules(path) == []
    assert "WARN" in capsys.readouterr().err


def test_valid_rules_load_in_order(tmp_path):
    path = _write_rules(tmp_path, [
        {"match": {"domain": "linkedin.com"}, "category": "Review"},
        {"match": {"sender": "LinkedIn Jobs"}, "category": "Newsletters"},
        {"match": {"pattern": r"jobs-noreply@.*"}, "category": "Information"},
    ])
    rules = gmail_rules.load_rules(path)
    assert [r["category"] for r in rules] == ["Review", "Newsletters", "Information"]


def test_gsd_prefix_is_stripped(tmp_path):
    path = _write_rules(tmp_path, [{"match": {"domain": "x.com"}, "category": "GSD/Review"}])
    assert gmail_rules.load_rules(path)[0]["category"] == "Review"


def test_bad_rules_are_skipped_with_warning(tmp_path, capsys):
    path = _write_rules(tmp_path, [
        {"match": {"domain": "x.com"}, "category": "NotACategory"},   # bad category
        {"match": {"domain": "a.com", "sender": "b"}, "category": "Review"},  # two keys
        {"match": {"realm": "a.com"}, "category": "Review"},          # unknown key
        {"match": {"pattern": "("}, "category": "Review"},            # bad regex
        {"match": {"domain": ""}, "category": "Review"},              # empty value
        {"match": {"domain": "good.com"}, "category": "Review"},      # the only good one
    ])
    rules = gmail_rules.load_rules(path)
    assert len(rules) == 1
    assert rules[0]["match"] == {"domain": "good.com"}
    assert capsys.readouterr().err.count("WARN") == 5


# --- match_rule ---------------------------------------------------------------

RULES = [
    {"match": {"sender": "linkedin jobs"}, "category": "Newsletters"},
    {"match": {"domain": "linkedin.com"}, "category": "Review"},
    {"match": {"pattern": r"noreply@.*\.example\.org"}, "category": "Information"},
]


def test_first_matching_rule_wins():
    cat, rationale = gmail_rules.match_rule(
        _msg("LinkedIn Jobs <jobs@linkedin.com>"), RULES)
    assert cat == "Newsletters"          # sender rule listed before domain rule
    assert "User rule" in rationale


def test_domain_rule_matches_substring_of_domain():
    cat, _ = gmail_rules.match_rule(_msg("LinkedIn <x@mail.linkedin.com>"), RULES)
    assert cat == "Review"


def test_pattern_rule_matches_from_field():
    cat, _ = gmail_rules.match_rule(_msg("Sys <noreply@app.example.org>"), RULES)
    assert cat == "Information"


def test_no_rule_matches_returns_none():
    assert gmail_rules.match_rule(_msg("someone@nowhere.net"), RULES) is None


def test_refused_category_is_skipped_and_logged(capsys):
    """A rule whose category is in `refuse` is skipped; later rules still apply."""
    rules = [
        {"match": {"domain": "linkedin.com"}, "category": "Safe to Delete"},
        {"match": {"domain": "linkedin.com"}, "category": "Review"},
    ]
    cat, _ = gmail_rules.match_rule(
        _msg("x@linkedin.com"), rules, refuse={"Safe to Delete"})
    assert cat == "Review"
    assert "refused" in capsys.readouterr().err
