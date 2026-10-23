# Spec 10: the ClientOS bridge (deferred; open questions)

## Purpose

Let GogOS plan the owner's day across everything, including work handled in one or
more ClientOS instances, without moving the client's knowledge out of those
instances. Decided so far (proposal §10 and §12): ClientOS owns the client's facts;
GogOS owns the owner's obligations; titles may be kept in GogOS; the design is the
last slice.

## Boundary (decided)

| Stays in `<slug>-os/client/` | May enter GogOS |
|---|---|
| people, business, product, technology facts; transcripts; registers' bodies | a reference (instance slug, path, id) |
| | a one-line title of an action, meeting or decision |
| | dates: due, meeting time, review_by |
| | counts |

Anything GogOS keeps is in `life/journal/` or `life/registers/` (tracked). The
digest itself is in `life/inbox/` (gitignored) and deleted after processing.

## Sketch

`gogos/intake/clientos/fetch.py`: reads, read-only, from each instance listed in
`.core/config/clientos.json` (`[{"slug":"acme","path":"~/acme-os"}]`):

- open actions owned by the owner, from `client/capture/meetings/*.md` checkbox
  lines matching the owner's name;
- today's and tomorrow's events already in GogOS's calendar (no need to read
  ClientOS for these; the bridge only adds the prep flag "ClientOS context exists");
- `client/registers/decisions/` items awaiting the owner (`outcome: pending`, past
  `review_by`) by title and path;
- `client/NEXT.md` top items if present.

Writes `life/inbox/clientos-<slug>-<date>.md`. `/process-inbox` turns owner-owned
actions into `commitments` (area `work`, `source` the instance path) **only for
items the owner confirms** in the Asks list; nothing from ClientOS is auto-filed.
`/start-day` shows them under Work with "open in `<slug>-os`". `/prep` for a work
event says "context in `<slug>-os`; run `/prep-for-meeting` there".

## Open questions (to settle before building)

1. **Direction of truth for a work commitment.** If the owner marks it kept in GogOS,
   should the bridge write the checkbox in the ClientOS meeting note? Writing into
   another repo's `client/` from GogOS crosses a boundary ClientOS guards; the
   alternative is that ClientOS stays the record for work actions and GogOS keeps a
   mirror that can go stale. Proposed: no writes; the weekly review lists mirrors
   that disagree.
2. **Which ClientOS version does the bridge read?** It depends on file shapes
   (`capture/meetings/` checkbox lines, `registers/decisions/` front matter). Pin the
   minimum ClientOS version in `clientos.json` and fail loudly on a shape change,
   like the `gog` connectors do.
3. **Multiple instances and FractionalOS.** When the fractional practice gets its
   own system, the bridge reads it the same way; the config is a list for that
   reason. Should pipeline items (prospects) ever enter GogOS? Proposed: counts only.
4. **Reading another repo's gitignored data from a cloud session.** The bridge is
   local-only by construction (it reads `~/…-os/client/`), so it never runs in a
   cloud session. Document that.
5. **The title boundary in practice.** A title like "Reply to <CEO name> re
   fundraising" is a client fact in miniature. Proposed: the bridge keeps titles as
   written (decided), and the LIFE health check flags titles containing a name from
   the instance's people pages as advisory so the owner can shorten them.

## Acceptance criteria (draft)

- [ ] With a synthetic `~/acme-os/client/` fixture, the bridge writes a digest with
      three owner-owned actions, one pending decision, and no body text.
- [ ] `/process-inbox` lists them as asks; confirming one creates a `commitment`
      with `source` pointing into the instance.
- [ ] `/start-day` Work section shows the commitment with "open in acme-os".
- [ ] A fixture whose meeting-note shape changed fails the bridge loudly.
