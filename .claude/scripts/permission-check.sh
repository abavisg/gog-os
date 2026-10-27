#!/usr/bin/env bash
# Copied from ClientOS (client-os, .claude/scripts/permission-check.sh); changed only by this line and the --help range.
# .claude/scripts/permission-check.sh: would this command prompt, and which rule decides?
#
# READ-ONLY BY CONTRACT. This script never edits a settings file, and must not
# be given the ability to. Granting permissions without the owner reading them
# is the failure this exists to prevent, not to automate: a tool that repairs
# the permission file is a tool that widens the assistant's own rights
# unattended. It reports; the human edits. (ARCHITECTURE.md section 15.)
#
# The deny -> ask -> allow ordering is genuinely unintuitive, and two properties
# surprise people often enough to be worth a tool:
#
#   - Order beats specificity. A broad ask wins over a narrow allow, so
#     Bash(git tag *) can be allowed while "git tag -d v1" still prompts. That
#     is what lets the allowlist be generous without weakening the gates.
#   - A trailing * matches the bare command ONLY when a space precedes it.
#     Bash(git push*) matches "git push --force" but NOT a plain "git push".
#
# Usage: permission-check.sh [--porcelain] <command> [<command>...]
#        permission-check.sh --audit [--porcelain]
#        permission-check.sh --help
#
#   (default)    explain the verdict for each command given
#   --audit      check the whole ruleset for the known failure modes
#   --porcelain  VERDICT<TAB>RULE<TAB>COMMAND lines, for other scripts
#
# Rules are merged the way Claude Code merges them, most specific last:
#   ~/.claude/settings.json  <  .claude/settings.json  <  .claude/settings.local.json
#
# EXIT CODES: 0 every command allowed / audit clean · 1 something prompts,
#             is denied, or the audit found a problem · 2 usage error
# Written for bash 3.2 (macOS default).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PORCELAIN=0
AUDIT=0
CMDS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --porcelain) PORCELAIN=1; shift ;;
    --audit)     AUDIT=1; shift ;;
    --help|-h)   sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --*)         echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    *)           CMDS="$CMDS$1"$'\n'; shift ;;
  esac
done

if [ "$AUDIT" -eq 0 ] && [ -z "$CMDS" ]; then
  echo "give a command to check, or --audit (try --help)" >&2; exit 2
fi

# All matching logic lives in one Python helper. It is written to a temp file
# rather than inlined in $(...): a pattern like `*)` inside a heredoc closes the
# command substitution early under bash 3.2, which broke run-tests.sh once.
HELPER="$(mktemp "${TMPDIR:-/tmp}/permcheck.XXXXXX")"
trap 'rm -f "$HELPER"' EXIT
cat > "$HELPER" <<'PY'
import json, os, sys, fnmatch

repo, mode, porcelain = sys.argv[1], sys.argv[2], sys.argv[3] == "1"

# Least specific first; later files win, matching Claude Code's own precedence.
SOURCES = [
    (os.path.expanduser("~/.claude/settings.json"), "user"),
    (os.path.join(repo, ".claude/settings.json"), "project"),
    (os.path.join(repo, ".claude/settings.local.json"), "local"),
]

