# EmailOS Automation Design

How the daily email loop runs unattended at 08:00, drains an inbox larger than
the fetch cap, and keeps the move (write-back) gated behind your approval.

## Decisions (locked)

- **Approval model:** the 08:00 routine runs **fetch → normalise → classify →
  triage → report** unattended, then **notifies you and stops**. **No emails move
  until you run `/email-apply` yourself.** Read is automatic; write stays manual.
- **Classifier:** triage must run without a human, so it becomes a committed,
  tested module (`gogos.gmail.gmail_classify`) — not an ad-hoc script. Built as a
  follow-up step after this design is agreed.
- **>200 handling:** when the inbox exceeds the cap, the flow loops in batches
  until the inbox is empty (details below).

## Three pieces to build

### 1. `gogos.gmail.gmail_classify` — deterministic triage module

Replaces hand/script classification. Pure function: normalised slim JSON →
triage JSON (same schema `gmail_triage` already validates).

Rules are **ordered, first-match-wins, conservative** (the shape proven on the
1,158-email run):

1. Calendar invitations / bookings → **Events**
2. Security / account-safety (new login, password, data exposure, failed
   payment) → **Action**
3. Civic / legal (electoral, police, HMRC, council tax) → **Action**
4. Known banks / insurers / utilities + financial language → **Action**;
   without a payment ask → **Information**
5. Real people (personal addresses, named individuals) → **Review**
6. Social / notification noise → **Safe to Delete**
7. LinkedIn (jobs/messages) → **Review** (never deleted — may be real)
8. Dev-platform notices (GitHub, Kaggle) → **Information**
9. Order / shipping / travel notices → **Information**
10. Financial-info platforms (scores, FX rates) → **Information**
11. Promo / marketing domains → **Safe to Delete**
12. Newsletter domains → **Newsletters**
13. Default long-tail automated mail → **Newsletters** (skim; reversible)

**Invariant:** anything financial, security, civic, or from a real person can
**never** land in Safe to Delete. The rule order guarantees those are matched
first. Sender lists live in config (`.core/config/gmail/classify.json`) so they
can grow without code changes.

Tested in isolation: each rule, the never-delete-the-important invariant, and
full coverage (every input id appears exactly once in output).

### 2. `/email-loop [account]` — drain an oversized inbox in batches

A command that wraps the existing pipeline in a loop, for inboxes bigger than
the fetch cap:

```
repeat:
  fetch (window=all, GOGOS_ALL_CAP=<cap>)
  normalise → classify → triage → report
  build move plan
  --> show plan, get ONE approval (or --yes to skip per-batch approval)
  apply  (move + archive)
until: fetch returns 0 messages   (inbox empty)
```

- Each `apply` archives its batch, so the next `fetch all` sees the *next* slice
  — the inbox drains without pagination state.
- A safety bound (max N iterations, default 20) prevents an infinite loop if
  something stops draining.
- Two approval modes:
  - **default** — pause for your yes on each batch's move plan (matches the
    manual flow today).
  - **`--yes`** — pre-authorise all batches (you said yes once up front). Still
    never deletes.

With `GOGOS_ALL_CAP` raised high enough (e.g. 2000), a single batch usually
clears everything and the loop runs once — but the loop guarantees correctness
regardless of size.

### 3. The 08:00 routine (claude.ai Routine)

A cloud routine (runs without a local session, unlike CronCreate which is
session-only) scheduled for ~08:00 local on weekdays. Its prompt:

> Run the GogOS morning email pipeline for `abavisg`: fetch all → normalise →
> classify → triage → render the report. **Do not move/apply anything.** Then
> summarise the report (counts per folder + the Action items) and tell me to run
> `/email-apply abavisg` (or `/email-loop abavisg`) to file them.

Because the routine is read-only, it's safe to run fully unattended. The moves
wait for you. When you're at your desk you run `/email-apply` (one batch) or
`/email-loop` (drain everything), reviewing the plan first.

## Why not a single fully-headless routine that also moves?

You chose read-only-routine + manual-apply deliberately: a headless run can't
show you a move plan, and write-back crosses the approval gate the whole project
is built around. Keeping the routine read-only preserves that gate while still
giving you a triaged inbox waiting every morning.

## Build order

1. `gogos.gmail.gmail_classify` + tests (unblocks everything).
2. Wire `classify` into a `/morning-email` or extend `/email-report` to use it
   instead of hand-triage.
3. `/email-loop` command + `gmail_apply` loop helper + tests.
4. Create the 08:00 routine via RemoteTrigger once 1–3 are committed.
