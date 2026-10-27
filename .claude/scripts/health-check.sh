#!/usr/bin/env bash
# health-check.sh: structural health check for GogOS (spec 8).
#
# Deterministic checks only, in two halves reported separately:
#
#   SYSTEM  the tracked machinery (gogos/, .claude/, docs/) and the rules that
#           keep private data local. S1 to S8.
#   LIFE    the owner's memory under life/ and me/. L1 to L8, advisory.
#
# EXIT CODE CONTRACT: the exit code reflects SYSTEM only. 0 = the machinery is
# sound, 1 = it is not, 2 = usage. LIFE findings never make this script
# non-zero: a stale inbox or a quiet journal is not a broken system. The LIFE
# block is still printed in full so a finding cannot hide by omission.
#
# The exception, deliberately: checks that protect the data boundary (S1, S4,
# S8) are SYSTEM checks and fail the exit code, because they test a rule the
# system enforces, not the owner's tidiness.
#
# Usage: health-check.sh [--system | --life | --all] [--no-tests] [--help]
#   --no-tests  skip S5 (pytest and run-tests.sh). run-tests.sh passes it when
#               it runs this script against a synthetic repo.
#
# Python: GOGOS_PYTHON if set, else .venv/bin/python, else python3. The LIFE
# half and S6 call gogos.core.health, so the register and front matter rules
# live in Python once and are never restated here.
# Written for bash 3.2 (macOS default). Run from anywhere.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
cd "$ROOT" || { echo "FATAL: cannot cd to repo root" >&2; exit 2; }

run_system=1
run_life=1
run_tests=1
while [ $# -gt 0 ]; do
  case "$1" in
    --system)   run_system=1; run_life=0 ;;
    --life)     run_system=0; run_life=1 ;;
    --all)      run_system=1; run_life=1 ;;
    --no-tests) run_tests=0 ;;
    --help|-h)  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

if [ -n "${GOGOS_PYTHON:-}" ]; then PY="$GOGOS_PYTHON"
elif [ -x .venv/bin/python ]; then PY=".venv/bin/python"
else PY="python3"; fi

sys_issues=0; sys_warns=0
life_warns=0

sys_issue() { printf '  ISSUE %s\n' "$1"; sys_issues=$((sys_issues+1)); }
sys_warn()  { printf '  warn  %s\n' "$1"; sys_warns=$((sys_warns+1)); }
ok()        { printf '  PASS  %s\n' "$1"; }
sec()       { printf '\n-- %s --\n' "$1"; }
band()      { printf '\n==== %s\n' "$1"; }

in_git=0
git rev-parse --git-dir >/dev/null 2>&1 && in_git=1

# Files under the system directories: tracked plus untracked-but-not-ignored,
# so a new file is checked before it is committed and gitignored local files
# (settings.local.json) are not.
system_files() {
  if [ "$in_git" -eq 1 ]; then
    git ls-files -co --exclude-standard -- gogos .claude docs 2>/dev/null
  else
    find gogos .claude docs -type f 2>/dev/null
  fi
}

# Value of a front matter key in a markdown file (first match, inside the block).
fm() { # $1=file $2=key
  awk -v k="$2" 'NR==1 && $0!="---"{exit} NR>1 && $0=="---"{exit}
                 NR>1 { if (index($0, k":")==1) { sub("^"k":[ \t]*", ""); print; exit } }' "$1"
}

echo "GogOS health check: root $ROOT"

# ============================================================================
# SYSTEM
# ============================================================================
if [ "$run_system" -eq 1 ]; then
band "SYSTEM (gates the exit code)"

# --- S1. Data boundary -------------------------------------------------------
sec "S1 data boundary"
before=$sys_issues
for rule in /life/inbox/ .core/storage/ .core/config/secrets/ .core/config/accounts.json; do
  grep -qxF "$rule" .gitignore 2>/dev/null || sys_issue "S1 .gitignore has lost the '$rule' rule"
done
if [ "$in_git" -eq 1 ]; then
  for p in life/inbox .core/storage .core/config/secrets .core/config/accounts.json; do
    n="$(git ls-files -- "$p" | wc -l | tr -d ' ')"
    [ "$n" -gt 0 ] && sys_issue "S1 $n file(s) under $p are tracked by git (run: git ls-files $p)"
  done
  while IFS= read -r f; do
    [ -n "$f" ] && sys_issue "S1 tracked file looks like a credential: $f"
  done < <(git ls-files | grep -iE '(^|/)[^/]*token[^/]*$|(^|/)[^/]*\.env$|(^|/)credentials[^/]*$')
fi
[ "$sys_issues" -eq "$before" ] && ok "S1 private paths ignored and untracked; no credential files tracked"

