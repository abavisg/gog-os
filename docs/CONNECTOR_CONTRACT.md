# Connector Contract

A **connector** is the code that talks to one external service (Gmail, Calendar, Granola, Linear, Slack, Notion, …) and turns its raw API shape into GogOS slim JSON. Connectors are a family: they have nothing in common at the API level, but every one conforms to the same contract so the host can treat them uniformly — and so they can eventually live in a separate connectors repo.

This is the pipeline principle `API → normalised JSON → skill → report` lifted into a per-connector interface.

## The contract

Every connector implements two pure functions:

```python
fetch(client, window) -> raw        # talk to the service, return its raw response
normalise(raw)        -> slim dict  # raw API shape → GogOS slim JSON
```

- `client` is an **already-authenticated** service client or credentials object, supplied by the host.
- `window` describes what to fetch (e.g. a day count, a date range) — connector-specific shape, but always passed in, never hardcoded.
- `raw` is the unmodified service response.
- The returned slim dict is what a skill is allowed to read. Nothing else reaches a model.

## Three prohibitions

A connector **must not**:

1. **Write storage.** No `storage_path`, no `latest-*` aliasing, no file I/O for output. It returns data; the host decides where it lands.
2. **Resolve identity.** No alias→account resolution, no token-path derivation, no reading `.core/config`. It receives an authenticated client; auth is the host's job.
3. **Import `gogos.*`.** A connector depends only on its service's SDK/HTTP client. This is the test for whether the seam is clean: if a connector imports from `gogos`, it isn't extractable.

## What the host owns

These never live in a connector — they belong to GogOS as the host system:

| Concern | Owner |
|---|---|
| Identity / alias resolution | `gogos/auth/accounts.py` |
| Auth flow, token storage | host (`gogos/auth/*`) — passes an authed client to the connector |
| Storage (dated dirs + `latest-*`) | `gogos/paths.py` |
| CLI wrappers (`python -m gogos.<module>`) | host |

The host wraps each connector: resolve account → build authed client → call `fetch`/`normalise` → write slim JSON to `.core/storage` with a `latest-*` alias.

## Data-hygiene gates ship with the connector

A connector that has a service-specific privacy or hygiene invariant enforces it **inside the connector**, so every host gets it for free and no host re-implements it. Example: the Gmail connector hard-asserts no message body ever appears in its output (`assert_no_body`); that assertion runs inside `fetch`/`normalise`, not in the GogOS wrapper.

## Auth varies; the contract does not

The contract is uniform; the auth model differs per service. This only changes how the host builds the `client` it passes in — not the connector's interface.

| Connector | Auth model | Host hands the connector |
|---|---|---|
| Gmail / Calendar | Google OAuth installed-app flow, per-account token files | a `Credentials` object |
| Granola / Linear / Slack / Notion | API key / bearer token | an already-constructed SDK client |

**Inject the client, not the secret.** A connector receives a constructed client (or `Credentials`), never a raw token or API key it has to build a client from. This keeps secret handling and config entirely on the host side, which is what the "never resolve identity" rule requires.

## Conformance checklist

A module is a conforming connector when:

- [ ] It exposes pure `fetch(client, window)` and `normalise(raw)` functions.
- [ ] `normalise` is pure: same `raw` in → same slim dict out, no side effects.
- [ ] No `gogos.*` import anywhere in the module.
- [ ] No storage writes, no `latest-*` aliasing, no `.core/config` reads.
- [ ] It receives an authenticated client; it does not authenticate or resolve accounts.
- [ ] Any service-specific hygiene gate (e.g. no-body) runs inside the connector.

## Status

Gmail and Calendar are the current connectors. They predate this contract: their pure functions (`normalise_message`, `normalise_event`, `normalise_raw`, `_assert_no_body`) are already separated by function boundary, but the top-level `fetch()`/`normalise()` orchestrators still resolve accounts and write storage. Bringing them into full conformance — and extracting all connectors into a separate repo — is a planned future refactor.
