#!/usr/bin/env python
"""PROTOTYPE — throwaway TUI shell over store.py; the logic module is the keeper.

Run:  .venv/bin/python prototypes/goals_store/tui.py

Drive the goals & commitments model by hand. The clock is SIMULATED — tick it
forward and watch what the accountability loop would say each morning.
"""
from __future__ import annotations

import sys
import termios
import tty
from datetime import datetime, timedelta, timezone

import store

B, D, R = "\x1b[1m", "\x1b[2m", "\x1b[0m"
RED, GRN, YEL = "\x1b[31m", "\x1b[32m", "\x1b[33m"

STATUS_MARK = {
    "open": f"{YEL}●{R}",
    "kept": f"{GRN}✔{R}",
    "missed": f"{RED}✘{R}",
    "dropped": f"{D}∅{R}",
    "active": f"{GRN}▶{R}",
    "achieved": f"{GRN}★{R}",
    "paused": f"{YEL}⏸{R}",
}


def getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {B}{label}{suffix}:{R} ").strip()
    return val or default


def rel(due_iso: str, now: datetime) -> str:
    delta = store.parse(due_iso) - now
    hours = delta.total_seconds() / 3600
    if hours < 0:
        h = -hours
        txt = f"{h/24:.0f}d overdue" if h >= 24 else f"{h:.0f}h overdue"
        return f"{RED}{txt}{R}"
    txt = f"in {hours/24:.0f}d" if hours >= 24 else f"in {hours:.0f}h"
    return f"{GRN}{txt}{R}"


def render(state: store.State, now: datetime, msg: str) -> None:
    print("\033[2J\033[H", end="")
    local = now.astimezone()
    print(f"{B}GOALS STORE PROTOTYPE{R}   {D}simulated now:{R} {B}{local:%a %d %b %H:%M}{R}")
    if msg:
        print(f"  {YEL}{msg}{R}")

    print(f"\n{B}GOALS{R}")
    for g in state["goals"].values():
        habit = ""
        if g["kind"] == "habit" and g["target_per_week"]:
            habit = f"  {D}{store.kept_this_week(state, now, g['id'])}/{g['target_per_week']} this wk{R}"
        print(
            f"  {D}[{g['id']}]{R} {STATUS_MARK[g['status']]} "
            f"{D}P{g['priority']} {g['kind']:<7}{R} {g['title']}{habit}"
        )

    print(f"\n{B}COMMITMENTS{R}")
    for c in state["commitments"].values():
        link = f"{D}({c['goal_id']}){R}" if c["goal_id"] else f"{D}(—){R}"
        flags = f"{D}moved:{store.moved_count(c)} nudged:{c['nudge_count']}{R}"
        due = rel(c["due_utc"], now) if c["status"] == "open" else f"{D}{c['status']}{R}"
        print(
            f"  {D}[{c['id']}]{R} {STATUS_MARK[c['status']]} {due:<24} "
            f"{link} {c['title']}  {flags}"
        )

    print(f"\n{B}── ACCOUNTABILITY LOOP (what the morning panel would say) ──{R}")
    due = store.due_within(state, now)
    print(f"  {B}due ≤24h:{R} " + (", ".join(c["title"] for c in due) or f"{D}none{R}"))
    over = store.overdue(state, now)
    print(f"  {B}overdue:{R}  " + (", ".join(c["title"] for c in over) or f"{D}none{R}"))
    ign = store.ignored(state, now)
    print(f"  {B}ignored:{R}  " + (", ".join(c["title"] for c in ign) or f"{D}none{R}"))
    print(f"  {B}suggested course corrections:{R}")
    for s in store.suggestions(state, now) or []:
        print(f"    {YEL}→{R} {s}")
    if not store.suggestions(state, now):
        print(f"    {D}none{R}")

    print(f"\n{B}── ATTENTION CONTEXT (what the ranking skill receives) ──{R}")
    for entry in store.attention_context(state):
        goal = entry["goal"] or "(no goal)"
        opens = ", ".join(o["title"] for o in entry["open"]) or "nothing open"
        print(f"  {D}P{entry['priority']}{R} {B}{goal}{R} {D}→{R} {opens}")

    print(
        f"\n{D}[g]{R} goal  {D}[c]{R} commit  {D}[k]{R} keep  {D}[m]{R} miss  "
        f"{D}[v]{R} move  {D}[n]{R} nudge  {D}[d]{R} drop  {D}[G]{R} goal status  "
        f"{D}[t]{R} +6h  {D}[T]{R} +1d  {D}[q]{R} quit"
    )


def seed(now: datetime) -> store.State:
    """Seed through the real mutation API with back-dated timestamps."""
    s = store.empty_state()
    t0 = now - timedelta(days=3)

    g1 = store.declare_goal(s, t0, "Close the Acme deal", "outcome", priority=1)
    store.add_commitment(s, now, "Reply to Acme proposal email", now + timedelta(hours=8), g1)

    g2 = store.declare_goal(s, t0, "Train 3x/week", "habit", priority=2, target_per_week=3)
    c_done = store.add_commitment(s, t0, "Gym session (Mon)", t0 + timedelta(days=1), g2)
    store.keep(s, now - timedelta(days=1), c_done)
    store.add_commitment(s, now, "Gym session (Thu)", now + timedelta(hours=26), g2)

    g3 = store.declare_goal(s, t0, "Life admin under control", "outcome", priority=3)
    c_ins = store.add_commitment(s, t0, "Renew car insurance", t0 + timedelta(days=1), g3)
    store.move(s, t0 + timedelta(days=1), c_ins, t0 + timedelta(days=2))
    store.move(s, t0 + timedelta(days=2), c_ins, now - timedelta(days=1))
    store.nudge(s, now - timedelta(hours=20), c_ins)
    store.nudge(s, now - timedelta(hours=4), c_ins)

    store.add_commitment(s, now, "Book dentist appointment", now + timedelta(days=3))
    return s


def main() -> None:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    state = seed(now)
    msg = "seeded: 3 goals, 5 commitments (c4 is already in trouble — watch the loop react)"

    while True:
        render(state, now, msg)
        msg = ""
        key = getch()
        try:
            if key == "q":
                print()
                return
            elif key == "t":
                now += timedelta(hours=6)
            elif key == "T":
                now += timedelta(days=1)
            elif key == "g":
                print()
                title = ask("goal title")
                kind = ask("kind (outcome/habit)", "outcome")
                prio = int(ask("priority 1-3", "2"))
                tpw = ask("target per week (habits only)", "")
                store.declare_goal(state, now, title, kind, prio, int(tpw) if tpw else None)
            elif key == "c":
                print()
                title = ask("commitment title")
                gid = ask("goal id (blank = none)", "") or None
                days = float(ask("due in how many days", "1"))
                store.add_commitment(state, now, title, now + timedelta(days=days), gid)
            elif key in "kmvnd":
                print()
                cid = ask("commitment id")
                if key == "k":
                    store.keep(state, now, cid)
                elif key == "m":
                    store.miss(state, now, cid)
                elif key == "n":
                    store.nudge(state, now, cid)
                elif key == "d":
                    store.drop_commitment(state, now, cid)
                elif key == "v":
                    days = float(ask("move to how many days from now", "1"))
                    store.move(state, now, cid, now + timedelta(days=days))
            elif key == "G":
                print()
                gid = ask("goal id")
                status = ask("status (active/achieved/paused/dropped)")
                store.set_goal_status(state, now, gid, status)
        except (KeyError, AssertionError, ValueError) as e:
            msg = f"!! {e}"


if __name__ == "__main__":
    main()
