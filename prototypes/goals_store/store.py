"""PROTOTYPE — throwaway; delete or absorb into gogos/goals/ when the question is answered.

QUESTION this prototype answers:
Are goals and commitments one entity or two? The bet made here: TWO —
a *goal* is declared and directional (kind: outcome | habit, no completion
date required), a *commitment* is a dated, checkable promise, optionally
linked to a goal. The model earns its keep only if it can feed all three
consumers of the real store without contortions:

  a) accountability loop -> due / overdue / ignored / course-correction suggestions
  b) attention engine    -> attention_context() (active goals + their open commitments)
  c) audit               -> every mutation appends to history[], nothing rewritten

Pure logic only: no I/O, no terminal codes, no persistence. State is a plain
dict so it maps 1:1 onto the append-only JSONL + latest-* convention later.
Timestamps are UTC ISO strings, per storage conventions.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

State = dict[str, Any]

GOAL_KINDS = ("outcome", "habit")
GOAL_STATUSES = ("active", "achieved", "paused", "dropped")
COMMITMENT_STATUSES = ("open", "kept", "missed", "dropped")


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s)


def empty_state() -> State:
    return {"goals": {}, "commitments": {}, "seq": {"g": 0, "c": 0}}


def _next_id(state: State, prefix: str) -> str:
    state["seq"][prefix] += 1
    return f"{prefix}{state['seq'][prefix]}"


def _hist(entity: dict, now: datetime, event: str, **fields: Any) -> None:
    entity["history"].append({"at": iso(now), "event": event, **fields})


# ── mutations ────────────────────────────────────────────────────────────────

def declare_goal(
    state: State,
    now: datetime,
    title: str,
    kind: str = "outcome",
    priority: int = 2,
    target_per_week: int | None = None,
) -> str:
    assert kind in GOAL_KINDS
    gid = _next_id(state, "g")
    goal = {
        "id": gid,
        "title": title,
        "kind": kind,
        "priority": priority,  # 1 = highest
        "target_per_week": target_per_week,
        "status": "active",
        "created_utc": iso(now),
        "history": [],
    }
    _hist(goal, now, "declared")
    state["goals"][gid] = goal
    return gid


def set_goal_status(state: State, now: datetime, gid: str, status: str) -> None:
    assert status in GOAL_STATUSES
    goal = state["goals"][gid]
    _hist(goal, now, "status", frm=goal["status"], to=status)
    goal["status"] = status


def add_commitment(
    state: State,
    now: datetime,
    title: str,
    due: datetime,
    goal_id: str | None = None,
) -> str:
    if goal_id is not None:
        assert goal_id in state["goals"], f"unknown goal {goal_id}"
    cid = _next_id(state, "c")
    c = {
        "id": cid,
        "title": title,
        "goal_id": goal_id,
        "due_utc": iso(due),
        "status": "open",
        "nudge_count": 0,
        "created_utc": iso(now),
        "history": [],
    }
    _hist(c, now, "committed", due=iso(due))
    state["commitments"][cid] = c
    return cid


def _set_commitment_status(state: State, now: datetime, cid: str, status: str) -> None:
    assert status in COMMITMENT_STATUSES
    c = state["commitments"][cid]
    _hist(c, now, "status", frm=c["status"], to=status)
    c["status"] = status


def keep(state: State, now: datetime, cid: str) -> None:
    _set_commitment_status(state, now, cid, "kept")


def miss(state: State, now: datetime, cid: str) -> None:
    _set_commitment_status(state, now, cid, "missed")


def drop_commitment(state: State, now: datetime, cid: str) -> None:
    _set_commitment_status(state, now, cid, "dropped")


def move(state: State, now: datetime, cid: str, new_due: datetime) -> None:
    """Reschedule: stays open; the move is history, moved_count is derived."""
    c = state["commitments"][cid]
    _hist(c, now, "moved", frm=c["due_utc"], to=iso(new_due))
    c["due_utc"] = iso(new_due)


def nudge(state: State, now: datetime, cid: str) -> None:
    """The accountability loop followed up on this commitment."""
    c = state["commitments"][cid]
    c["nudge_count"] += 1
    _hist(c, now, "nudged", count=c["nudge_count"])


# ── derived ──────────────────────────────────────────────────────────────────

def moved_count(c: dict) -> int:
    return sum(1 for h in c["history"] if h["event"] == "moved")


def open_commitments(state: State) -> list[dict]:
    return [c for c in state["commitments"].values() if c["status"] == "open"]


def kept_this_week(state: State, now: datetime, gid: str) -> int:
    """Commitments for this goal kept in the rolling last 7 days."""
    cutoff = now - timedelta(days=7)
    n = 0
    for c in state["commitments"].values():
        if c["goal_id"] != gid or c["status"] != "kept":
            continue
        kept_at = next(
            (h["at"] for h in reversed(c["history"]) if h.get("to") == "kept"), None
        )
        if kept_at and parse(kept_at) >= cutoff:
            n += 1
    return n


# ── accountability loop queries ──────────────────────────────────────────────

def due_within(state: State, now: datetime, hours: int = 24) -> list[dict]:
    horizon = now + timedelta(hours=hours)
    return sorted(
        (c for c in open_commitments(state) if now <= parse(c["due_utc"]) <= horizon),
        key=lambda c: c["due_utc"],
    )


def overdue(state: State, now: datetime) -> list[dict]:
    return sorted(
        (c for c in open_commitments(state) if parse(c["due_utc"]) < now),
        key=lambda c: c["due_utc"],
    )


def ignored(state: State, now: datetime, min_nudges: int = 2) -> list[dict]:
    """Overdue AND followed-up at least min_nudges times, still open."""
    return [c for c in overdue(state, now) if c["nudge_count"] >= min_nudges]


def suggestions(state: State, now: datetime) -> list[str]:
    """Course-correction candidates. Strings for now — the real system would
    emit structured proposals into the action pipeline."""
    out: list[str] = []
    for c in open_commitments(state):
        n_moved = moved_count(c)
        if n_moved >= 2:
            out.append(
                f"'{c['title']}' has been moved {n_moved}x — renegotiate: "
                f"shrink it or pick a slot that survives contact with your week."
            )
    for c in ignored(state, now):
        out.append(
            f"'{c['title']}' is overdue despite {c['nudge_count']} nudges — "
            f"drop it deliberately, or re-plan it?"
        )
    for c in state["commitments"].values():
        if c["status"] == "missed" and c["goal_id"]:
            g = state["goals"][c["goal_id"]]
            if g["status"] == "active":
                out.append(
                    f"'{c['title']}' was missed — reschedule it to keep "
                    f"'{g['title']}' moving?"
                )
    for g in state["goals"].values():
        if g["status"] != "active":
            continue
        open_for_goal = [c for c in open_commitments(state) if c["goal_id"] == g["id"]]
        if g["kind"] == "habit" and g["target_per_week"]:
            kept = kept_this_week(state, now, g["id"])
            if kept < g["target_per_week"] and len(open_for_goal) < (
                g["target_per_week"] - kept
            ):
                out.append(
                    f"habit '{g['title']}' at risk: {kept}/{g['target_per_week']} kept "
                    f"this week and only {len(open_for_goal)} session(s) scheduled."
                )
        elif not open_for_goal:
            out.append(
                f"goal '{g['title']}' has nothing scheduled — commit a next step."
            )
    return out


# ── attention engine projection ──────────────────────────────────────────────

def attention_context(state: State) -> list[dict]:
    """The slim, ranked context the attention engine reads to weigh incoming
    signals. This is the latest-* projection of the real store."""
    ctx = []
    for g in sorted(state["goals"].values(), key=lambda g: g["priority"]):
        if g["status"] != "active":
            continue
        ctx.append(
            {
                "goal": g["title"],
                "kind": g["kind"],
                "priority": g["priority"],
                "open": [
                    {"title": c["title"], "due_utc": c["due_utc"]}
                    for c in open_commitments(state)
                    if c["goal_id"] == g["id"]
                ],
            }
        )
    orphans = [
        {"title": c["title"], "due_utc": c["due_utc"]}
        for c in open_commitments(state)
        if c["goal_id"] is None
    ]
    if orphans:
        ctx.append({"goal": None, "kind": None, "priority": 99, "open": orphans})
    return ctx
