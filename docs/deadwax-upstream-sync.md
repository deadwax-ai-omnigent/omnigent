# Keeping Deadwax up to date with upstream

> Fork-only doc (lives on the `deadwax` branch; never contributed upstream).

## The shape of the problem

Upstream (`omnigent-ai/omnigent`) publishes releases. Deadwax is those releases
plus our own commits — branding, theme, fork fixes. Our commits are *edits to
their files*, not additions alongside them, so adopting a release means
replaying our commits on top of the new one. That replay is a `git rebase`, and
it is the only part of this that can need a human: when upstream restructures a
file we also changed, git stops and asks which version wins.

Three branches carry the whole model:

| Branch | What it is |
|---|---|
| `main` | A pristine mirror of the latest upstream **stable** release. Nobody edits it; it exists so you can always diff against untouched upstream. |
| `deadwax` | The product. That release plus our commits. This is what gets installed and served. Also the repo's default branch, so scheduled work runs from it. |
| `recovery/deadwax-YYYYMMDD` | A snapshot of `deadwax` taken immediately before each sync rewrites it. Pruned after 90 days. |

Upstream's `vX.Y.Z.devN` tags are daily builds, not releases. We ignore them
and track `vX.Y.Z` only.

## What runs automatically

`scripts/deadwax/sync.sh`, daily at 04:00 via the `io.deadwax.omnigent-sync`
launchd job on the host that serves Deadwax. Daily rather than weekly because
the pass costs nothing when there is no new release, and a release should reach
the host within a day.

It runs on its own clone (`~/.omnigent/sync-checkout`) and never touches a
developer working tree. One pass:

1. **Look.** Newest upstream stable tag vs. the tag `deadwax` currently sits on
   (computed from git, so a hand-run sync can't leave the automation confused).
   Same? Exit, having done nothing but a deploy check.
2. **Snapshot.** Push `recovery/deadwax-<date>` so the pre-sync stack is
   recoverable by name no matter what follows.
3. **Mirror.** Move `main` to the new release tag.
4. **Replay.** `git rebase --onto <new-tag> <old-tag>` — the Deadwax commits
   onto the new release.
5. **Verify.** Install deps, run `tests/host`, and build the wheel. The wheel
   build compiles the web UI, which is where our branding lives — a rebase can
   apply cleanly and still break the bundle, and this is what catches that.
6. **Publish.** Force-with-lease `deadwax`.
7. **Deploy.** Install the new build, restart the stack, poll `/health`. If it
   doesn't come back, reinstall the previous commit and file an issue.
8. **Tidy.** Re-run the Actions disable sweep (a sync re-registers upstream's
   workflows as active), delete remote branches already merged into `deadwax`,
   drop recovery refs older than 90 days.

Nothing is published unless the replay was clean *and* verification passed. A
conflict stops at step 4 with `deadwax` untouched and the host still on its
current build.

### When it needs you

Two channels, because they do different jobs. A **push notification** is the
interrupt; the **GitHub issue** is the durable record holding the conflicted
file list until the work is done.

The push exists because the issue alone reaches nobody: the script
authenticates as the repo owner, and GitHub never notifies you about your own
activity. An issue filed by your own token is a silent issue.

Pushes go through [ntfy.sh](https://ntfy.sh) to a private topic held in
`~/.omnigent/deadwax-sync.env` (mode 600, never committed — the topic is an
unlisted URL and anyone who knows it can read the alerts). Subscribe to that
topic in the ntfy iOS app. Without the file the sync still runs and still files
issues; it just cannot shout. Only three events push — conflicted rebase,
failed deploy, release adopted — so a push always means something happened.

It files a GitHub issue on this fork titled
`[upstream-sync] Rebase Deadwax onto vX.Y.Z needs a human`, listing the
conflicted files and the exact commands to reproduce the rebase. Resolve by
keeping upstream's behaviour and porting the Deadwax branding into whatever the
UI looks like now, force-with-lease `deadwax`, then re-run `sync.sh`. The issue
closes itself on the next successful pass.

A failed deploy files
`[upstream-sync] Deploy of vX.Y.Z failed on the Deadwax host` instead, after
rolling back.

## Running it by hand

```bash
scripts/deadwax/sync.sh --dry-run
```

Reads both repos, attempts the rebase locally, and reports what it would do —
no pushes, no deploy. This is the safe way to answer "would the next release
land cleanly?"

```bash
scripts/deadwax/sync.sh
```

The real pass. Add `--no-deploy` to publish without touching the running stack,
or `--force-deploy` to restart even while sessions are live (it defers by
default — a restart kills live agent sessions).

Transcript: `~/.omnigent/logs/deadwax-sync.log`.

## Installing the schedule

```bash
cp scripts/deadwax/io.deadwax.omnigent-sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.deadwax.omnigent-sync.plist
```

The job runs `~/.omnigent/bin/deadwax-sync.sh`, a stable copy rather than the
working tree — an unattended 04:00 job must not depend on which branch someone
left checked out. Each successful run refreshes that copy from the published
`deadwax`, so the schedule stays on reviewed code without anyone remembering to
reinstall it.

Check on it with `launchctl print gui/$(id -u)/io.deadwax.omnigent-sync`.

## Why this is not a GitHub Action

It was one, and it never worked. Two structural reasons, both worth
remembering before someone moves it back:

- **Actions can't deploy here.** The stack runs on a Mac on a tailnet. GitHub
  can publish `deadwax` but cannot install or restart anything, so the cloud
  half would always need a second local half anyway.
- **`GITHUB_TOKEN` can't push workflow files.** Upstream releases routinely
  change `.github/workflows/*`, and GitHub rejects those pushes from the
  built-in token — there is no `workflows:` key you can add to `permissions:`.
  It needs a human-created PAT with the `workflow` scope, stored as a secret,
  and rotated forever.

The host already has a credential with that scope, has to do the deploy
regardless, and runs the tests on the machine whose behaviour we actually care
about. One job, no secrets, no Actions minutes.

## Never send anything upstream

Unchanged and unconditional — see `CLAUDE.md`. The sync clone sets its
`upstream` push URL to `no_push`, so even this automation cannot write to
`omnigent-ai/omnigent`.
