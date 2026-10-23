# GogOS v2 specs

One spec per build slice from `docs/REARCHITECTURE-PROPOSAL.md` §11. A spec is
buildable when someone can start it without asking a question that the spec should
have answered. Each has the same shape: purpose, scope and non-scope, design,
acceptance criteria, tests, open questions.

| # | Spec | Depends on | Size |
|---|---|---|---|
| 1 | [Defects and CI](01-defects-and-ci.md) | none | half a day |
| 2 | [Memory substrate](02-memory-substrate.md) | none | 2 to 3 days |
| 3 | [Intake via gog](03-intake-via-gog.md) | 2 (inbox path) | 2 to 3 days |
| 4 | [Intelligence core](04-intelligence-core.md) | 2, 3 | 2 days |
| 5 | [Daily loop](05-daily-loop.md) | 2, 3, 4 | 2 to 3 days |
| 6 | [Wellness](06-wellness.md) | 2, 5 | 1 day |
| 7 | [Council](07-council.md) | 2, 4 | 1 to 2 days |
| 8 | [Governance](08-governance.md) | 2 | 1 to 2 days |
| 9 | [Home and Family services](09-home-and-family-services.md) | 3, 4, 5 | 2 days |
| 10 | [ClientOS bridge](10-clientos-bridge.md) | 5 | deferred; spec is open questions |
| 11 | [Further intake](11-further-intake.md) | per source | placeholder |

Slices 1 and 2 can start in parallel. 8 can slot anywhere after 2 and is worth
doing early because its health check catches drift in every later slice.

## Conventions every slice follows

- **One `today()`.** `gogos.core.paths.today()` returns the local date in
  `GOGOS_TIMEZONE`; every dated path, approval directory and journal file uses it.
  Event timestamps are UTC ISO 8601.
- **No LLM in Intake.** Connectors, indexers and assemblers are Python, deterministic,
  tested with pytest. Anything that needs judgement is a skill invoked by an agent or
  a command.
- **Front matter on content files** under `life/` and `me/`, using the schemas in
  spec 2. `.claude/` files use Claude Code's native schema. Docs are plain markdown.
- **Append, do not rewrite.** Journal files are append-only. Register items keep a
  `## History` section. Finalised reports are amended, never edited.
- **Cite sources.** Every artefact lists the paths it was built from.
- **Decoupling.** Nothing under `gogos/`, `.claude/`, `docs/` names a person, an
  account, an area's content, or a client. Fixtures are synthetic.
- **Writing.** No em-dashes in files the owner will read or publish; recast the
  sentence instead.
- **Definition of done for a slice:** tests green (`pytest` and, from slice 8,
  `run-tests.sh`), health check passes, the spec's acceptance criteria are ticked in
  the PR description, and `docs/IMPLEMENTATION_PLAN.md` moves the slice to DONE.

## Shared vocabulary

| Term | Meaning |
|---|---|
| Area | One of `wellness`, `finance`, `growth`, `family`, `home`, `work`. A tag, and a wiki section. |
| Service | An executive-assistant capability that applies to every area: commitments, waiting-on, renewals, occasions, prep, plan, review. Implemented as a register kind, a skill, or a command. |
| Register | A stateful item with a lifecycle under `life/registers/<kind>/`. |
| Journal | Append-only events under `life/journal/`. |
| Digest | One markdown file per source per run under `life/inbox/`, written by a connector. |
| Workspace | A folder under `life/workspaces/<slug>/` for a piece of thinking in progress. |
| Artefact | A generated report or document under `life/reports/` or a workspace. |
