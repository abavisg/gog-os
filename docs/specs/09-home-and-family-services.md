# Spec 9: Home and Family services

## Purpose

Light up the services that make the Home and Family rows useful with almost no new
intake: renewals fed by the classifier, occasions from people pages, a last-contact
index, meeting prep for personal meetings, and the workspace and trip templates.

## Scope

- Renewal candidates from the email classifier into `/process-inbox`.
- `occasions` from `people/` pages; `last-contact` script.
- `meeting-prep` skill (personal) and `/prep <person|event>`.
- `templates/workspace.md`, `templates/trip.md`, `templates/person.md`,
  `templates/provider.md`; `/new-workspace <slug> [--template trip]`.
- `life/wiki/home/documents/` conventions (no bodies, no numbers that are secrets).

## Non-scope

WhatsApp import (spec 11). Any automation that sends a message or buys anything.

## Design

### Renewals from the classifier

`gmail_classify` already matches renewal / expiry / statement language and bank,
insurer and utility senders. Add a pure function
`gogos/intake/gmail/renewals.py: candidates(slim, triage) -> list[dict]` returning
`{provider (sender domain), subject, date, expires (parsed from subject or snippet
when a date is present, else none), message_id}` for Action items whose rationale is
financial or civic and whose subject matches `renew|expir|due|statement|policy|MOT|
tax`. The digest writer adds a `## Renewal candidates` block; `register-update`
(spec 4) dedups against open `renewals` by provider and creates or updates items
(`auto_file` includes `renewal`). `expires: unknown` is valid and surfaces in the
brief as "date needed".

### Occasions and people

`life/wiki/people/<name>.md` front matter gains `birthday: MM-DD|none`,
`anniversaries: [{label, date}]`, `relationship: family|friend|colleague|provider|
other`, `area: family|work|none`. `gogos/core/occasions.py sync()` creates or
updates one `occasion` item per dated field with `recurrence: yearly` (idempotent by
`person + label`); `brief.py` already reads occasions within 14 days.

### Last contact

`.claude/scripts/last-contact.sh` → `python -m gogos.core.last_contact`: for each
people page, the latest date on which the person appears as a calendar attendee
(calendar slim JSON across stored dates) or as a sender / recipient (gmail slim
JSON, matching the page's `emails: []` field). Writes `last_contact` into the page
front matter and `life/wiki/people/_index.md` sorted by staleness. Deterministic, no
LLM. `/start-day` Schedule flags attendees whose page exists and whose
`last_contact` is older than 60 days ("first contact in 4 months").

### Meeting prep

`.claude/skills/meeting-prep/` adapted from ClientOS: inputs are a calendar event
(or a person), the people pages, related wiki pages, open `waiting` and
`commitments` involving the person, and the last three journal events mentioning
them. Output: objective, who and what they care about, what you owe them and they
owe you, talking points, questions. `/prep <event-id|person>` delegates to the
analyst; `/start-day` offers it for events with a known attendee. Work events are
bridged in spec 10; until then `/prep` works from GogOS memory only and says so.

### Templates and workspaces

`templates/workspace.md` (goal, why, material, working notes, open questions,
outputs, status log; ClientOS's shape with `area:`), `templates/trip.md` (dates,
travellers, bookings table, documents checklist with expiry cross-check against
`renewals`, people to see with `last_contact`, commitments falling in the window,
packing, "learned for next time" → wiki on archive), `templates/person.md`,
`templates/provider.md` (home providers: what, account reference *label* not
number, renewal link, contact). `/new-workspace <slug> [--template t] [--area a]`
scaffolds and journals `artefact.written`.

### Documents vault conventions

`life/wiki/home/documents/<class>.md` (passports, licences, insurance, car, house):
one page per class, a table of items with holder, issuer, `expires`, where the
original is kept, and a `renewal` item link. **No document numbers, no scans.** The
health check (L1) flags any 8+ digit run on these pages as advisory.

## Acceptance criteria

- [ ] A synthetic digest with "Your home insurance renews on 14 November" from an
      insurer domain yields a `renewal` with `expires: 2026-11-14`, `provider`, and
      `review_by` 60 days earlier; rerun updates, does not duplicate.
- [ ] A people page with `birthday: 11-02` yields one `occasion`; editing the date
      updates the same item.
- [ ] `last-contact` sets `last_contact` from a calendar fixture and a gmail fixture
      and sorts the index by staleness.
- [ ] `/prep <person>` cites the people page, open items, and journal events.
- [ ] `/new-workspace greece-2027 --template trip` scaffolds the trip file with the
      documents checklist cross-referencing open renewals.

## Tests

`tests/test_renewal_candidates.py`, `tests/test_occasions.py`,
`tests/test_last_contact.py`, `tests/test_new_workspace.py`.

## Open questions

- Should a renewal auto-create a `commitment` ("decide on renewal") at `review_by`,
  or is the brief's "Coming up" line enough? Spec says the line is enough for v1.
