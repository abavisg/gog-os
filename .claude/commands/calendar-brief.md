# /calendar-brief [account] [today|tomorrow|week]

Model: Claude Sonnet 4.6

Purpose: generate a calendar operating brief.

Steps:

1. Fetch Google Calendar events for requested period.
2. Store raw and normalised events.
3. Invoke calendar-brief skill.
4. Generate Markdown and HTML brief.

Output sections:

- Schedule overview.
- Conflicts.
- Preparation needed.
- Follow-ups.
- Focus gaps.
