"""registers.derived(): the rules carried from the goals prototype.

- an outcome goal with no open commitment is "idle";
- a habit goal is "at risk" in a week when kept_this_week < target_per_week and
  open_commitments_this_week < target_per_week - kept_this_week;
- a commitment moved twice or more is a "renegotiate" candidate;
- a waiting item nudged twice and still open is "ignored" (and, as in the
  prototype, so is an overdue commitment nudged twice).

The week is the ISO week (Monday to Sunday) containing today. 2026-10-23 is a
Friday, so the week runs 2026-10-19 to 2026-10-25.
"""
from __future__ import annotations

from gogos.core import registers

TODAY = "2026-10-23"


def _d(path):
    item = registers.load_item(path)
    return registers.derived(item, registers.load(), today=TODAY)


# --- renegotiate / moved_count ------------------------------------------------

def test_moved_twice_is_renegotiate(life, clock):
    clock("2026-10-20T08:00:00Z")
    path = registers.create("commitment", "Fix gate", "home", due="2026-10-21")
    registers.set_field(path, "due", "2026-10-22")
    assert _d(path)["moved_count"] == 1 and _d(path)["renegotiate"] is False
    registers.set_field(path, "due", "2026-10-26")
    assert _d(path)["moved_count"] == 2 and _d(path)["renegotiate"] is True


def test_closed_commitment_is_not_renegotiate(life, clock):
    clock("2026-10-20T08:00:00Z")
    path = registers.create("commitment", "Fix gate", "home", due="2026-10-21")
    registers.set_field(path, "due", "2026-10-22")
    registers.set_field(path, "due", "2026-10-23")
    registers.set_status(path, "kept")
    d = _d(path)
    assert d["moved_count"] == 2 and d["renegotiate"] is False


def test_other_field_changes_are_not_moves(life, clock):
    clock("2026-10-20T08:00:00Z")
    path = registers.create("commitment", "Fix gate", "home", due="2026-10-21")
    registers.set_field(path, "title", "Fix the gate")
    registers.set_field(path, "area", "family")
    assert _d(path)["moved_count"] == 0


# --- days_overdue ---------------------------------------------------------------

def test_days_overdue(life, clock):
    clock("2026-10-20T08:00:00Z")
    late = registers.create("commitment", "Late", "home", due="2026-10-20T09:00")
    today = registers.create("commitment", "Today", "home", due=TODAY)
    kept = registers.create("commitment", "Kept", "home", due="2026-10-19")
    registers.set_status(kept, "kept")
    waiting = registers.create("waiting", "Reply", "work", owed_by="Sam",
                               asked_on="2026-10-10")
    assert _d(late)["days_overdue"] == 3
    assert _d(today)["days_overdue"] == 0
    assert _d(kept)["days_overdue"] == 0
    assert _d(waiting)["days_overdue"] == 6  # review_by = asked_on + 7


def test_no_date_means_no_overdue(life, clock):
    clock("2026-10-20T08:00:00Z")
    goal = registers.create("goal", "Read", "growth")
    assert _d(goal)["days_overdue"] is None


# --- ignored --------------------------------------------------------------------

def test_waiting_nudged_twice_and_open_is_ignored(life, clock):
    clock("2026-10-20T08:00:00Z")
    path = registers.create("waiting", "Deposit back", "home", owed_by="Landlord",
                            asked_on="2026-10-20")
    registers.nudge(path)
    assert _d(path)["ignored"] is False
    registers.nudge(path)
    assert _d(path)["ignored"] is True
    registers.set_status(path, "received")
    assert _d(path)["ignored"] is False


def test_commitment_ignored_only_when_overdue_and_nudged_twice(life, clock):
    clock("2026-10-20T08:00:00Z")
    late = registers.create("commitment", "Late", "home", due="2026-10-21")
    ahead = registers.create("commitment", "Ahead", "home", due="2026-10-30")
    for p in (late, ahead):
        registers.nudge(p)
        registers.nudge(p)
    assert _d(late)["ignored"] is True
    assert _d(ahead)["ignored"] is False


# --- idle -------------------------------------------------------------------------

def test_outcome_goal_without_open_commitment_is_idle(life, clock):
    clock("2026-10-20T08:00:00Z")
    goal = registers.create("goal", "Sort the loft", "home")
    assert _d(goal)["idle"] is True
    c = registers.create("commitment", "Book skip", "home", due="2026-10-24",
                         goal="sort-the-loft")
    assert _d(goal)["idle"] is False
    registers.set_status(c, "kept")
    assert _d(goal)["idle"] is True


def test_idle_does_not_apply_to_habits_or_inactive_goals(life, clock):
    clock("2026-10-20T08:00:00Z")
    habit = registers.create("goal", "Run", "wellness", kind="habit", target_per_week=3)
    paused = registers.create("goal", "Paint", "home")
    registers.set_status(paused, "paused")
    assert _d(habit)["idle"] is False
    assert _d(paused)["idle"] is False


# --- at_risk ----------------------------------------------------------------------

def _habit_with(clock, kept_at: list[str], open_due: list[str]):
    clock("2026-10-12T08:00:00Z")
    goal = registers.create("goal", "Train", "wellness", kind="habit", target_per_week=3)
    for i, ts in enumerate(kept_at):
        clock("2026-10-12T08:00:00Z")
        c = registers.create("commitment", f"Session k{i}", "wellness",
                             due=ts[:10], goal="train")
        clock(ts)
        registers.set_status(c, "kept")
    clock("2026-10-12T08:00:00Z")
    for i, due in enumerate(open_due):
        registers.create("commitment", f"Session o{i}", "wellness", due=due, goal="train")
    return goal


def test_habit_two_kept_one_scheduled_is_not_at_risk(life, clock):
    goal = _habit_with(clock, ["2026-10-20T07:00:00Z", "2026-10-22T07:00:00Z"], ["2026-10-24"])
    assert _d(goal)["at_risk"] is False


def test_habit_two_kept_none_scheduled_is_at_risk(life, clock):
    goal = _habit_with(clock, ["2026-10-20T07:00:00Z", "2026-10-22T07:00:00Z"], [])
    assert _d(goal)["at_risk"] is True


def test_habit_target_met_is_not_at_risk(life, clock):
    goal = _habit_with(clock, ["2026-10-19T07:00:00Z", "2026-10-20T07:00:00Z",
                               "2026-10-21T07:00:00Z"], [])
    assert _d(goal)["at_risk"] is False


def test_kept_last_week_and_scheduled_next_week_do_not_count(life, clock):
    goal = _habit_with(clock, ["2026-10-18T07:00:00Z", "2026-10-20T07:00:00Z"],
                       ["2026-10-24", "2026-10-26"])
    # kept this week: 1 (the 18th is last week); open this week: 1 (the 26th is next).
    # 1 < 3 and 1 < 3 - 1, so at risk.
    assert _d(goal)["at_risk"] is True


def test_habit_without_target_is_never_at_risk(life, clock):
    clock("2026-10-20T08:00:00Z")
    goal = registers.create("goal", "Stretch", "wellness", kind="habit")
    assert _d(goal)["at_risk"] is False


def test_derived_keys_are_uniform_across_kinds(life, clock):
    clock("2026-10-20T08:00:00Z")
    path = registers.create("parked", "Pool heater", "home", revisit_by="2027-04-01")
    assert set(_d(path)) == {"moved_count", "days_overdue", "renegotiate",
                             "ignored", "idle", "at_risk"}
