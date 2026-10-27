#!/usr/bin/env bash
# run-tests.sh: bash tests for the GogOS scripts (spec 8). pytest covers Python.
#
# Run by health-check.sh (S5), so a failure here fails the SYSTEM verdict.
#
# Every case builds a SYNTHETIC repo in a temp directory: a copy of gogos/ and
# .claude/scripts/, a placeholder me/ and life/, and a fresh git index. Cases
# never read or depend on the real life/ or me/. Each SYSTEM check has a case
# that plants one violation and asserts the check fails on it, plus a clean
# baseline that must pass. Fixture hygiene is itself a case: no fixture here
# may contain an account email or alias from this machine's config.
#
# Usage: run-tests.sh [--verbose]
# Written for bash 3.2 (macOS default).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERBOSE=0
[ "${1:-}" = "--verbose" ] && VERBOSE=1

if [ -n "${GOGOS_PYTHON:-}" ]; then PY="$GOGOS_PYTHON"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then PY="$REPO_ROOT/.venv/bin/python"
else PY="python3"; fi
export GOGOS_PYTHON="$PY"

pass=0; fail=0
TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/gogos-tests.XXXXXX")"
trap 'rm -rf "$TMPROOT"' EXIT

ok()    { printf '    ok   %s\n' "$1"; pass=$((pass+1)); }
bad()   { printf '    FAIL %s\n' "$1"; fail=$((fail+1)); }
group() { printf '  %s\n' "$1"; }

