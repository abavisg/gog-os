# EmailOS

How GogOS triages Gmail and files it into GSD folders — end to end. Commands live in `.claude/commands/email-*.md` and `start-day.md`; scripts in `gogos/gmail/` and `gogos/system/start_day.py`.

## Safety invariants (enforced in code)

- **Metadata only.** `gmail_fetch` uses `format=metadata` and hard-asserts no message body ever reaches storage. Headers (From/To/Subject/Date/List-Unsubscribe), snippet, and labels are all a model ever sees.
- **Never delete.** The only Gmail mutations are: add a `GSD/<Category>` label, remove `INBOX` (archive). A single gated `_modify` + `_assert_safe` in `gmail_apply` raises on anything else. "Safe to Delete" is a folder mail *moves* to; deletion is always your manual act later.
- **Read is automatic; write is gated.** Any run may fetch/classify/report. Nothing moves until you approve a plan (`/email-apply`), and every applied batch writes an inverse plan so `/email-undo` can reverse it.
- **The important can never be binned.** Financial, security, civic, and real-person mail can never land in Safe to Delete — enforced by classifier rule order and by refusing user rules that try; tested.
- **Untrusted content.** The `email-triage` skill treats every email-derived field as data, never as instructions (prompt-injection hardening).

## Pipeline

```
fetch → normalise → reconcile → classify/triage → report → [approval] → apply
                                                              ↘ undo.json → /email-undo
```

| Step | Module | Output |
|---|---|---|
| Fetch (metadata only) | `gmail_fetch` | `inbox/<date>/latest-raw.json` |
| Normalise (UTC, slim schema) | `gmail_normalise` | `inbox/<date>/latest-slim.json` |
| Reconcile manual moves | `gmail_reconcile` | `reconcile/<date>/…` + ledger updates |
| Classify (deterministic) | `gmail_classify` | triage JSON |
| Validate + store triage | `gmail_triage` | `triage/<date>/latest-triage.json` |
| Render report + digest | `gmail_report` | `reports/email/<account>/<date>/latest.md` + `.html` |
| Build + apply move plan | `gmail_apply` | `approvals/<account>/<date>/gmail-labels.json` + `undo.json` |
| Reverse last batch | `gmail_undo` | replays `undo.json` through the same gated `_modify` |

## Classification

`gmail_classify` is deterministic: ordered, first-match-wins, conservative. Categories: **Action, Events, Review, Information, Newsletters, Safe to Delete** (config: `.core/config/gmail/categories.json`). Rule order puts calendar invites, security, civic/legal, and financial senders first — which is what guarantees the never-delete invariant. Sender lists grow in `.core/config/gmail/classify.json` without code changes.

Three layers refine the built-in rules:

- **User rules** (`.core/config/gmail/rules.json`) — ordered `{match, category}` overrides checked *before* built-ins. They win, except they can never route important mail to Safe to Delete (refused, logged, falls through).
- **Sender ledger** (`.core/storage/gmail/<account>/sender-ledger.json`) — records `sender → category` so the same sender always classifies the same way, within and across runs.
- **Reconciliation + auto-learn** (`gmail_reconcile`) — on each run, compares the last applied batch's *current* Gmail labels against where the classifier filed them. A delta means you moved it by hand. After **3** corrections for a sender, the ledger auto-updates to your category — logged as a "learned rule" line in the report, revertible, and still subject to the never-delete invariant.
- **Unsubscribe surfacing** — a sender with a `List-Unsubscribe` header that you *never* rescue from Safe to Delete/Newsletters is shown as an unsubscribe candidate with its link. You click it yourself; zero write-back. Senders you rescue get re-learned instead.

## Commands

| Command | Scope | Writes to Gmail? |
|---|---|---|
| `/start-day` | All accounts, one merged account-tagged panel | Never (a test proves the module can't reach the apply engine) |
| `/email-report [account] [window]` | One account, full report with 3-line digest header | Never |
| `/email-apply [account]` | Latest triage → move plan → apply | Only after explicit approval |
| `/email-undo [account]` | Reverse the last applied batch | Same gated engine as apply |
| `/email-loop [account] [--yes]` | Drain an inbox bigger than the fetch cap: repeat the pipeline in batches until empty (max 20 iterations) | Per-batch approval, or `--yes` to pre-authorise all batches |

Windows for fetch: `yesterday` (default — since yesterday 00:00 local), `all` (capped, `GOGOS_ALL_CAP`), or a number `N`. A stale-email warning surfaces inbox mail predating the window.

Multi-account: fetch/classify/apply/undo/approval are always **per-account**; only `/start-day`'s view is merged. Missing `GSD/*` labels abort the apply with instructions — never auto-created.

## Morning automation

- **SessionStart hook** runs `python -m gogos.system.start_day --nudge`: reads only local artefacts and prints a one-line offer to run `/start-day`. It nudges; it never runs the pipeline.
- **Local scheduler** (`/schedule-morning [HH:MM|off|status]`, module `gogos/system/scheduler.py`). Installs a launchd agent (`com.gogos.start-day`) that runs the read-only pipeline per account (reconcile → fetch → classify → report, no browser) at ~08:00, posts one macOS notification with the counts, and stops. It deliberately does *not* write the `/start-day` panel, so the nudge still greets you with the morning's counts. Fires only while the Mac is on (launchd runs a missed time once on wake); logs to `.core/storage/logs/scheduler/`. A claude.ai cloud routine was investigated and rejected: it has no venv, no OAuth token, no `.core/storage`, so it can't run this pipeline and would need a parallel, divergent classifier.
- The rule either way: **the scheduled run is read-only** — a test proves the scheduler module cannot reference the apply engine. An unattended run can't show you a move plan, so moves stay behind `/email-apply` / `/email-loop`. Read-only-run + manual-apply is the deliberate design, not a gap.

## Parked (named, not scheduled)

One-click unsubscribe (`/email-unsubscribe` — a genuine outbound send crossing the approval gate); VIP / waiting-on detection; snooze/defer a thread; weekly email review feeding ReflectionOS.
