# Module Spec: CalendarOS

## Purpose

Generate today/tomorrow/week Google Calendar brief.

## Build model

Claude Sonnet 4.6.

## Inputs

- Google Calendar read-only OAuth token.
- Calendar settings.

## Outputs

- Raw event JSON.
- Normalised event JSON.
- Markdown/HTML calendar brief.

## Acceptance criteria

- Handles all-day events.
- Identifies conflicts and tight transitions.
- Handles empty calendar.
- No event creation in MVP.
