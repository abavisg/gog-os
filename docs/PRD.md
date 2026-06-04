# GogOS PRD

## 1. Product Name

GogOS

## 2. Product Summary

GogOS is a Claude Code-native personal AI operating system for managing daily execution across email, calendar, tasks, news, learning, activity, health, content, and reflection.

The first version must be local-first, modular, safe, and useful from the command line before any dashboard is built.

GogOS is not an email tool. EmailOS is only the first module.

## 3. Product Thesis

GogOS should reduce daily cognitive load by turning scattered personal information into structured, actionable operating loops.

The core loop is:

1. Morning: brief, prioritise, plan.
2. During the day: capture, log, update.
3. Evening: review, reflect, carry forward.
4. Weekly: identify patterns, reset priorities, improve the system.

If a feature does not serve this loop, it should not be built yet.

## 4. Target User

Primary user: Giorgos.

Characteristics:

- Technical enough to use Claude Code.
- Wants high leverage personal automation.
- Uses Gmail, Google Calendar, Claude Code, local files, and possibly Notion later.
- Wants to manage work, learning, health, content, trading/finance/news interests, and family life.
- Prefers practical systems over decorative dashboards.

## 5. Goals

### Product goals

- Create a personal command centre inside Claude Code.
- Generate useful daily briefs.
- Triage email without reading full bodies by default.
- Summarise calendar and identify prep/follow-up needs.
- Support configurable news feeds.
- Track activity, decisions, learning, workouts, content progress.
- Produce end-of-day and weekly reviews.
- Keep all state local unless explicitly configured otherwise.

### Technical goals

- Modular command architecture.
- Deterministic Python scripts for API access and storage operations.
- Claude Code slash commands for orchestration.
- Claude skills/subagents for reasoning-heavy transformation.
- Local JSON/Markdown/HTML storage in early phases.
- Explicit approval before state-changing external actions.
- No destructive action without confirmation.
- Clear model selection by task.

## 6. Non-goals

For the first implementation, do not build:

- A web dashboard.
- A desktop app.
- Mobile notifications.
- Fully autonomous email deletion or archiving.
- Background daemons before the manual commands are proven.
- Complex database persistence before local files are insufficient.
- A universal agent platform with too many abstractions.

## 7. Success Metrics

### MVP success

- `/setup-check` confirms local environment and required folders.
- `/login-google personal` completes OAuth and stores token locally.
- `/email-report personal` generates a useful email triage report.
- `/calendar-brief personal today` generates a useful calendar brief.
- `/morning-brief` combines email, calendar, task notes, and news into one report.
- `/log` captures activity entries into local storage.
- `/end-day` generates a daily review from logs and generated reports.

### Quality success

- Commands are understandable.
- Failures are explicit and recoverable.
- Reports include source files and timestamps.
- User can inspect every generated JSON/Markdown/HTML artefact.
- No write-back happens without explicit approval.

## 8. Product Modules

### 8.1 FoundationOS

Base project structure, config, validation, logging, command conventions, storage conventions.

### 8.2 EmailOS

Fetch, triage, and report Gmail inbox items. First scope is read-only Gmail OAuth, metadata-only fetch by default, classification, Markdown/HTML reports. Later scope is Gmail labelling and archiving only after approval.

### 8.3 CalendarOS

Fetch and summarise Google Calendar events. First scope is read-only Calendar OAuth, today/tomorrow/week event fetch, schedule summary, conflicts, prep, and focus gaps.

### 8.4 TaskOS

Manage local tasks first, then integrate with Notion or Google Tasks later if justified.

### 8.5 NewsOS

Configurable feeds for AI news, Claude Code news, finance, trading, tech leadership, energy, and personal interests. It must be relevance-scored, not a noisy RSS dump.

### 8.6 BriefingOS

Morning command centre combining EmailOS, CalendarOS, TaskOS, NewsOS, and optional health/learning/content status.

### 8.7 ActivityOS

Fast capture of activities, decisions, learning, workouts, content progress, and notes.

### 8.8 LearningOS

Daily learning support for Python, React, AI agents, RAG, Rust, trading education, leadership frameworks, and other configured tracks.

### 8.9 HealthOS

Workout, energy, sleep, and metabolic health support. First version uses static config and manual logs. Apple Health ingestion comes later.

### 8.10 ContentOS Bridge

Connects GogOS to existing LinkedIn/Substack/content workflows without rebuilding the separate content app.

### 8.11 ReflectionOS

End-of-day and weekly reviews based on logs, briefs, tasks, decisions, and module outputs.

### 8.12 AgentOS

Registry of commands, skills, models, permissions, and workflow dependencies.

## 9. Key Risks

- Overbuilding a dashboard before workflows are proven.
- Creating too many agents before the data model is stable.
- Letting Claude reason over too much raw data.
- OAuth/token mishandling.
- Accidental destructive email/calendar actions.
- News feeds becoming noisy and non-actionable.
- Health/learning/content modules becoming generic advice rather than grounded operating loops.

## 10. Product Principles

- Workflow-first, UI later.
- Local-first, cloud only when necessary.
- Read-only first, write-back only with explicit approval.
- Small modules, clear contracts.
- Scripts fetch and normalise; models interpret and summarise.
- Every generated report must cite its input artefacts.
- Prefer boring storage until the system proves it needs a database.
