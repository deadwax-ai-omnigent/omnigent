#!/usr/bin/env bash
#
# Deadwax upstream sync + deploy.
#
# Runs unattended on the machine that serves the Deadwax stack. One pass:
#
#   1. Ask upstream whether it has cut a newer STABLE release (vX.Y.Z; the
#      vX.Y.Z.devN daily tags are not releases and are ignored).
#   2. Point the clean `main` mirror at that release.
#   3. Replay the Deadwax stack (branding, themes, fork fixes) onto it.
#   4. Verify the result builds and passes the host test suite.
#   5. Publish `deadwax`, install it, restart the stack, prove it is healthy.
#   6. Roll back and file an issue if any of that fails.
#
# Every step is safe to re-run: with no new release the script exits 0 having
# changed nothing. The human is only pulled in when the replay conflicts —
# upstream restructured a file the fork also edits — which is the one judgment
# call that cannot be automated.
#
# The script never touches a developer working tree. It operates on its own
# clone (DEADWAX_SYNC_CLONE, default ~/.omnigent/sync-checkout) so an
# interrupted run can never leave your checkout mid-rebase.
#
# Usage:
#   sync.sh                 # full pass (what launchd runs)
#   sync.sh --dry-run       # report what it would do; no pushes, no deploy
#   sync.sh --no-deploy     # sync and publish, but leave the running stack alone
#   sync.sh --force-deploy  # deploy even while sessions are live (kills them)

set -euo pipefail

UPSTREAM_URL="https://github.com/omnigent-ai/omnigent.git"
FORK_SLUG="deadwax-ai-omnigent/omnigent"
FORK_URL="https://github.com/${FORK_SLUG}.git"
CLONE="${DEADWAX_SYNC_CLONE:-$HOME/.omnigent/sync-checkout}"
LOG_DIR="$HOME/.omnigent/logs"
LOG_FILE="$LOG_DIR/deadwax-sync.log"
LAUNCHD_LABEL="io.deadwax.omnigent-phone"
# The copy the scheduled job actually executes; kept in step with `deadwax`.
INSTALLED_COPY="$HOME/.omnigent/bin/deadwax-sync.sh"
HEALTH_URL="http://127.0.0.1:6767/health"
# How long the restarted stack gets to answer /health before we call it broken
# and roll back. The watchdog re-checks every 20s and the server's cold import
# is slow, so this is deliberately generous.
HEALTH_TIMEOUT_S=180
# Recovery refs older than this are pruned. Long enough to notice a bad sync
# weeks later, short enough that the branch list stays readable.
RECOVERY_KEEP_DAYS=90

# Host-local settings, kept OUT of this public repo. Currently just
# DEADWAX_NTFY_TOPIC — the ntfy.sh topic that pushes alarms to the phone.
# Without it the script still files its GitHub issue; it just cannot shout.
CONFIG_FILE="$HOME/.omnigent/deadwax-sync.env"
# shellcheck source=/dev/null
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

DRY_RUN=0
DEPLOY=1
FORCE_DEPLOY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-deploy) DEPLOY=0 ;;
    --force-deploy) FORCE_DEPLOY=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

run() {
  # Echo-and-execute, or echo-only under --dry-run. Used for every mutating
  # command so a dry run reads as an exact transcript of the real thing.
  if [[ $DRY_RUN -eq 1 ]]; then
    log "DRY-RUN would run: $*"
    return 0
  fi
  "$@"
}

die() {
  log "FAILED: $*"
  exit 1
}

# ── Alarms ────────────────────────────────────────────────────────
#
# Two channels with different jobs. The GitHub issue is the durable record —
# it holds the conflicted file list and survives until the work is done. The
# push is the interrupt: GitHub cannot notify you about issues your own token
# filed, so an issue alone is a message nobody receives.
#
# Only three events push: a conflicted rebase, a failed deploy, and a release
# successfully adopted. Nightly no-op runs are silent, which is what keeps the
# push worth reading.

