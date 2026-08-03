#!/usr/bin/env bash
# PreToolUse(Bash) guard: refuse commands that publish to any repo outside the
# Deadwax fork.
#
# `gh pr create` inside a fork defaults to the UPSTREAM parent, so an agent can
# open a public PR on omnigent-ai/omnigent without ever naming it. This requires
# the fork to be named explicitly, and blocks direct pushes to `upstream`.
#
# Matching is anchored to a shell command position, and backtick-quoted spans
# are stripped first, so prose that merely mentions these commands (a commit
# message, a doc edit) is not mistaken for running them.
#
# Exit 2 = block the tool call and show stderr to the agent.

set -uo pipefail

FORK="deadwax-ai-omnigent/omnigent"

payload=$(cat)
if command -v jq >/dev/null 2>&1; then
  cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // ""' 2>/dev/null)
else
  cmd="$payload"
fi
[ -z "$cmd" ] && exit 0

# Drop backtick-quoted spans (markdown references, not invocations).
scan=$(printf '%s' "$cmd" | sed 's/`[^`]*`//g')

# A command position: start of a line, or just after ; & | ( or &&/||.
AT_CMD='(^|[;&|(])[[:space:]]*'

deny() {
  printf 'BLOCKED by .claude/hooks/block-upstream-writes.sh\n\n%s\n\n%s\n' "$1" \
    "See AGENTS.md -> \"Never send anything upstream without explicit approval\".
Ask the repository owner first. If they approve, they run the command themselves." >&2
  exit 2
}

# Creating or commenting on PRs/issues must name the fork explicitly.
if printf '%s' "$scan" | grep -qE "${AT_CMD}gh[[:space:]]+(pr|issue)[[:space:]]+(create|comment)\b"; then
  printf '%s' "$scan" | grep -qF -- "--repo $FORK" \
    || deny "This publishes a PR/issue/comment without an explicit '--repo $FORK'.
In a fork, gh targets the upstream parent by default, so this may post publicly
to omnigent-ai/omnigent under the owner's name."
fi

# Never push straight into upstream. `upstream` must be its own argument — a
# branch named e.g. block-upstream-writes is not a remote.
if printf '%s' "$scan" | grep -qE "${AT_CMD}git[[:space:]]+push\b[^|;&]*[[:space:]]upstream([[:space:]]|$)"; then
  deny "This pushes directly to the 'upstream' remote (omnigent-ai/omnigent)."
fi

# Write-method API calls against upstream.
if printf '%s' "$scan" | grep -qE "${AT_CMD}gh[[:space:]]+api\b" \
  && printf '%s' "$scan" | grep -qE '(-X|--method)[[:space:]]+(POST|PATCH|PUT|DELETE)' \
  && printf '%s' "$scan" | grep -qF 'omnigent-ai/omnigent'; then
  deny "This is a write request to the upstream repository's API."
fi

exit 0