# A clean synthetic repo: the real scripts and gogos/, placeholder content.
new_repo() { # $1=name; prints the directory
  d="$TMPROOT/$1"
  mkdir -p "$d/.claude/scripts" "$d/.claude/commands" "$d/.claude/agents" \
           "$d/.claude/skills/demo" "$d/docs" "$d/me" "$d/.core/config" \
           "$d/life/inbox" "$d/life/journal" "$d/life/reports/weekly" \
           "$d/life/wiki/home" "$d/life/workspaces"
  for r in commitment decision goal occasion parked renewal waiting; do
    mkdir -p "$d/life/registers/$r"
  done
  cp "$REPO_ROOT"/.claude/scripts/*.sh "$d/.claude/scripts/"
  # S5 is exercised with a stub; the real suite here would recurse.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$d/.claude/scripts/run-tests.sh"
  ( cd "$REPO_ROOT" && tar cf - --exclude='__pycache__' gogos ) | ( cd "$d" && tar xf - )
  cp "$REPO_ROOT/me/areas.json" "$d/me/areas.json"
  cat > "$d/.gitignore" <<'EOF'
/life/inbox/
.core/storage/
.core/config/secrets/
.core/config/accounts.json
.claude/settings.local.json
EOF
  cat > "$d/me/profile.md" <<'EOF'
---
title: Owner profile
type: profile
status: draft
area: none
created: 2026-01-01
updated: 2026-01-01
tags: []
validation: provisional
last_validated: none
content_approved: false
---
# Owner profile

| # | Section | Claim | Status | Since | Evidence |
|---|---|---|---|---|---|
| 1 | Synthetic | placeholder | provisional | 2026-01-01 | none |
EOF
  cat > "$d/.claude/commands/demo.md" <<'EOF'
---
description: synthetic command
---
Run `python -m gogos.core.registers index`.
EOF
  cat > "$d/.claude/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: synthetic skill
---
EOF
  cat > "$d/.claude/agents/analyst.md" <<'EOF'
---
name: analyst
description: synthetic agent
model: sonnet
tools: Read, Glob, Grep
---
EOF
  printf '# Synthetic doc\n' > "$d/docs/README.md"
  ( cd "$d" && git init -q && git add -A )
  echo "$d"
}

# Run the health check; sets OUT and RC. $1=dir, rest = extra flags.
hc() {
  d="$1"; shift
  OUT="$( cd "$d" && bash .claude/scripts/health-check.sh --no-tests "$@" 2>&1 )"
  RC=$?
}

# $1=dir $2=needle $3=description [$4=expected rc, default 1]
expect_issue() {
  hc "$1" --system
  want="${4:-1}"
  case "$OUT" in
    *"$2"*) if [ "$RC" -eq "$want" ]; then ok "$3"; else bad "$3 (exit $RC, wanted $want)"; fi ;;
    *) bad "$3"; [ "$VERBOSE" -eq 1 ] && printf '%s\n' "$OUT" | sed 's/^/         /' ;;
  esac
}

echo "GogOS script tests"
echo

# ===========================================================================
group "health-check.sh: baseline"
# ===========================================================================
d="$(new_repo clean)"
hc "$d" --all
if [ "$RC" -eq 0 ] && ! printf '%s\n' "$OUT" | grep -q '  ISSUE'; then
  ok "a clean synthetic repo passes SYSTEM with exit 0"
else
  bad "clean synthetic repo should pass"; printf '%s\n' "$OUT" | grep ISSUE | sed 's/^/         /'
fi
case "$OUT" in *"PASS  L3 0 register items valid"*) ok "LIFE runs against an empty life/ (packaging smoke test)" ;;
               *) bad "LIFE half should run on an empty life/" ;; esac

# ===========================================================================
group "S1 data boundary"
# ===========================================================================
d="$(new_repo s1-rule)"
grep -vxF '/life/inbox/' "$d/.gitignore" > "$d/.gi" && mv "$d/.gi" "$d/.gitignore"
expect_issue "$d" "S1 .gitignore has lost the '/life/inbox/' rule" "a missing /life/inbox/ rule fails S1"

d="$(new_repo s1-tracked)"
mkdir -p "$d/.core/storage/x" && echo '{}' > "$d/.core/storage/x/raw.json"
( cd "$d" && git add -f .core/storage/x/raw.json )
expect_issue "$d" "S1 1 file(s) under .core/storage are tracked" "a tracked file under .core/storage/ fails S1"

d="$(new_repo s1-cred)"
echo '{}' > "$d/gogos/synthetic_token.json"; ( cd "$d" && git add gogos/synthetic_token.json )
expect_issue "$d" "S1 tracked file looks like a credential" "a tracked *token* file fails S1"

# ===========================================================================
group "S2 agents and skills"
# ===========================================================================
d="$(new_repo s2-model)"
sed -i.bak '/^model:/d' "$d/.claude/agents/analyst.md"
expect_issue "$d" "S2 agent missing 'model:'" "an agent without model: fails S2"

d="$(new_repo s2-skill)"
printf -- '---\nname: demo\ndescription: d\nmodel: opus\n---\n' > "$d/.claude/skills/demo/SKILL.md"
expect_issue "$d" "S2 skill declares 'model:'" "a skill with model: fails S2"

d="$(new_repo s2-bash)"
sed -i.bak 's/^tools: .*/tools: Read, Bash/' "$d/.claude/agents/analyst.md"
expect_issue "$d" "S2 agent analyst has Bash" "a non-gardener agent with Bash fails S2"

d="$(new_repo s2-seat)"
printf -- '---\nname: council-skeptic\ndescription: d\nmodel: sonnet\ntools: Read, Write\n---\n' \
  > "$d/.claude/agents/council-skeptic.md"
expect_issue "$d" "S2 council seat council-skeptic has Write" "a council seat with Write fails S2"

d="$(new_repo s2-missing)"
printf -- '---\ndescription: d\n---\nDelegate to the `planner` agent.\n' > "$d/.claude/commands/plan.md"
expect_issue "$d" "S2 a command names agent 'planner'" "a command naming a missing agent fails S2"

# ===========================================================================
group "S3 command targets"
# ===========================================================================
d="$(new_repo s3)"
printf -- '---\ndescription: d\n---\nRun `python -m gogos.no_such_module`.\n' > "$d/.claude/commands/broken.md"
expect_issue "$d" "S3 a command runs 'gogos.no_such_module'" "a command target that does not import fails S3"

# ===========================================================================
group "S4 decoupling"
# ===========================================================================
d="$(new_repo s4-email)"
printf '{"version": 1, "default": "synth", "aliases": {"synth": "owner@example.test"}}\n' \
  > "$d/.core/config/accounts.json"
printf 'Write to owner@example.test for access.\n' > "$d/docs/guide.md"
expect_issue "$d" "S4 docs/guide.md contains" "an account email in a docs file fails S4"

d="$(new_repo s4-alias)"
printf '{"version": 1, "default": "synthalias", "aliases": {"synthalias": "a@example.test", "personal": "b@example.test"}}\n' \
  > "$d/.core/config/accounts.json"
printf 'Example: /email-report synthalias\n' > "$d/.claude/commands/ex.md"
printf 'Example: /email-report personal\n' > "$d/docs/generic.md"
hc "$d" --system
case "$OUT" in *"S4 .claude/commands/ex.md contains"*) ok "a non-generic alias is a default forbidden term" ;;
               *) bad "a non-generic alias should be a default forbidden term" ;; esac