notify() {
  local title="$1" body="$2" priority="${3:-default}"
  if [[ -z "${DEADWAX_NTFY_TOPIC:-}" ]]; then
    log "no DEADWAX_NTFY_TOPIC set; skipping push (see $CONFIG_FILE)"
    return 0
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    log "DRY-RUN would push: $title"
    return 0
  fi
  # Never let a notification failure take down a sync that otherwise worked.
  curl -sf --max-time 10 \
    -H "Title: $title" \
    -H "Priority: $priority" \
    -H "Tags: vinyl" \
    -d "$body" \
    "https://ntfy.sh/${DEADWAX_NTFY_TOPIC}" >/dev/null 2>&1 ||
    log "push notification failed (continuing)"
}

# One open issue per stuck release, reused rather than duplicated, so a month
# of failed nightly runs is one thread and not thirty.

issue_upsert() {
  local title="$1" body="$2" existing
  if [[ $DRY_RUN -eq 1 ]]; then
    log "DRY-RUN would file issue: $title"
    return 0
  fi
  existing="$(gh issue list --repo "$FORK_SLUG" --state open --limit 50 \
    --json number,title --jq ".[] | select(.title == \"$title\") | .number" | head -1)"
  if [[ -n "$existing" ]]; then
    gh issue comment "$existing" --repo "$FORK_SLUG" --body "$body" >/dev/null
    log "updated issue #$existing"
  else
    gh issue create --repo "$FORK_SLUG" --title "$title" --body "$body" >/dev/null
    log "filed issue: $title"
  fi
}

issue_close_for_tag() {
  # A landed sync closes its own alarm; nothing is more misleading than an open
  # "needs a human" issue for work that already shipped.
  local tag="$1" number
  [[ $DRY_RUN -eq 1 ]] && return 0
  for number in $(gh issue list --repo "$FORK_SLUG" --state open --limit 50 \
    --json number,title --jq ".[] | select(.title | contains(\"$tag\")) | .number"); do
    gh issue close "$number" --repo "$FORK_SLUG" \
      --comment "Synced and deployed automatically." >/dev/null || true
    log "closed issue #$number"
  done
}

# ── The sync clone ────────────────────────────────────────────────

ensure_clone() {
  # Deliberately NOT wrapped in `run`: preparing the private clone is
  # read-only as far as the outside world is concerned, and a --dry-run that
  # cannot read the repos cannot tell you anything useful.
  if [[ ! -d "$CLONE/.git" ]]; then
    log "creating sync clone at $CLONE"
    git clone --quiet "$FORK_URL" "$CLONE"
  fi
  git -C "$CLONE" remote get-url upstream >/dev/null 2>&1 ||
    git -C "$CLONE" remote add upstream "$UPSTREAM_URL"
  # The fork's own guardrail: this clone must never be able to push upstream.
  git -C "$CLONE" remote set-url --push upstream no_push

  # An interrupted run leaves a rebase in progress; clear it rather than
  # stacking a second one on top.
  if [[ -d "$CLONE/.git/rebase-merge" || -d "$CLONE/.git/rebase-apply" ]]; then
    log "clearing an interrupted rebase in the sync clone"
    git -C "$CLONE" rebase --abort || true
  fi
  git -C "$CLONE" fetch --quiet --prune origin
  git -C "$CLONE" fetch --quiet upstream 'refs/tags/v*:refs/tags/v*' --force
  git -C "$CLONE" checkout --quiet --detach origin/deadwax
}

latest_stable_tag() {
  # Newest vX.Y.Z, excluding prereleases (v0.10.0.dev20260817 and friends).
  git -C "$CLONE" tag --list 'v*' --sort=-version:refname |
    grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1
}

