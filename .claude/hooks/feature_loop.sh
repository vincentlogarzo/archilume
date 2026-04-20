#!/usr/bin/env bash
# PostToolUse hook for /feature TDD loop.
#
# Reads tool-use JSON on stdin, checks whether the edited file is tied to an
# active feature tracked under .claude/features/, runs that feature's test
# file, and emits a JSON hook response instructing the main agent to invoke
# the reflex-audit subagent on the diff.
#
# Exits 0 unconditionally — never blocks the user's workflow. If no feature
# is active, emits nothing and is silent.

set -u

payload="$(cat)"

file_path="$(echo "$payload" | jq -r '.tool_input.file_path // empty')"
if [ -z "$file_path" ]; then
    exit 0
fi

# Only act on files inside archilume_app/ — hook should be cheap elsewhere.
case "$file_path" in
    *archilume_app*) ;;
    *) exit 0 ;;
esac

repo_root="$(git -C "$(dirname "$file_path")" rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -z "$repo_root" ]; then
    exit 0
fi

features_dir="$repo_root/.claude/features"
if [ ! -d "$features_dir" ]; then
    exit 0
fi

# Find every feature tracking file that either (a) lists the edited file under
# "Target files" or (b) has a test file matching the edited file's basename.
relevant=()
base="$(basename "$file_path")"
slug_base="${base%.py}"
for feat in "$features_dir"/*.md; do
    [ -f "$feat" ] || continue
    if grep -qF "$base" "$feat" 2>/dev/null; then
        relevant+=("$feat")
    fi
done

if [ "${#relevant[@]}" -eq 0 ]; then
    exit 0
fi

# For each relevant feature, run its test file. Accumulate summaries.
summaries=""
audit_requests=""
for feat in "${relevant[@]}"; do
    slug="$(basename "$feat" .md)"
    test_file="archilume/apps/archilume_app/tests/test_${slug}.py"
    if [ ! -f "$repo_root/$test_file" ]; then
        continue
    fi
    pytest_out="$(cd "$repo_root" && uv run pytest "$test_file" --confcutdir=archilume/apps/archilume_app/tests -x --tb=short 2>&1 || true)"
    tail_out="$(echo "$pytest_out" | tail -n 20)"
    summaries+="\n\n### Feature: $slug\n\n\`\`\`\n$tail_out\n\`\`\`"
    audit_requests+="\n- $slug → invoke reflex-audit with file=$file_path, diff=\`git diff HEAD -- $file_path\`, spec=\`.claude/features/$slug.md\`"
done

if [ -z "$summaries" ]; then
    exit 0
fi

# Build the additionalContext string. jq -Rs reads raw stdin into one string,
# preserving newlines and escaping quotes — avoids hand-rolled JSON escaping.
context="## /feature loop hook fired

Edited: $file_path

### Pytest results$summaries

### Next actions
1. Review pytest output. If red → fix failures first.
2. If green → invoke the reflex-audit subagent for each feature below:$audit_requests
3. After audit, parse \`SCORE: X/10\`. Loop if < 9/10. Exit if ≥ 9/10 AND all tests green.
4. Append the audit report to the feature's tracking file under a \`## Audit <N>\` heading."

jq -Rsc --null-input \
    --arg ctx "$context" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$ctx}}' \
    < /dev/null

exit 0
