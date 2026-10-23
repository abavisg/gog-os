# Spec 11: further intake (placeholder; one spec per source when earned)

Each source below becomes its own spec when a real need appears. The bar, from the
proposal: a weekly question it answers, a register or journal type it feeds, and a
deterministic connector with no LLM in the fetch path. Order is a guess, to be
reordered by use.

| Source | Area | Connector shape | Earned when |
|---|---|---|---|
| **Apple Health export** | wellness | one-off XML/CSV export dropped in `life/inbox/`, parsed to `log.sleep`, `log.workout`, `log.weight` journal events with `source: apple-health`, deduped by timestamp | `/log` for wellness has held for 4+ weeks and the manual entries are the bottleneck |
| **WhatsApp export** | family, people | ClientOS's `_whatsapp_import.py` as-is (dedup ledger, digest); `/process-inbox` treats it as a conversation: asks and facts, no outcome inferred | a family or school group is where commitments are actually made |
| **Finance feeds / statements** | finance | CSV statement drops (bank export) parsed to a monthly `finance` summary in `inputs.json`: recurring charges, new merchants, renewals matched to `renewals` | the "silent money" question is asked twice without an answer |
| **News feeds** | growth, finance | RSS fetch to a digest, relevance-filtered by `me/areas.json` keywords, deterministic; the `news-curator` skill (recreated with a real contract) summarises with sources | the weekly review wants market or AI signals and the inbox is clean enough to carry them |
| **Reading list** | growth | a `life/wiki/growth/reading.md` table plus `/log learning --ref`; no connector | immediately, it is a page |
| **Car / home telemetry** | home | none planned; MOT and tax dates come from the renewals register | not planned |
| **Slack, Linear, GitHub** | work | not in GogOS; those belong to ClientOS or FractionalOS and reach GogOS via the bridge (spec 10) | never directly |

Each new connector follows spec 3's shape: `gogos/intake/<source>/fetch.py` with
`fetch()` and `main()`, a dedup ledger under `.core/storage/<source>/`, a digest in
`life/inbox/<source>-<date>.md` with capture front matter, bounded by config caps,
tests with synthetic fixtures, and a row in `/sync`'s source table.
