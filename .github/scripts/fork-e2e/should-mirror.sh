#!/usr/bin/env bash
# Decides whether a fork PR's head commit should be mirrored onto the trusted
# fork-e2e/pr-N branch (which lets e2e run as a `push` with the test-gateway
# secrets). Called by .github/workflows/fork-e2e-mirror.yml.
#
# Gate: the PR has an approving review from a maintainer (in
# .github/MAINTAINER@main). We read the latest non-COMMENTED review state per
# reviewer and check if any approver is a maintainer -- the same semantics as
# maintainer-approval.yml. GitHub only lets Triage+ users apply labels, but
# reviews are even more constrained: only users with write access can submit
# approving reviews on a fork PR, so the maintainer check here is defence in
# depth.
#
# New commits while the approval is present re-mirror automatically (this
# script re-runs on `synchronize`); the security scan plus the maintainer's
# review are the safety net for post-approval pushes. Requesting changes or
# dismissing the review stops future mirrors (this script re-runs and finds no
# approving maintainer review). Closing the PR deletes the mirror branch --
# see the workflow.
#
# Fail closed: any error or unexpected state leaves the gate shut, so secrets
# never run on an unverified PR.
#
# Env in:  GH_TOKEN, REPO, PR,
#          MAINTAINERS (space-separated, from merge-ready/load-maintainers.sh).
# Out:     `mirror=true|false` and `reason=<text>` on $GITHUB_OUTPUT.

set -euo pipefail

emit() {
  echo "mirror=$1" >> "$GITHUB_OUTPUT"
  echo "reason=$2" >> "$GITHUB_OUTPUT"
  echo "mirror=$1 ($2)"
}

MAINTAINERS_LC=$(echo "${MAINTAINERS:-}" | tr '[:upper:]' '[:lower:]')

if [[ -z "${MAINTAINERS_LC// /}" ]]; then
  emit false "no maintainers loaded (.github/MAINTAINER@main empty/missing)"
  exit 0
fi

# Find approvers: latest non-COMMENTED review per user, keep those with
# APPROVED state. Matches maintainer-approval.yml semantics: COMMENTED does
# not supersede APPROVED; CHANGES_REQUESTED and DISMISSED do.
APPROVERS=$(gh api "repos/$REPO/pulls/$PR/reviews" --paginate \
  --jq '[.[] | select(.state != "COMMENTED")] | group_by(.user.login) | map(max_by(.submitted_at)) | .[] | select(.state == "APPROVED") | .user.login')

if [[ -z "$APPROVERS" ]]; then
  emit false "awaiting approval from a maintainer"
  exit 0
fi

for u in $APPROVERS; do
  u_lc=$(echo "$u" | tr '[:upper:]' '[:lower:]')
  for m in $MAINTAINERS_LC; do
    if [[ "$m" == "$u_lc" ]]; then
      emit true "approved by maintainer @$u"
      exit 0
    fi
  done
done

emit false "no approving review from a maintainer"
