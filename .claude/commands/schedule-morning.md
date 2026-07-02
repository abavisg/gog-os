# /schedule-morning [HH:MM | off | status]

Implementation model: Sonnet (default — unpinned, tracks current Sonnet)

Purpose: manage the local launchd agent that runs the read-only morning email
triage automatically (Phase 4.6 §7). The scheduled run does reconcile → fetch →
normalise → classify → report per account, posts one macOS notification with
the counts, and **stops** — it never moves email and never opens a browser.
When you open Claude Code afterwards, the SessionStart nudge offers
`/start-day` with this morning's counts.

## Argument

- *(none)* or `HH:MM` — install (or reinstall) the agent; default time 08:00.
- `off` — uninstall the agent.
- `status` — show whether it is installed, loaded, and when it fires.

## Safety block

- The scheduled run is **read-only towards Gmail** — a test proves the module
  cannot reference the apply engine. Moves stay behind `/email-apply` /
  `/email-loop`.
- The agent fires only while the Mac is on; launchd runs a missed time once on
  wake and skips it if the machine was off.
- Installing writes only `~/Library/LaunchAgents/com.gogos.start-day.plist`
  and creates the log directory under `.core/storage/logs/scheduler/`.

## Steps

### install (default, optional HH:MM)

```
python -m gogos.system.scheduler install [--time HH:MM]
```

Report the output verbatim. On success, remind the user the run is read-only
and they can check it any time with `/schedule-morning status`.

### off

```
python -m gogos.system.scheduler uninstall
```

### status

```
python -m gogos.system.scheduler status
```

If the logs are mentioned and the user asks what happened this morning, read
`.core/storage/logs/scheduler/launchd.err.log` (stderr of the run) — never
print token or credential material.