case "$OUT" in *"S4 docs/generic.md"*) bad "a generic alias (personal) should not be a forbidden term" ;;
               *) ok "a generic alias (personal) is not a forbidden term" ;; esac

d="$(new_repo s4-terms)"
mkdir -p "$d/tests/fixtures"; printf '# owner list\nSynthetic Surname\n' > "$d/tests/fixtures/forbidden-terms.txt"
printf 'Ask synthetic surname first.\n' > "$d/gogos/note.txt"
expect_issue "$d" "S4 gogos/note.txt contains" "a term from forbidden-terms.txt fails S4, case-insensitively"

d="$(new_repo s4-owner)"
sed -i.bak 's/^validation: provisional$/owner: Placeholder Owner\nvalidation: provisional/' "$d/me/profile.md"
printf 'Placeholder Owner wrote this.\n' > "$d/docs/x.md"
expect_issue "$d" "S4 docs/x.md contains" "the profile owner's name in a docs file fails S4"

# ===========================================================================
group "S5 tests"
# ===========================================================================
d="$(new_repo s5)"
mkdir -p "$d/tests"; printf 'def test_ok():\n    assert True\n' > "$d/tests/test_ok.py"
OUT="$( cd "$d" && bash .claude/scripts/health-check.sh --system 2>&1 )"; RC=$?
case "$OUT" in *"PASS  S5"*) ok "S5 passes when pytest and run-tests.sh pass" ;;
               *) bad "S5 should pass with a green stub suite"; [ "$VERBOSE" -eq 1 ] && printf '%s\n' "$OUT" ;; esac
printf '#!/usr/bin/env bash\nexit 1\n' > "$d/.claude/scripts/run-tests.sh"
OUT="$( cd "$d" && bash .claude/scripts/health-check.sh --system 2>&1 )"; RC=$?
case "$OUT" in *"S5 run-tests.sh fails"*) [ "$RC" -eq 1 ] && ok "a failing run-tests.sh fails S5" || bad "S5 exit code" ;;
               *) bad "a failing run-tests.sh should fail S5" ;; esac
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/.claude/scripts/run-tests.sh"
printf 'def test_no():\n    assert False\n' > "$d/tests/test_no.py"
OUT="$( cd "$d" && bash .claude/scripts/health-check.sh --system 2>&1 )"
case "$OUT" in *"S5 pytest fails"*) ok "a failing pytest fails S5" ;; *) bad "a failing pytest should fail S5" ;; esac

# ===========================================================================
group "S6 areas"
# ===========================================================================
d="$(new_repo s6-json)"
"$PY" -c 'import json,sys; p=sys.argv[1]; a=json.load(open(p)); a.append({"id":"hobbies","title":"H","priority":7}); json.dump(a,open(p,"w"))' \
  "$d/me/areas.json"
expect_issue "$d" "S6 me/areas.json ids" "an extra id in me/areas.json fails S6"

d="$(new_repo s6-life)"
cat > "$d/life/wiki/home/boiler.md" <<'EOF'
---
title: Boiler
type: wiki
status: current
area: garden
created: 2026-01-01
updated: 2026-01-01
tags: []
---
EOF
expect_issue "$d" "S6 life/wiki/home/boiler.md: area 'garden'" "an unknown area in life/ fails S6"

# ===========================================================================
group "S7 source scan"
# ===========================================================================
d="$(new_repo s7-gog)"
mkdir -p "$d/gogos/intake"
printf 'CMD = ["gog", "gmail", "search", "in:inbox"]\n' > "$d/gogos/intake/fetch.py"
expect_issue "$d" "S7 gog call without --readonly" "a gog call without --readonly outside gogos/execution/ fails S7"

