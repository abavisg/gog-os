# Claude Code Start Prompts

## Prompt 1: Architecture review

Use model: Claude Opus 4.8

```text
Read the whole repository. Start with README.md, docs/PRD.md, docs/ARCHITECTURE.md, docs/IMPLEMENTATION_PLAN.md, docs/GOOGLE_INTEGRATIONS.md, docs/SECURITY.md, and docs/MODEL_USAGE.md.

Do not write code yet.

Give me:
1. Your critique of the GogOS architecture.
2. The biggest risks.
3. Anything that is over-engineered.
4. Anything missing.
5. The smallest safe first implementation step.
```

## Prompt 2: FoundationOS implementation

Use model: Claude Sonnet 4.6

```text
Implement Phase 1: FoundationOS only.

Do not implement Gmail, Calendar, News, Health, Learning, or dashboard code yet.

Create the minimal Python package, config loader, setup check, .env.example, .gitignore, and tests.

Follow docs/IMPLEMENTATION_PLAN.md and docs/ARCHITECTURE.md.

After implementation, run tests and give me a short summary of what changed.
```

## Prompt 3: Google OAuth foundation

Use model: Claude Sonnet 4.6

```text
Implement Phase 2: Google Auth Foundation only.

Use read-only Gmail and Calendar scopes from docs/GOOGLE_INTEGRATIONS.md.

Create reusable OAuth helper code. Add login and logout scripts/commands. Do not fetch emails or calendar events yet.

Add tests where practical without requiring live Google credentials.
```

## Prompt 4: EmailOS MVP

Use model: Claude Sonnet 4.6

```text
Implement Phase 3: EmailOS MVP only.

Build metadata-only Gmail fetch, normalisation, dated storage, categories, rubric, and /email-report command.

No Gmail write-back. No labels. No archive. No delete.

Use Sonnet for classification and Haiku for report rendering where Claude Code supports model selection.
```

## Prompt 5: CalendarOS MVP

Use model: Claude Sonnet 4.6

```text
Implement Phase 4: CalendarOS MVP only.

Build read-only Google Calendar event fetch, normalisation, dated storage, and /calendar-brief command.

Handle today, tomorrow, and week ranges. Handle all-day events.
```

## Prompt 6: Morning Brief MVP

Use model: Claude Sonnet 4.6

```text
Implement Phase 6: BriefingOS MVP.

Read the latest EmailOS, CalendarOS, and TaskOS/local task artefacts if available. Generate a daily brief with top priorities, schedule, risks, and actions.

Handle missing module outputs gracefully.
```
