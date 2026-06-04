# Model Usage Guide

Use the best model only where it changes the outcome. Do not waste Opus-class models on formatting reports.

## Current recommended model mapping

As of June 2026, Anthropic documents Claude Opus 4.8 as the most capable model for complex reasoning and long-horizon agentic coding, Claude Sonnet 4.6 as the best speed/intelligence balance, and Claude Haiku 4.5 as the fastest current model.

## Build-time model guidance inside Claude Code

| Step | Work | Recommended model |
|---|---|---|
| 0 | Architecture review and scope challenge | Claude Opus 4.8 |
| 1 | FoundationOS implementation | Claude Sonnet 4.6 |
| 2 | Google OAuth foundation | Claude Sonnet 4.6 |
| 3 | EmailOS MVP code | Claude Sonnet 4.6 |
| 3 | Email report rendering | Claude Haiku 4.5 |
| 4 | CalendarOS MVP | Claude Sonnet 4.6 |
| 5 | TaskOS local MVP | Claude Sonnet 4.6 |
| 6 | Morning Brief MVP | Claude Sonnet 4.6 |
| 7 | ActivityOS | Claude Sonnet 4.6 for code, Haiku 4.5 for simple summaries |
| 8 | ReflectionOS | Claude Sonnet 4.6 |
| 9 | NewsOS | Claude Sonnet 4.6 |
| 10 | HealthOS/LearningOS/ContentOS Bridge | Claude Sonnet 4.6 |
| 11 | Dashboard decision | Claude Opus 4.8 |

## Runtime model policy

| Task | Model |
|---|---|
| Architecture redesign | Opus 4.8 |
| Complex agentic coding | Opus 4.8 or Sonnet 4.6 |
| Normal implementation | Sonnet 4.6 |
| Gmail classification | Sonnet 4.6 initially |
| Calendar reasoning | Sonnet 4.6 initially |
| HTML/Markdown report rendering | Haiku 4.5 |
| Simple log summaries | Haiku 4.5 |
| Weekly pattern analysis | Sonnet 4.6 |
| Final system critique | Opus 4.8 |

## Cost-control rule

Default to Sonnet for building and Haiku for simple runtime report rendering. Use Opus only when the decision has architectural consequences.