# --- S2. Agents and skills ---------------------------------------------------
sec "S2 agents and skills"
before=$sys_issues
agent_names=""
for f in .claude/agents/*.md; do
  [ -f "$f" ] || continue
  for k in name description model tools; do
    [ -n "$(fm "$f" "$k")" ] || sys_issue "S2 agent missing '$k:' in front matter: $f"
  done
  n="$(fm "$f" name)"; agent_names="$agent_names $n"
  m="$(fm "$f" model)"
  case "$m" in *fable*) sys_issue "S2 agent $f pins a Fable model (excluded, see CLAUDE.md)" ;; esac
  tools="$(fm "$f" tools)"
  case "$n" in
    council-chair) ;;
    council-*)
      case "$tools" in *Write*|*Edit*) sys_issue "S2 council seat $n has Write or Edit; seats only read" ;; esac ;;
    gardener) ;;
    *)
      case "$tools" in *Bash*) sys_issue "S2 agent $n has Bash; only gardener may" ;; esac ;;
  esac
done
for f in .claude/skills/*/SKILL.md; do
  [ -f "$f" ] || continue
  [ -n "$(fm "$f" model)" ] && sys_issue "S2 skill declares 'model:' (skills inherit their caller's): $f"
done
# An agent is "named in a command" as .claude/agents/<name>.md or as `<name>` agent.
while IFS= read -r a; do
  [ -n "$a" ] || continue
  case " $agent_names " in *" $a "*) ;; *) sys_issue "S2 a command names agent '$a', which does not exist" ;; esac
