# Email Triage Rubric

Classify from sender, subject, date, labels, and snippet only unless full-body mode is explicitly requested.

## Rules

- Prefer Action when the email asks Giorgos to do something.
- Prefer Events for invitations, bookings, appointments, travel, tickets, or schedule changes.
- Prefer Review when the email may matter but action is unclear.
- Prefer Information when it is useful but passive.
- Prefer Newsletters for repeat publication/digest/subscription content.
- Use Safe to Delete conservatively. Never mark legal, financial, client, family, school, health, banking, tax, or contract messages as Safe to Delete from metadata alone.

## Output requirement

Return structured JSON with message id, category, confidence, rationale, and suggested action.
