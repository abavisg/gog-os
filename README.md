# GogOS Rebuild Pack

This pack is designed to be unzipped into a fresh folder and reviewed by Claude Code before implementation.

## Recommended first instruction to Claude Code

```text
Read README.md, docs/PRD.md, docs/IMPLEMENTATION_PLAN.md, docs/MODEL_USAGE.md, and docs/ARCHITECTURE.md first. Do not implement anything yet. Produce a short review of the proposed architecture, identify risks, and then suggest the smallest safe first implementation step.
```

## What this contains

- A detailed PRD for rebuilding GogOS from scratch.
- Incremental module-by-module implementation specs.
- Claude Code command and skill scaffolding.
- Google Gmail and Calendar integration guidance.
- Model selection guidance for each build phase and runtime workflow.
- Security, permissions, storage, and approval-gate requirements.
- Starter config and file structure.

## What this does not contain

- No live Google credentials.
- No OAuth tokens.
- No generated secrets.
- No production-ready code yet.

The point is to give Claude Code a clean product and technical specification, not inherit the old implementation.