base_tag_of_deadwax() {
  # The release the Deadwax stack currently sits on: the newest stable tag that
  # is an ancestor of origin/deadwax. This is the rebase's "from", and reading
  # it from git rather than a recorded file means a hand-run sync can never
  # leave the automation pointed at the wrong base.
  local tag
  while read -r tag; do
    if git -C "$CLONE" merge-base --is-ancestor "$tag" origin/deadwax 2>/dev/null; then
      echo "$tag"
      return 0
    fi
  done < <(git -C "$CLONE" tag --list 'v*' --sort=-version:refname |
    grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$')
  return 1
}

# ── Verification gate ─────────────────────────────────────────────

verify_tree() {
  # Two questions, in the order they fail fastest: does the Python still work,
  # and does the branded web UI still compile? The second is the one that
  # matters for this fork — our changes are in the UI shell, so a clean-looking
  # rebase can still produce a build that no longer bundles.
  log "verifying the rebased tree (tests, then wheel build)"
  run uv sync --quiet --extra all --extra dev --directory "$CLONE" ||
    die "dependency install failed in the sync clone"
  run uv run --no-sync --directory "$CLONE" python -m pytest tests/host -q ||
    die "host test suite failed on the rebased tree"
  run uv build --quiet --wheel --directory "$CLONE" ||
    die "wheel build failed on the rebased tree (web UI likely broke in the rebase)"
  # The wheel was only ever a build check; leave no artifacts behind.
  run rm -rf "$CLONE/dist"
}

# ── Deploy ────────────────────────────────────────────────────────

installed_sha() {
  local info="$HOME/.local/share/uv/tools/omnigent/lib/python3.12/site-packages/omnigent/_build_info.py"
  [[ -f "$info" ]] || return 0
  sed -n "s/^COMMIT_SHA: str = '\(.*\)'$/\1/p" "$info"
}

sessions_are_live() {
  # A restart kills live agent sessions. Runner processes are the honest
  # signal: the zygote alone is idle capacity, a runner is somebody's work.
  pgrep -f 'omnigent\.runner\._entry' >/dev/null 2>&1
}

install_and_restart() {
  local ref="$1"
  run uv tool install --force --reinstall "git+file://$CLONE@$ref" ||
    return 1
  run launchctl kickstart -k "gui/$(id -u)/$LAUNCHD_LABEL" || return 1
  local waited=0
  while (( waited < HEALTH_TIMEOUT_S )); do
    if curl -sf --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 10
    waited=$(( waited + 10 ))
  done
  [[ $DRY_RUN -eq 1 ]] && return 0
  return 1
}

deploy() {
  local target_sha="$1" tag="$2" previous_sha
  previous_sha="$(installed_sha)"

  if [[ "$previous_sha" == "$target_sha" ]]; then
    log "already running $target_sha; nothing to deploy"
    return 0
  fi

  if sessions_are_live && [[ $FORCE_DEPLOY -eq 0 ]]; then
    # Deliberately not an error: the next run picks it up. Deploying over a
    # live session to hit a schedule is the wrong trade.
    log "sessions are live; deferring the deploy to the next run"
    return 0
  fi

  log "deploying $target_sha (was ${previous_sha:-unknown})"
  if install_and_restart "$target_sha"; then
    log "deploy healthy on $target_sha"
    return 0
  fi

  log "deploy of $target_sha failed its health check; rolling back"
  if [[ -n "$previous_sha" ]] && install_and_restart "$previous_sha"; then
    log "rolled back to $previous_sha"
  else
    log "ROLLBACK ALSO FAILED — the stack may be down"
  fi
  notify "Deadwax deploy failed" \
    "$tag built and tested fine, but the restart never came back healthy. Rolled back to the previous build. See the issue on the fork." \
    high
  issue_upsert "[upstream-sync] Deploy of $tag failed on the Deadwax host" \
    "Rebase onto \`$tag\` succeeded and passed verification, but installing
\`$target_sha\` left the stack unhealthy (no answer from \`$HEALTH_URL\` within
${HEALTH_TIMEOUT_S}s). Rolled back to \`${previous_sha:-unknown}\`.

See \`$LOG_FILE\` on the host."
  return 1
}

# ── Housekeeping ──────────────────────────────────────────────────

refresh_installed_copy() {
  # launchd runs a stable copy under ~/.omnigent/bin rather than a developer
  # working tree, whose branch at 04:00 is anybody's guess. Refreshing it from
  # the published `deadwax` keeps the scheduled job on the reviewed version.
  #
  # Done at the END of a run and via mv, never cp-in-place: a shell reads its
  # own script lazily, so overwriting the file it is executing corrupts the
  # run. mv swaps the inode, leaving this process on the old one.
  local src="$CLONE/scripts/deadwax/sync.sh"
  [[ -f "$src" ]] || return 0
  [[ $DRY_RUN -eq 1 ]] && { log "DRY-RUN would refresh $INSTALLED_COPY"; return 0; }
  cmp -s "$src" "$INSTALLED_COPY" 2>/dev/null && return 0
  mkdir -p "$(dirname "$INSTALLED_COPY")"
  cp "$src" "$INSTALLED_COPY.new" && chmod +x "$INSTALLED_COPY.new" &&
    mv -f "$INSTALLED_COPY.new" "$INSTALLED_COPY" &&
    log "refreshed the scheduled copy at $INSTALLED_COPY"
}

resweep_workflows() {
  # An upstream sync rewrites .github/workflows/*, which GitHub re-registers as
  # brand-new workflow IDs in state "active" — every inherited upstream job
  # (hourly demo checks, benchmarks, alert triage) silently switches itself
  # back on and starts billing. Nothing in this fork needs an Actions run, so
  # the sweep is unconditional. See docs/deadwax-github-actions.md.
  local id
  [[ $DRY_RUN -eq 1 ]] && { log "DRY-RUN would re-run the Actions disable sweep"; return 0; }
  for id in $(gh workflow list --repo "$FORK_SLUG" --all --limit 100 \
    --json id,name,state \
    --jq '.[] | select(.state=="active") | select(.name != "Dependency Graph") | .id'); do
    gh workflow disable "$id" --repo "$FORK_SLUG" >/dev/null 2>&1 &&
      log "re-disabled workflow $id" || true
  done
}

branch_is_absorbed() {
  # Is every commit on this branch already in deadwax? Two ways that happens:
  # the branch is a plain ancestor, or it was squash-merged — which rewrites
  # the commits, so ancestry says no while `git cherry` still recognises the
  # patches by content. Anything with an unapplied commit ("+") is somebody's
  # unfinished work and is left alone.
  local branch="$1"
  git -C "$CLONE" merge-base --is-ancestor "origin/$branch" origin/deadwax 2>/dev/null && return 0
  local unapplied
  unapplied="$(git -C "$CLONE" cherry origin/deadwax "origin/$branch" 2>/dev/null |
    grep -c '^+' || true)"
  [[ "$unapplied" == "0" ]]
}

prune_artifacts() {
  # Remote branches already folded into deadwax, and recovery refs old enough
  # that nobody is going back to them. Keeps the branch list a signal.
  local branch cutoff ref when
  [[ $DRY_RUN -eq 1 ]] && { log "DRY-RUN would prune merged and expired branches"; return 0; }

  while read -r branch; do
    [[ -z "$branch" ]] && continue
    # HEAD is origin's symbolic default-branch pointer, not a branch.
    case "$branch" in main|deadwax|HEAD|recovery/*) continue ;; esac
    if branch_is_absorbed "$branch"; then
      log "pruning merged branch $branch"
      git -C "$CLONE" push --quiet origin --delete "$branch" || true
    fi
  done < <(git -C "$CLONE" for-each-ref --format='%(refname:strip=3)' refs/remotes/origin)

  cutoff="$(date -v-${RECOVERY_KEEP_DAYS}d '+%Y%m%d' 2>/dev/null ||
    date -d "-${RECOVERY_KEEP_DAYS} days" '+%Y%m%d')"
  while read -r ref; do
    [[ -z "$ref" ]] && continue
    when="${ref##*-}"
    if [[ "$when" =~ ^[0-9]{8}$ ]] && [[ "$when" < "$cutoff" ]]; then
      log "pruning expired recovery ref $ref"
      git -C "$CLONE" push --quiet origin --delete "$ref" || true
    fi
  done < <(git -C "$CLONE" for-each-ref --format='%(refname:strip=3)' 'refs/remotes/origin/recovery/*')
}

# ── Main ──────────────────────────────────────────────────────────

main() {
  log "=== deadwax sync starting (dry_run=$DRY_RUN deploy=$DEPLOY) ==="
  command -v gh >/dev/null || die "gh CLI is required"
  command -v uv >/dev/null || die "uv is required"

  ensure_clone

  local latest base stamp recovery deadwax_sha
  latest="$(latest_stable_tag)" || die "no stable upstream release tag found"
  [[ -n "$latest" ]] || die "no stable upstream release tag found"
  base="$(base_tag_of_deadwax)" ||
    die "deadwax does not descend from any stable release tag; sync by hand"
  log "upstream latest stable: $latest   deadwax base: $base"

  if [[ "$latest" == "$base" ]]; then
    log "already on $latest; nothing to sync"
    # Still worth a deploy pass: a hand-merged fix on deadwax should reach the
    # box without waiting for upstream to cut a release.
    deadwax_sha="$(git -C "$CLONE" rev-parse origin/deadwax)"
    [[ $DEPLOY -eq 1 ]] && deploy "$deadwax_sha" "$base"
    prune_artifacts
    refresh_installed_copy
    log "=== done ==="
    return 0
  fi

  log "new release to adopt: $base -> $latest"
  stamp="$(date '+%Y%m%d')"
  recovery="recovery/deadwax-$stamp"

  # Recovery ref first: after this line the old stack is recoverable by name,
  # whatever the rebase does.
  run git -C "$CLONE" push --quiet --force origin "origin/deadwax:refs/heads/$recovery"
  log "recovery ref pushed: $recovery"

  # The clean mirror. Force-with-lease so a concurrent hand-sync is not
  # silently clobbered.
  run git -C "$CLONE" push --quiet \
    --force-with-lease="refs/heads/main:$(git -C "$CLONE" rev-parse origin/main)" \
    origin "$latest:refs/heads/main"
  log "main now mirrors $latest"

  # The replay. --onto takes every commit after the OLD release tag and lands
  # it on the new one; those commits are the whole Deadwax fork.
  # The rebase itself is local to the private clone, so it runs even under
  # --dry-run: "would this replay cleanly?" is the whole question a dry run
  # exists to answer.
  git -C "$CLONE" checkout --quiet -B deadwax-sync origin/deadwax
  if ! git -C "$CLONE" rebase --onto "$latest" "$base" deadwax-sync; then
    local conflicts
    conflicts="$(git -C "$CLONE" diff --name-only --diff-filter=U | sed 's/^/- /')"
    git -C "$CLONE" rebase --abort || true
    notify "Deadwax sync needs you" \
      "Upstream released $latest, but replaying the Deadwax commits onto it hit conflicts. Nothing was published and the host is untouched. Details in the issue on the fork." \
      high
    issue_upsert "[upstream-sync] Rebase Deadwax onto $latest needs a human" \
      "Upstream released **$latest** (the fork sits on \`$base\`). The clean
\`main\` mirror has been updated and \`origin/$recovery\` holds the pre-sync
\`deadwax\`, but replaying the Deadwax commits hit conflicts:

$conflicts

Nothing was published — \`deadwax\` is untouched and the host still runs its
current build. Resolve with:

\`\`\`
git fetch upstream 'refs/tags/v*:refs/tags/v*' --force
git checkout -B deadwax-sync origin/deadwax
git rebase --onto $latest $base deadwax-sync
\`\`\`

Keep upstream's behaviour, port the Deadwax branding into whatever the UI
looks like now, then force-with-lease \`deadwax\` and re-run \`sync.sh\`."
    die "rebase onto $latest conflicted; issue filed, nothing published"
  fi

  log "rebase applied cleanly"
  if [[ $DRY_RUN -eq 1 ]]; then
    log "DRY-RUN: skipping verification, publish and deploy"
    log "=== dry run complete: $latest would replay onto the fork cleanly ==="
    return 0
  fi

  verify_tree

  deadwax_sha="$(git -C "$CLONE" rev-parse HEAD)"
  run git -C "$CLONE" push --quiet \
    --force-with-lease="refs/heads/deadwax:$(git -C "$CLONE" rev-parse origin/deadwax)" \
    origin "deadwax-sync:refs/heads/deadwax"
  log "deadwax published on $latest ($deadwax_sha)"

  if [[ $DEPLOY -eq 1 ]]; then
    deploy "$deadwax_sha" "$latest" || die "deploy failed; see the filed issue"
  else
    log "--no-deploy: leaving the running stack alone"
  fi

  issue_close_for_tag "$latest"
  resweep_workflows
  prune_artifacts
  refresh_installed_copy
  notify "Deadwax updated to $latest" \
    "Rebased, tested, deployed and healthy. The stack is running $latest with the Deadwax branding intact."
  log "=== done: Deadwax is on $latest ==="
}

main "$@"
