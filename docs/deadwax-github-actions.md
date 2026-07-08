# Deadwax fork — GitHub Actions cost control

> Fork-only doc (lives on the `deadwax` branch; never contributed upstream).
> Companion to [`CLAUDE.md`](../CLAUDE.md) → "Branch model".

## Why

We inherit **all** of upstream's `.github/workflows/*`. On our fork's default
branch (`deadwax`) GitHub was auto-running them — most importantly the **daily
scheduled suites `E2E Tests`, `E2E UI Tests`, and `Integration Tests`**, which
exercise a live LLM gateway. Every day they **failed / timed out**, burning
GitHub Actions minutes **and LLM tokens** for zero signal:

- Our fork is **frontend-only** (branding / themes / deploy — see
  [`scripts/deadwax-deploy.sh`](../scripts/deadwax-deploy.sh)). We don't change
  the Python runtime those suites test.
- Upstream already runs all of these on every release.
- Beyond the daily suites, `CI` / `Lint` / `ap-web Tests` fire on every
  `push origin main` (i.e. each weekly sync), and PR workflows — including the
  token-spending **`Polly AI Review`** — fire on any PR opened into `deadwax`.

Per `CLAUDE.md`, **"No CI is wired up for our workflow — by design."** So to stay
within budget for the Deadwax project, we **disabled every workflow on the fork
except one**, at the repo level (not via file edits).

## Current state

**Disabled: 2026-07-08.** Method: `gh workflow disable` on every workflow except
`Fork e2e mirror`. This is a **repo-level** setting (`disabled_manually`), so it
is **independent of branch content and survives the weekly rebase / force-push**
— no need to redo it on every upstream sync.

**Still active (2):**

| Workflow | Why it's still active |
|---|---|
| `Fork e2e mirror` (`.github/workflows/fork-e2e-mirror.yml`) | Intentionally kept (our chosen exception). Note: it's an upstream-maintainer mechanism and won't do anything meaningful on the fork, but we left it enabled by choice. |
| `Dependency Graph` (`dynamic/dependabot/update-graph`) | **Not** a real Actions workflow — GitHub's built-in Dependabot dependency-graph updater. Runs on GitHub's own infra, **consumes zero Actions minutes and zero LLM tokens**, and the Actions API can't disable it. Left as-is (harmless). Disable via repo **Settings → Code security** if ever desired. |

**Disabled (35):**
`Auto-assign Reviewer`, `Auto-assign Reviewer Test`, `CI`, `Close stale issues`,
`Code Coverage`, `Duplicate PRs`, `Duplicate PRs Test`, `E2E Tests`,
`E2E UI Required`, `E2E UI Tests`, `Flake stress`, `Flake stress (E2E)`,
`GitHub Release`, `Integration Tests`, `Issue Triage`, `Lint`,
`Maintainer Approval`, `Maintainer Approval Rerun`,
`Maintainer Approval Rerun Run`, `Merge Ready`, `OSS Scorecard`,
`OSS regenerate lockfiles + smoke`, `OSS regenerate lockfiles on /regen comment`,
`PR Autoformat`, `PR Size Labeling`, `Polly AI Review`,
`Polly Review Approval Dispatch`, `Polly Review On Approval`,
`Publish images (public)`, `Release omnigent (PyPI)`, `Rerun Security Gate`,
`Rerun Security Gate Run`, `Security Gate`, `Security Scan`, `ap-web Tests`.

## Check the current state

```bash
FORK=deadwax-ai-omnigent/omnigent
# Human-readable list of every workflow + state (active / disabled_manually):
gh workflow list --repo "$FORK" --all
# Just the ones still active:
gh api --paginate "repos/$FORK/actions/workflows" \
  -q '.workflows[] | select(.state=="active") | .name'
```

## Re-enable

```bash
FORK=deadwax-ai-omnigent/omnigent

# Re-enable ONE workflow (by name or by its .yml filename):
gh workflow enable "E2E Tests" --repo "$FORK"

# Re-enable EVERYTHING:
gh api --paginate "repos/$FORK/actions/workflows" -q '.workflows[].id' \
  | while read -r id; do
      gh api -X PUT "repos/$FORK/actions/workflows/$id/enable" >/dev/null 2>&1 \
        && echo "enabled $id"
    done
```

> Re-enabling `CI` / `Lint` / `ap-web Tests` / the daily suites brings the
> Actions-minute + LLM-token spend back. Re-enable selectively.

## Re-disable (repeat the sweep)

Run this to disable everything again except `Fork e2e mirror`. **Do this after a
major upstream sync**, because any *brand-new* workflow file an upstream release
adds will land in state `active` by default:

```bash
FORK=deadwax-ai-omnigent/omnigent
KEEP="Fork e2e mirror"
gh api --paginate "repos/$FORK/actions/workflows" \
  -q '.workflows[] | "\(.id)\t\(.state)\t\(.name)"' \
  | while IFS=$'\t' read -r id state name; do
      [ "$name" = "$KEEP" ] && { echo "KEEP  $name"; continue; }
      [ "$state" != "active" ] && continue
      gh api -X PUT "repos/$FORK/actions/workflows/$id/disable" >/dev/null 2>&1 \
        && echo "disabled $name" || echo "SKIP (cannot disable) $name"
    done
```

(`Dependency Graph` will report `SKIP (cannot disable)` — expected and harmless.)

## Notes

- **Upstream is unaffected.** `omnigent-ai/omnigent` is a separate repo with its
  own Actions; disabling on our fork changes nothing there.
- **Disabled workflows don't fire on any trigger** — schedule, push, PR, or
  `workflow_dispatch`. To run one manually you must re-enable it first.
- We deliberately chose the repo-level disable over per-file `if:` guards on the
  workflow YAML: the disable covers **all** workflows (not just the daily
  suites), needs no file edits, and can't be undone by an upstream rebase.

## History

- **2026-07-08** — Disabled all fork workflows except `Fork e2e mirror` to stop
  daily E2E/E2E-UI/Integration failures (Actions minutes + LLM tokens) and the
  weekly `main`-push / PR CI spend. Budget control for the Deadwax project.
