# Deadwax fork — GitHub Actions cost control

> Fork-only doc (lives on the `deadwax` branch; never contributed upstream).
> Companion to [`CLAUDE.md`](../CLAUDE.md) → "Deadwax fork".

## Why

We inherit **all** of upstream's `.github/workflows/*`. On our fork's default
branch (`deadwax`) GitHub auto-runs them, burning Actions minutes — and, for the
suites that reach a live LLM gateway, tokens — for zero signal:

- Our fork is **frontend-only** (branding / themes / deploy — see
  [`scripts/deadwax-deploy.sh`](../scripts/deadwax-deploy.sh)). We don't change
  the Python runtime those suites test.
- Upstream already runs all of these on every release.
- The scheduled suites (`Backwards-Compat`, `E2E Tests`, `Integration Tests`,
  `Benchmark`, `Demo Check`, …) fail or no-op here every day, and each run
  emails the repo owner.
- Push and PR workflows — including the token-spending **`Polly AI Review`** —
  fire on every sync push and on any PR opened into `deadwax`.

So we **disable every inherited workflow at the repo level** (not via file
edits), keeping only our own.

## Current state

**Last full sweep: 2026-08-11.** Method: `gh workflow disable` on every `active`
workflow except the two below.

**Active (2):**

| Workflow | Why |
|---|---|
| `Deadwax · Upstream Release Check` (`.github/workflows/deadwax-upstream-sync.yml`) | Ours. Weekly; advances the `main` mirror and alerts on the tracking PR. Must stay enabled. |
| `Dependency Graph` (`dynamic/dependabot/update-graph`) | **Not** a real Actions workflow — GitHub's built-in Dependabot dependency-graph updater. Runs on GitHub's infra, consumes zero Actions minutes, and the Actions API can't disable it. Harmless; disable via repo **Settings → Code security** if ever desired. |

Everything else (78 entries) is `disabled_manually`.

## The trap: a major upstream sync re-registers workflows

The disable is a **repo-level** setting keyed to a **workflow ID**, not to the
file. It survives ordinary rebases and force-pushes — but **not** a sync that
replaces the workflow files wholesale.

The `v0.6.0` forward sync did exactly that: GitHub registered ~35 workflows
under a **new ID range** (`3173124xx`) alongside the old, already-disabled ones
(`2985xxxxx`). New IDs default to **`active`**, so the July sweep silently
stopped covering them and `Backwards-Compat` (every 12h), `Demo Check`
(hourly), `Benchmark`, `Security Alert Triage`, and `Discord watch rotation`
started running and emailing again.

**Re-run the sweep below after every major upstream sync**, and confirm the
active count is back to 2. Two generations of IDs for the same workflow name is
the tell.

## Check the current state

```bash
FORK=deadwax-ai-omnigent/omnigent
gh workflow list --repo "$FORK" --all
```

Just the ones still active — this should print exactly the two rows above:

```bash
gh workflow list --repo deadwax-ai-omnigent/omnigent --all --limit 100 \
  --json id,name,state --jq '.[] | select(.state=="active") | "\(.id)\t\(.name)"'
```

## Re-disable (repeat the sweep)

Disables everything except our upstream-release check. Safe to re-run; already
disabled workflows are skipped.

```bash
gh workflow list --repo deadwax-ai-omnigent/omnigent --all --limit 100 \
  --json id,name,state \
  --jq '.[] | select(.state=="active")
             | select(.name != "Deadwax · Upstream Release Check")
             | select(.name != "Dependency Graph") | .id' \
  | xargs -I{} gh workflow disable {} --repo deadwax-ai-omnigent/omnigent
```

## Re-enable

```bash
FORK=deadwax-ai-omnigent/omnigent

# One workflow, by name or by its .yml filename:
gh workflow enable "E2E Tests" --repo "$FORK"

# Everything:
gh api --paginate "repos/$FORK/actions/workflows" -q '.workflows[].id' \
  | xargs -I{} gh workflow enable {} --repo "$FORK"
```

> Re-enabling the push/PR gates or the scheduled suites brings the
> Actions-minute and LLM-token spend back. Re-enable selectively.

## Notes

- **Upstream is unaffected.** `omnigent-ai/omnigent` is a separate repo with its
  own Actions; disabling on our fork changes nothing there.
- **Disabled workflows don't fire on any trigger** — schedule, push, PR, or
  `workflow_dispatch`. To run one manually you must re-enable it first.
- We chose the repo-level disable over per-file `if:` guards in the workflow
  YAML: it covers all workflows, needs no file edits, and doesn't add conflict
  surface to the rebase.

## History

- **2026-08-11** — Re-ran the sweep after the `v0.9.0` forward sync, which
  re-registered 13 workflows under a third ID generation (`3324324xx`) in state
  `active` — among them `Nightly Release` and the PR-hygiene bots that fire on
  every push into `deadwax`. Registered total is now 80; active is back to 2.
- **2026-08-01** — Re-ran the sweep over 32 workflows the `v0.6.0` sync had
  re-registered as new, `active` IDs (see "The trap" above). Dropped the old
  `Fork e2e mirror` exception — upstream removed that workflow in `v0.6.0`.
- **2026-07-08** — First sweep. Disabled all fork workflows to stop daily
  E2E/E2E-UI/Integration failures and the weekly `main`-push / PR CI spend.
