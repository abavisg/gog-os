# EmailOS Automation Design

How the daily email pipeline drains an inbox larger than the fetch cap and keeps
the move (write-back) gated behind your approval. Scheduling is deferred — see
§3 for why a cloud routine doesn't fit and what the path is.

## Decisions (locked)

- **Approval model:** a scheduled (or manual) run does **fetch → normalise →
  classify → triage → report**, then **notifies you and stops**. **No emails move
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

### 3. Scheduling the morning run — the constraint

The original plan was an 08:00 **claude.ai cloud Routine**. Investigation showed
this **does not fit the GogOS pipeline**: a cloud routine runs in Anthropic's
cloud with a fresh git checkout and **none of** the local prerequisites the
pipeline needs — no `.venv`, no `.env`, no Google OAuth token, no `.core/storage`.
Running `gogos.gmail.gmail_fetch` there would fail immediately (no credentials).

So scheduling is **deferred**, with two viable paths for later:

- **Local scheduler (launchd/cron on the Mac).** Runs the real `gogos` pipeline
  with the local venv, OAuth token, and storage. Truly executes the read-only
  morning triage. Only fires while the machine is on. This is the natural fit and
  the recommended path when we automate.
- **Cloud routine via the Gmail MCP connector.** A genuinely-headless path that
  reads the inbox through the connected `Gmail` MCP connector (works in the
  cloud) and reports a summary — but it would be a *parallel* classifier, not the
  `gogos` code, so it duplicates logic and diverges from the tested module.

Either way the rule stands: the scheduled run is **read-only** (fetch → classify
→ report → notify). Moves remain manual via `/email-apply` (one batch) or
`/email-loop` (drain all), so the approval gate is preserved.

## Why not a single fully-headless run that also moves?

Read-only run + manual-apply is deliberate: an unattended run can't show you a
move plan, and write-back crosses the approval gate the whole project is built
around. Keeping the scheduled run read-only preserves that gate while still
giving you a triaged inbox waiting every morning.

## Build order / status

1. ✅ `gogos.gmail.gmail_classify` + tests (unblocks everything). — PR #3
2. ✅ `gogos.gmail.gmail_loop` + `/email-loop` command + tests. — this PR
3. ⏭️ **Scheduling deferred.** Cloud routines can't run the local pipeline (no
   venv/OAuth/storage); a local launchd/cron job is the path when we automate.
4. ⏭️ (optional) Wire `classify` into `/email-report` so its triage step also
   runs without hand-classification.