d="$(new_repo s7-ok)"
mkdir -p "$d/gogos/intake" "$d/gogos/execution"
printf 'CMD = ["gog", "--readonly", "gmail", "search"]\n' > "$d/gogos/intake/fetch.py"
printf 'CMD = ["gog", "gmail", "batch", "modify"]\n' > "$d/gogos/execution/apply.py"
hc "$d" --system
case "$OUT" in *"PASS  S7"*) ok "--readonly reads and gogos/execution/ writes pass S7" ;; *) bad "S7 false positive" ;; esac

d="$(new_repo s7-import)"
printf 'from gogos.execution import gmail_apply\n' > "$d/gogos/core/brief.py"
expect_issue "$d" "S7 imports gogos.execution from a read path" "gogos/core/brief.py importing gogos.execution fails S7"

# ===========================================================================
group "S8 local permissions"
# ===========================================================================
d="$(new_repo s8)"
printf '{"permissions": {"allow": ["Bash(ls *)"]}}\n' > "$d/.claude/settings.local.json"
expect_issue "$d" "S8 .claude/settings.local.json holds 1 allow rule" "an allow rule in settings.local.json fails S8"
printf '{"permissions": {"deny": ["Bash(rm -rf *)"]}}\n' > "$d/.claude/settings.local.json"
hc "$d" --system
case "$OUT" in *"PASS  S8"*) ok "local deny rules are allowed (they only narrow)" ;; *) bad "S8 should allow local deny rules" ;; esac

# ===========================================================================
group "LIFE is advisory"
# ===========================================================================
d="$(new_repo life)"
cat > "$d/life/wiki/home/future.md" <<'EOF'
---
title: Future
type: wiki
status: current
area: home
created: 2026-01-01
updated: 2999-01-01
tags: []
related: [[[missing-page]]]
---
EOF
cat > "$d/life/reports/weekly/w1.md" <<'EOF'
---
title: Week one
type: report
status: final
area: none
created: 2026-01-01
updated: 2026-01-01
tags: []
kind: weekly
---
Original text.
EOF
hc "$d" --all
case "$OUT" in *"warn  L1 life/wiki/home/future.md: updated 2999-01-01 is in the future"*) ok "L1 flags an updated date in the future" ;;
               *) bad "L1 should flag a future updated date" ;; esac
case "$OUT" in *"warn  L2 unresolved [[missing-page]]"*) ok "L2 flags an unresolved wikilink" ;;
               *) bad "L2 should flag an unresolved wikilink" ;; esac
[ "$RC" -eq 0 ] && ok "LIFE warnings leave the exit code at 0" || bad "LIFE warnings must not fail the exit code"
printf 'Rewritten text.\n' >> "$d/life/reports/weekly/w1.md"
hc "$d" --life
case "$OUT" in *"warn  L8 life/reports/weekly/w1.md changed after it was finalised"*) ok "L8 flags an edited final report" ;;
               *) bad "L8 should flag an edited final report" ;; esac
"$PY" - "$d/life/reports/weekly/w1.md" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read().replace("Rewritten text.\n", "")
open(p, "w").write(s + "\n## Amendment 2026-01-02\n\nA dated correction.\n")
PY
hc "$d" --life
case "$OUT" in *"PASS  L8"*) ok "L8 accepts a dated Amendment section" ;; *) bad "L8 should accept an Amendment" ;; esac

# ===========================================================================
group "fixture hygiene"
# ===========================================================================
leaks="$("$PY" - "$REPO_ROOT" <<'PY'
import json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
terms = set()
try:
    data = json.loads((root / ".core/config/accounts.json").read_text())
    terms |= set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", json.dumps(data)))
    terms |= {a for a in data.get("aliases", {}) if a not in
              {"personal", "work", "home", "main", "default", "family"}}
except (OSError, ValueError, AttributeError):
    pass
files = [root / ".claude/scripts/run-tests.sh"] + sorted((root / "tests/fixtures").rglob("*"))
for f in files:
    if not f.is_file() or f.name == "forbidden-terms.txt":
        continue
    text = f.read_text(errors="ignore").lower()
    if any(t.lower() in text for t in terms):
        print(f.relative_to(root))
PY
)"
if [ -z "$leaks" ]; then ok "no fixture contains an account email or alias from this machine"
else bad "fixtures contain a real account term: $leaks"; fi

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
