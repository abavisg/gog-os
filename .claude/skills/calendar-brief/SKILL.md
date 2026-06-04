---
name: calendar-brief
description: Turns normalised calendar events into a daily or weekly operating brief.
model: claude-sonnet-4-6
---

# Calendar Brief Skill

## Inputs

- Normalised event JSON.
- Requested period.
- Working hours config.

## Output sections

- Schedule overview.
- Important meetings.
- Conflicts or tight transitions.
- Prep required.
- Follow-up opportunities.
- Focus gaps.

## Rules

- Do not invent meeting context beyond title, attendees, location, and description presence.
- Call out uncertainty.
- Treat all-day events separately.
