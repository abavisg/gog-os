# Security and Privacy Requirements

## Baseline stance

GogOS handles private email, calendar, health, learning and personal logs. Treat
all generated data as sensitive.

## Rules

- Local-first by default.
- No secrets in git.
- No tokens in prompts unless explicitly required and redacted.
- No destructive or external write action without explicit approval.
- OAuth scopes: read-only for fetch; Gmail uses `gmail.modify` to enable
  EmailOS write-back (label + archive). **`gmail.modify` does not permit
  permanent deletion, and GogOS never calls a delete or trash endpoint**: the only
  mutations are adding `GSD/*` labels and removing `INBOX`.
- Prefer generated summaries over exposing full raw email or calendar data to Claude.
- The Gmail snippet is body-derived (up to about 100 characters). It is stored in
  the raw and slim JSON under `.core/storage` and shown to the model; no other body
  content is fetched or stored.

## The data boundary

Everything is tracked in one private repo except the paths below. The health check
(S1) asserts each rule is present in `.gitignore` and that `git ls-files` shows
nothing under any of them, so the boundary is tested, not assumed.

| Path | Tracked? | Why |
|---|---|---|
| `life/inbox/` | no | connector digests and drops; from slice 3 they hold mail bodies |
| `.core/storage/` | no | raw and slim JSON, approvals, ledgers, OAuth tokens |
| `.core/config/secrets/` | no | credentials |
| `.core/config/accounts.json` | no | maps aliases to real addresses |
| `.claude/settings.local.json` | no | machine-local permission gates |
| `tests/fixtures/forbidden-terms.txt` | no | the owner's real terms for the S4 scan |
| `.core/config/` (the rest) | yes | decoupled config: categories, classifier lists, rubric, feeds; system, so S4 scans it |
| `life/` (the rest), `me/` | yes | the owner's memory and profile, in the private repo |
| `gogos/`, `.claude/`, `docs/`, `tests/`, `README.md`, `CLAUDE.md` | yes | the system; must contain no personal fact (S4) |

Also ignored: `.env`, `credentials.json`, `*token*.json`, `.venv/`, caches.
S1 fails if a tracked file name looks like a credential (`*token*.json`, `*.env`,
`credentials*`).

**Decoupling.** S4 scans the system files (`gogos/`, `.claude/`, `docs/`,
`tests/`, the tracked `.core/config/`, `README.md` and `CLAUDE.md`; never `me/`)
for any address in `.core/config/accounts.json`, the `owner:` named in
`me/profile.md`, and each term in `tests/fixtures/forbidden-terms.txt` (one per
line; without it, the non-generic account aliases). Independently of those terms,
every email address must be at `example.com`, `example.org` or `example.net`, or be
listed in the tracked, owner-reviewed `tests/fixtures/synthetic-addresses.txt`, so
the check still bites in CI where no terms exist. Examples use `personal`, `work`
and `you@example.com`.

## Assistant permissions

`.claude/settings.json` is tracked and is the posture:

- **deny**: direct `gog`, Google API calls, reading credential stores (OAuth
  tokens, `.core/config/secrets/`, `.env`, SSH and cloud keys, the keychain, the
  environment), and GitHub writes other than the pull request flow.
- **ask**: `git push`, history rewrites, every `rm` form, the PR flow (create,
  ready, merge, close), and Gmail write-back (`gmail_apply ... apply`,
  `gmail_undo`, `gmail_loop`).
- **allow**: reads, the gogos modules, tests, ruff and the `.claude/scripts/`
  helpers.

`settings.local.json` may narrow (ask, deny) but never widen: an allow rule there
fails S8. `bash .claude/scripts/permission-check.sh <command>` explains which rule
decides a command; `--audit` checks the whole ruleset.

## Approval gates

State-changing actions use a two-step flow:

1. Generate the proposed action file.
2. Apply only after explicit user confirmation.

## OAuth safety

Use one Google OAuth desktop client for local development. Use read-only scopes
first. If scopes change, delete the token and re-authenticate. Slice 3 moves token
storage to the `gog` CLI and the platform keyring.