rules = {"deny": [], "ask": [], "allow": []}
origin = {}          # rule text -> which file it came from
loaded = []
for path, label in SOURCES:
    if not os.path.exists(path):
        continue
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (ValueError, OSError) as exc:
        print("could not read %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(2)
    perms = data.get("permissions", {})
    loaded.append(label)
    for key in rules:
        for r in perms.get(key, []):
            rules[key].append(r)
            origin.setdefault((key, r), label)


def split_segments(cmd):
    """Claude Code splits compound commands and matches each part independently.
    Separators: && || ; | |& & and newlines."""
    out, buf, i = [], "", 0
    while i < len(cmd):
        two = cmd[i:i + 2]
        if two in ("&&", "||", "|&"):
            out.append(buf); buf = ""; i += 2; continue
        if cmd[i] in ";|&\n":
            out.append(buf); buf = ""; i += 1; continue
        buf += cmd[i]; i += 1
    out.append(buf)
    return [s.strip() for s in out if s.strip()]


# Stripped before matching. `bash` is deliberately NOT here: that is why
# "bash foo.sh" and "./foo.sh" need separate rules.
WRAPPERS = ("timeout", "time", "nice", "nohup", "stdbuf", "command",
            "builtin", "noglob")


def strip_wrappers(cmd):
    parts = cmd.split()
    while parts and parts[0] in WRAPPERS:
        parts = parts[1:]
        # skip a wrapper's own options/arguments (timeout 30 npm test)
        while parts and (parts[0].startswith("-") or parts[0].isdigit()):
            parts = parts[1:]
    return " ".join(parts) if parts else cmd


def rule_matches(cmd, inner):
    if fnmatch.fnmatchcase(cmd, inner):
        return True
    # A lone trailing " *" also matches the bare command.
    if inner.endswith(" *") and inner.count("*") == 1 and cmd == inner[:-2]:
        return True
    return False


def find(cmd, key):
    for r in rules[key]:
        if not (r.startswith("Bash(") and r.endswith(")")):
            continue
        if rule_matches(cmd, r[5:-1]):
            return r
    return None


def verdict(segment):
    """deny -> ask -> allow, first match wins. Order beats specificity."""
    c = strip_wrappers(segment)
    for key, name in (("deny", "DENY"), ("ask", "ASK"), ("allow", "ALLOW")):
        hit = find(c, key)
        if hit:
            return name, hit, origin.get((key, hit), "?")
    return "PROMPT", None, None


def check(cmd):
    """A compound command is only as permitted as its least-permitted segment."""
    segs = split_segments(cmd)
    worst, rank = None, -1
    order = {"ALLOW": 0, "PROMPT": 1, "ASK": 2, "DENY": 3}
    for s in segs:
        v, rule, src = verdict(s)
        if order[v] > rank:
            rank, worst = order[v], (v, rule, src, s)
    return worst, segs


if mode == "audit":
    problems = 0

    # 1. A glued trailing * in ask/deny lets the bare command escape.
    glued = []
    for key in ("ask", "deny"):
        for r in rules[key]:
            if not (r.startswith("Bash(") and r.endswith("*)")):
                continue
            inner = r[5:-1]
            if inner.count("*") == 1 and not inner.endswith(" *"):
                glued.append((key, r))
    if glued:
        problems += len(glued)
        if not porcelain:
            print("  ISSUE  %d ask/deny rule(s) whose trailing * is glued, so the"
                  " bare command escapes the gate:" % len(glued))
            for key, r in glued[:10]:
                print("           %-5s %s   -> should be %s"
                      % (key, r, r[:-2] + " *)"))
        else:
            for key, r in glued:
                print("GLUED\t%s\t%s" % (key, r))
    elif not porcelain:
        print("  ok     every single-wildcard ask/deny rule matches its bare command")

    # 2. Allow rules in settings.local.json reach no other instance, and a
    #    local allow widens the assistant's rights invisibly. Local ask/deny
    #    rules are the opposite failure mode: they only narrow, and the
    #    gitignored file is the only legitimate home for engagement-specific
    #    gates, which must never enter the client-agnostic tracked file.
    n_local = sum(1 for r in rules["allow"]
                  if origin.get(("allow", r)) == "local")
    n_gates = sum(1 for key in ("ask", "deny") for r in rules[key]
                  if origin.get((key, r)) == "local")
    if n_local:
        problems += 1
        if porcelain:
            print("LOCAL_RULES\t%d" % n_local)
        else:
            print("  ISSUE  %d allow rule(s) live in settings.local.json,"
                  " which is gitignored" % n_local)
            print("           No other instance can see them and a fresh clone"
                  " loses them.")
            print("           Move any the system needs into"
                  " .claude/settings.json.")
    elif not porcelain:
        print("  ok     no allow rules stranded in the gitignored"
              " settings.local.json")
    if n_gates and not porcelain:
        print("  ok     %d instance-local ask/deny rule(s) in"
              " settings.local.json (deny only narrows; client-specific"
              " gates belong here)" % n_gates)

    # 3. Every directly-invoked script needs a rule under each prefix used.
    sdir = os.path.join(repo, ".claude/scripts")
    missing = []
    if os.path.isdir(sdir):
        for name in sorted(os.listdir(sdir)):
            if not name.endswith(".sh") or name.startswith("_"):
                continue
            if not find(".claude/scripts/" + name, "allow"):
                missing.append(name)
    if missing:
        problems += len(missing)
        if porcelain:
            for m in missing:
                print("NO_RULE\t%s" % m)
        else:
            print("  ISSUE  %d script(s) with no allow rule: %s"
                  % (len(missing), " ".join(missing)))
    elif not porcelain:
        print("  ok     every directly-invoked script in .claude/scripts/ has a rule")

    if not porcelain:
        print()
        print("  sources merged: %s" % (", ".join(loaded) or "none"))
        print("  rules: %d deny, %d ask, %d allow"
              % (len(rules["deny"]), len(rules["ask"]), len(rules["allow"])))
    sys.exit(1 if problems else 0)

# --- explain mode ---------------------------------------------------------
worst_rank = 0
order = {"ALLOW": 0, "PROMPT": 1, "ASK": 2, "DENY": 3}
for line in sys.stdin.read().split("\n"):
    cmd = line.strip()
    if not cmd:
        continue
    (v, rule, src, seg), segs = check(cmd)
    worst_rank = max(worst_rank, order[v])
    if porcelain:
        print("%s\t%s\t%s" % (v, rule or "-", cmd))
        continue

    label = {"ALLOW": "runs unattended", "ASK": "PROMPTS",
             "DENY": "BLOCKED", "PROMPT": "PROMPTS (no rule matches)"}[v]
    print("  %-8s %s" % (v, cmd))
    print("           %s" % label)
    if rule:
        print("           matched %s   [%s]" % (rule, src))
        if v == "ALLOW":
            pass
        else:
            print("           deny and ask are checked before allow, so this"
                  " wins even if an allow rule also matches.")
    else:
        print("           No rule in any settings file matches it. Approving the"
              " prompt would write a rule")
        print("           to .claude/settings.local.json, which is gitignored"
              " and reaches no other instance.")
    if len(segs) > 1:
        print("           compound command, %d segments; the verdict is the"
              " least-permitted one (%s)" % (len(segs), seg))
    print()

sys.exit(1 if worst_rank > 0 else 0)
PY

if [ "$AUDIT" -eq 1 ]; then
  [ "$PORCELAIN" -eq 1 ] || echo "-- Permission ruleset audit --"
  printf '' | python3 "$HELPER" "$REPO_ROOT" audit "$PORCELAIN"
  exit $?
fi

printf '%s' "$CMDS" | python3 "$HELPER" "$REPO_ROOT" explain "$PORCELAIN"
exit $?
