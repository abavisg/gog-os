#!/usr/bin/env bash
# banner.sh: the SessionStart banner (spec 8). Replaces the start-day nudge.
#
# Prints one line from local files only, no network and no Python:
#
#   ◇ GogOS · 2 inbox items · 1 commitment due today · 3 uncommitted
#
# and offers /start-day when today's start-day report does not exist yet
# (life/reports/start-day/<today>/ or the current panel under .core/storage).
# It never runs the pipeline. "Today" is the local date in GOGOS_TIMEZONE
# (default Europe/London), matching gogos.core.paths.today().
#
# Output contract (Claude Code hooks): JSON on stdout; systemMessage is shown
# to the owner, hookSpecificOutput.additionalContext is given to the model.
# Always exits 0: a banner must never block a session.
# Written for bash 3.2, dependency-free.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
cd "$ROOT" 2>/dev/null || exit 0

TODAY="$(TZ="${GOGOS_TIMEZONE:-Europe/London}" date +%Y-%m-%d)"

plural() { [ "$1" -eq 1 ] && printf '%s %s' "$1" "$2" || printf '%s %ss' "$1" "$2"; }

inbox=0
if [ -d life/inbox ]; then
  inbox="$(find life/inbox -type f ! -name '.*' 2>/dev/null | wc -l | tr -d ' ')"
fi

# Open commitments whose due date (YYYY-MM-DD[THH:MM]) is today. Front matter
# only: the scan stops at the closing ---.
due=0
for f in life/registers/commitment/*.md; do
  [ -f "$f" ] || continue
  case "$f" in */_*) continue ;; esac
  hit="$(awk -v t="$TODAY" 'NR==1 && $0!="---"{exit} NR>1 && $0=="---"{exit}
          /^status:/ { s=$2 } /^due:/ { d=$2; gsub(/"/,"",d); d=substr(d,1,10) }
          END { if (s=="open" && d==t) print 1 }' "$f")"
  [ "$hit" = "1" ] && due=$((due+1))
done

dirty=0
if git rev-parse --git-dir >/dev/null 2>&1; then
  dirty="$(git status --porcelain --untracked-files=all 2>/dev/null | wc -l | tr -d ' ')"
fi

line="◇ GogOS · $(plural "$inbox" "inbox item") · $(plural "$due" commitment) due today · $dirty uncommitted"

ran=0
[ -d "life/reports/start-day/$TODAY" ] && [ -n "$(ls -A "life/reports/start-day/$TODAY" 2>/dev/null)" ] && ran=1
[ -f ".core/storage/reports/start-day/all/$TODAY/start-day.md" ] && ran=1

if [ "$ran" -eq 1 ]; then
  printf '{"systemMessage": "%s"}\n' "$line"
else
  printf '{"systemMessage": "%s · run /start-day?",\n "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "There is no /start-day report for %s yet. Offer /start-day once if the owner starts on the day; never run it unasked."}}\n' \
    "$line" "$TODAY"
fi
exit 0
