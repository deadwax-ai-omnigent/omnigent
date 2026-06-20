# Deadwax fork — working notes for Claude

This repo is a **branded fork** of [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent).
This file lives on the `deadwax` branch only; it is never contributed upstream.

## Remotes
- `origin`   → `deadwax-ai-omnigent/omnigent` (our org fork)
- `upstream` → `omnigent-ai/omnigent` (the OSS project)

If a fresh clone is missing `upstream`:
`git remote add upstream https://github.com/omnigent-ai/omnigent.git`

## Branch model
| Branch | Role | Rule |
|--------|------|------|
| `main` | Clean mirror of the latest **upstream release tag** (currently `v0.2.0`) | Never commit Deadwax changes here |
| `deadwax` | Our customizations as a **linear stack** on top of that release | All branding / themes / deploy live here |
| `<type>/<topic>` | Short-lived change branch → PR into `deadwax` | Delete after merge |

Tracking PR [**#1**](https://github.com/deadwax-ai-omnigent/omnigent/pull/1) (`deadwax` → `main`) is a permanently-open *living diff* of everything custom. **Do not merge it.**

No CI is wired up for our workflow — review and revert are manual by design. Upstream's own `.github/workflows/*` are left intact for upstream compatibility; don't depend on them running here.

## Make a customization (our repo)
```bash
git switch deadwax && git pull
git switch -c feat/my-change
# ...edit, commit...
git push -u origin feat/my-change
gh pr create -R deadwax-ai-omnigent/omnigent --base deadwax --head feat/my-change
# after review, squash-merge (keeps deadwax linear for clean rebases):
gh pr merge --squash --delete-branch
git switch deadwax && git pull
```
**Back out** a change: `git revert <sha>` on `deadwax` (or drop it during the next rebase), then push.

## Stay current with upstream releases
We track **tagged releases**, not dev `main`.
```bash
git fetch upstream --tags
# safety net before rewriting deadwax:
git branch -f deadwax-backup deadwax && git tag -f deadwax-pre-rebase deadwax
# move our mirror to the new release (e.g. vX.Y.Z):
git switch main && git merge --ff-only vX.Y.Z && git push origin main
# find the tag deadwax currently sits on, then replay our stack onto the new one:
git switch deadwax
git rebase --onto vX.Y.Z "$(git describe --tags --abbrev=0 @{1})" deadwax   # or pass OLDTAG explicitly
git push --force-with-lease origin deadwax
```
Resolve any conflicts by keeping upstream's functional change **and** reapplying our branding.

## Contribute a fix UPSTREAM (be a good OSS citizen)
Per the Omnigent maintainers (Discord):
1. **File an issue** describing the bug: https://github.com/omnigent-ai/omnigent/issues
2. **Open a PR from a fork branch** and reference the issue with `Fixes #N` / `Closes #N` in the body.
3. **Request a review** from a maintainer.

Branch from **`upstream/main`**, never from `deadwax`, so no branding/config leaks into the PR:
```bash
git fetch upstream
git switch -c fix/short-topic upstream/main
# ...minimal, focused fix that matches upstream style; no Deadwax-specific changes...
git push -u origin fix/short-topic
gh pr create -R omnigent-ai/omnigent --base main \
  --head deadwax-ai-omnigent:fix/short-topic \
  --title "fix: <summary>" --body "Fixes #N"
```
Keep it scoped to the issue and add/adjust tests as upstream expects. Once merged, it flows back to us via the normal release-rebase above — no need to also carry it on `deadwax`.