done < <(cat .claude/commands/*.md 2>/dev/null \
          | grep -oE '\.claude/agents/[a-z0-9-]+\.md|`[a-z0-9-]+` agent' \
          | sed -e 's#^\.claude/agents/##' -e 's#\.md$##' -e 's#^`##' -e 's#` agent$##' | sort -u)
[ "$sys_issues" -eq "$before" ] && ok "S2 agent front matter complete, tool grants within policy, skills unpinned"

# --- S3. Command targets import ----------------------------------------------
sec "S3 command targets"
before=$sys_issues
mods="$(cat .claude/commands/*.md 2>/dev/null | grep -oE 'python3? -m gogos(\.[a-z0-9_]+)+' \
        | sed 's/.* -m //' | sort -u)"
n=0
for m in $mods; do
  n=$((n+1))
  "$PY" -c "import $m" >/dev/null 2>&1 || sys_issue "S3 a command runs '$m', which does not import"
done
[ "$sys_issues" -eq "$before" ] && ok "S3 all $n gogos modules named by commands import"

# --- S4. Decoupling ----------------------------------------------------------
sec "S4 decoupling"
before=$sys_issues
terms_file="$(mktemp "${TMPDIR:-/tmp}/gogos-terms.XXXXXX")"
trap 'rm -f "$terms_file"' EXIT
"$PY" - "$terms_file" <<'PY'
import json, re, sys
from pathlib import Path
# Aliases that are ordinary words; the docs use them as examples.
GENERIC = {"personal", "work", "home", "main", "default", "family"}
out = []
aliases = []
try:
    data = json.loads(Path(".core/config/accounts.json").read_text())
    out += re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", json.dumps(data))
    if isinstance(data.get("aliases"), dict):
        aliases = [a for a in data["aliases"] if a not in GENERIC]
except (OSError, ValueError, AttributeError):
    pass
try:
    text = Path("me/profile.md").read_text().split("\n")
    if text and text[0] == "---":
        for line in text[1:text.index("---", 1)]:
            if line.startswith("owner:"):
                v = line[6:].strip().strip('"')
                if v and v != "none" and not v.startswith("<"):
                    out.append(v)
except (OSError, ValueError):
    pass
try:
    for line in Path("tests/fixtures/forbidden-terms.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
except OSError:
    out += aliases  # no owner list yet: default to the account aliases
Path(sys.argv[1]).write_text("".join(t + "\n" for t in sorted(set(out))))
PY
n_terms="$(grep -c . "$terms_file" | tr -d ' ')"
if [ "$n_terms" -gt 0 ]; then
  hits="$(system_files | while IFS= read -r f; do
            [ -f "$f" ] && grep -IilF -f "$terms_file" "$f" 2>/dev/null
          done)"
  for f in $hits; do sys_issue "S4 $f contains an account email, the owner's name or a forbidden term"; done
fi
[ -f tests/fixtures/forbidden-terms.txt ] \
  || sys_warn "S4 no tests/fixtures/forbidden-terms.txt; using the account aliases as the forbidden terms"
[ "$sys_issues" -eq "$before" ] && ok "S4 no personal term in gogos/, .claude/ or docs/ ($n_terms term(s) checked)"

# --- S5. Tests ---------------------------------------------------------------
sec "S5 tests"
if [ "$run_tests" -eq 0 ]; then
  echo "  skipped (--no-tests)"
else
  before=$sys_issues
  for s in .claude/scripts/*.sh; do
    bash -n "$s" 2>/dev/null || sys_issue "S5 syntax error in $s"
  done
  "$PY" -m pytest -q >/dev/null 2>&1 || sys_issue "S5 pytest fails (run: $PY -m pytest -q)"
  if [ -f .claude/scripts/run-tests.sh ]; then
    bash .claude/scripts/run-tests.sh >/dev/null 2>&1 \
      || sys_issue "S5 run-tests.sh fails (run: bash .claude/scripts/run-tests.sh)"
  else
    sys_issue "S5 .claude/scripts/run-tests.sh is missing"
  fi
  [ "$sys_issues" -eq "$before" ] && ok "S5 scripts parse; pytest and run-tests.sh pass"
fi

# --- S6. Areas ---------------------------------------------------------------
sec "S6 areas"
s6="$("$PY" -m gogos.core.health areas --root "$ROOT" 2>&1)"
while IFS= read -r line; do
  case "$line" in
    "PASS S6 "*)  ok "S6 ${line#PASS S6 }" ;;
    "ISSUE S6 "*) sys_issue "S6 ${line#ISSUE S6 }" ;;
    "") ;;
    *) sys_issue "S6 could not run gogos.core.health: $line" ;;
  esac
done <<EOF
$s6
EOF

# --- S7. Source-scan invariants ----------------------------------------------
sec "S7 source scan"
before=$sys_issues
while IFS= read -r hit; do
  [ -n "$hit" ] && sys_issue "S7 gog call without --readonly outside gogos/execution/: $hit"
done < <(grep -rnE --include='*.py' "[\"']gog[\"' ]" gogos 2>/dev/null \
          | grep -v '^gogos/execution/' | grep -v -- '--readonly')
while IFS= read -r hit; do
  [ -n "$hit" ] && sys_issue "S7 imports gogos.execution from a read path: $hit"
done < <(grep -rnE --include='*.py' '^[[:space:]]*(from|import)[[:space:]]+gogos\.execution' \
          gogos/core/brief.py gogos/intake 2>/dev/null)
[ "$sys_issues" -eq "$before" ] && ok "S7 every gog read is --readonly; read paths never import gogos.execution"

# --- S8. Local permissions ---------------------------------------------------
sec "S8 local permissions"
before=$sys_issues
if [ -f .claude/settings.local.json ]; then
  n="$("$PY" -c 'import json,sys
try: d=json.load(open(sys.argv[1]))
except ValueError: print("bad"); sys.exit()
print(len(d.get("permissions",{}).get("allow",[])))' .claude/settings.local.json 2>/dev/null)"
  case "$n" in
    0) ;;
    bad) sys_issue "S8 .claude/settings.local.json is not valid JSON" ;;
    *) sys_issue "S8 .claude/settings.local.json holds $n allow rule(s); move the ones the system needs into .claude/settings.json" ;;
  esac
fi
[ "$sys_issues" -eq "$before" ] && ok "S8 no allow rules in settings.local.json"

fi # run_system

# ============================================================================
# LIFE
# ============================================================================
if [ "$run_life" -eq 1 ]; then
band "LIFE (advisory)"
sec "L1 to L8"
life_out="$("$PY" -m gogos.core.health life --root "$ROOT" 2>&1)"
while IFS= read -r line; do
  case "$line" in
    "PASS "*) ok "${line#PASS }" ;;
    "WARN "*) printf '  warn  %s\n' "${line#WARN }"; life_warns=$((life_warns+1)) ;;
    "") ;;
    *) printf '  warn  %s\n' "$line"; life_warns=$((life_warns+1)) ;;
  esac
done <<EOF
$life_out
EOF
fi

# ============================================================================
# SUMMARY
# ============================================================================
band "SUMMARY"
[ "$run_system" -eq 1 ] && printf '  SYSTEM  %s issue(s), %s warning(s)\n' "$sys_issues" "$sys_warns"
[ "$run_life" -eq 1 ]   && printf '  LIFE    %s warning(s), advisory only\n' "$life_warns"
if [ "$run_system" -eq 1 ] && [ "$sys_issues" -gt 0 ]; then
  echo "SYSTEM ISSUES: fix before pushing."
  exit 1
fi
echo "SYSTEM HEALTHY"
exit 0
