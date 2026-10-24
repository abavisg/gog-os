---
description: Append an entry to the journal; waiting and commitment entries also create a register item
argument-hint: <type> <text> [--area A] [--value V --unit U] [--due D] [--owed-by X]
allowed-tools: Bash(.venv/bin/python -m gogos.core.journal:*)
---

# /log <type> <text>

Implementation model: Sonnet (default, unpinned).

Purpose: record one thing that happened, in one line, in today's journal
(`life/journal/YYYY-MM-DD.jsonl`). The script does the work; this command only
parses the arguments, asks when the script needs an answer, and relays the result.

Arguments: `$ARGUMENTS`

## Types

| Type | Area | Side effect |
|---|---|---|
| `workout` `sleep` `weight` `energy` `meal` | wellness (inferred) | none |
| `learning` | growth (inferred) | none |
| `activity` `decision` `note` | ask | none |
| `waiting` | ask | creates a `waiting` register item, owed by whoever follows "from" |
| `commitment` | ask | creates a `commitment` register item, due date parsed from the text |

An explicit `--area` always wins over the inferred one. The six areas are
`wellness finance growth family home work` (see `me/areas.json`).

## Steps

1. Split `$ARGUMENTS` into the type (first word), the text (the rest, quotes
   removed) and any `--flag value` pairs. A number given as `--value` may carry
   `--unit` (`min`, `h`, `kg`, `km`, `score`).
2. Run, quoting the text as one argument:

   ```
   .venv/bin/python -m gogos.core.journal log <type> "<text>" [flags]
   ```

3. Read the exit code:
   - **0**: print the script's single `OK` line and stop. Nothing else.
   - **3** (`ASK` on stderr): the script needs an answer. Ask the owner exactly that
     question in one line, then rerun with the answer as a flag:
     area → `--area <id>`; due date → `--due YYYY-MM-DD` (or `YYYY-MM-DDTHH:MM`);
     who owes it → `--owed-by "<name>"`. Never guess an answer.
   - **1 or 2**: show the `ERROR` line and stop.

## Due dates (`commitment`)

The script reads `by|on|before|due <when>` at the end of the text, or a bare
trailing `today`, `tonight` or `tomorrow`. `<when>` is `today`, `tomorrow`, a
weekday (the next one, never today) or `YYYY-MM-DD`, optionally followed by
`HH:MM`. It asks for anything else, including "next Friday", a weekday that is
today, and `24/10`. The text minus the date phrase becomes the item's title.

## Examples

```
/log workout "run 5k" --value 30 --unit min
/log learning "finished chapter 4 of the stats book"
/log waiting "invoice from Acme" --area work
/log commitment "send the school forms by Friday" --area family
/log decision "switch energy supplier at renewal" --area home
```

## Safety

- Append only. Journal lines are never edited or removed; a correction is a new entry.
- Local only. Nothing leaves the machine; no network call is made.
- Register items are created through `gogos.core.registers` (validated, with history);
  never write a register file by hand from this command.
