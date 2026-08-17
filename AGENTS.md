# Agent guidance

Guidance for AI agents (Claude Code, Copilot, Cursor, etc.) working in this
repository. See `CONTRIBUTING.md` for the full contributor workflow.

## Committing

Run the `pre-commit` hook before committing (`pre-commit run --all-files`, or
let it run on staged files via `git commit`). Fix any issues it reports so the
commit lands clean — CI runs the same checks.

## Local development shortcuts

Use `just` for common tasks; run `just --list` for grouped recipes.

- `just ensure` — install/check prerequisites
- `just run-ios` / `just run-android` — build/run mobile apps
- `just dev` / `just dev-mobile` — start the omnigent dev pod
- `just electron-dev` / `just electron-build` — Electron desktop shell
- `just lint` / `just lint-all` — run pre-commit
- `just normalize-locks` — rewrite lockfile registries to PyPI/npmjs.org

## Pull requests

When you open a pull request, fill in the repo's PR template at
`.github/pull_request_template.md` (case-sensitive on Linux — note the lowercase
filename). Keep every section and checkbox row so reviewers can skim them.

- **Summary** — what changed and why.
- **Test Plan** — how you verified it.
- **Demo** — a **video or images** showing the change. Expected on contributor
  PRs for UI / frontend changes (check the "UI / frontend change" box under
  _Type of change_) so reviewers can see the new behaviour without checking out
  the branch. Use `N/A` for non-visual changes.
- **Type of change** / **Test coverage** — check all that apply (at least one
  each).
- **Coverage notes** — required if you checked "Manual verification completed"
  or "Not applicable".

Generate the description from the actual diff and this session's context — lead
with the motivation, then the change. Don't pass a `--body` that skips these
sections.

## Finishing a task

When you finish a task, print instructions to the user on how to test it: the
commands to run, the inputs to provide, or the steps to reproduce so they can
verify the result themselves. Don't leave the user guessing how to confirm the
work — tell them exactly what to do.

## Deprecating features

When deprecating a feature, note the version in which it is expected to be
removed so we can clean it up when that version ships. Call out the deprecation
version in code (e.g. a `@deprecated` tag or comment naming the target release)
and in the PR/commit description, so there's a clear marker to act on later.

## Code comments

Keep comments short and focused on the code, not on the change history.

- **Keep them brief** — prefer one or two lines. Avoid comments longer than
  three lines; if you need more, the code likely needs refactoring or a doc
  string, not a wall of inline commentary.
- **Describe the scenario, not the PR** — explain _what_ the code handles or
  _why_ it exists, in terms a future reader needs. Don't reference PR numbers,
  issue numbers, or ticket IDs (e.g. `#1646`, `fixes JIRA-123`); the scenario
  should be clear without chasing external links.

## Database query names

Application stores use `make_named_managed_session_maker` and give every
session a stable semantic operation name. The session-level name must describe
the caller's intent rather than repeat SQL syntax; use a nested
`query_name_scope` only when one transaction needs distinct names for important
subqueries. Because the named session covers implicit flush and commit, don't
add an explicit `flush()` only to make a query name observable.

## Framework-owned instructions

Keep runtime lifecycle and metadata instructions separate from portable agent
instructions:

- Agent-spec and per-request instructions are user-authored. Framework-owned
  instructions are additive runtime behavior and are appended after them in
  `omnigent/runtime/prompt.py`.
- Keep the canonical instruction text and lifecycle gate in the owning framework
  module. Harness adapters should only transport the composed instructions; do
  not duplicate policy across adapters or add lifecycle metadata to `AgentSpec`.
- If framework instructions grow beyond a small ordered list, introduce a
  structured `FrameworkInstructions` value at the prompt-composition boundary.

## Deadwax fork

This branch is the branded Deadwax fork of
[`omnigent-ai/omnigent`](https://github.com/omnigent-ai/omnigent). Keep
Deadwax-only branding, themes, and deployment changes out of upstream pull
requests.

- `origin` is `deadwax-ai-omnigent/omnigent`.
- `upstream` is `omnigent-ai/omnigent`.
- `main` mirrors the latest stable upstream release tag (currently `v0.9.0`).
- `deadwax` is a linear stack of fork customizations on that release.
- Short-lived change branches target `deadwax` and are squash-merged.

Syncing is automated by `scripts/deadwax/sync.sh`, run daily on the host that
serves Deadwax via the `io.deadwax.omnigent-sync` launchd job. It adopts a new
upstream stable release end to end — recovery ref, `main` mirror, rebase of the
Deadwax stack, tests + wheel build, publish, install, restart, rollback on an
unhealthy deploy — and stops for a human only when the rebase conflicts, filing
an issue on the fork. See
[`docs/deadwax-upstream-sync.md`](docs/deadwax-upstream-sync.md); resolve
conflicts by keeping upstream behavior and porting the branding into the
current UI structure, and publish rewritten `deadwax` history only with
`--force-with-lease`.

Every inherited upstream workflow is disabled at the repo level to keep the
Actions bill down, and nothing in this fork depends on an Actions run. A sync
that replaces the workflow files re-registers them under new IDs in state
`active`; the sync job re-runs the disable sweep in
[`docs/deadwax-github-actions.md`](docs/deadwax-github-actions.md) itself, so
that is a check rather than a chore.

### Never send anything upstream without explicit approval

**Do not create a pull request, issue, or comment on `omnigent-ai/omnigent` — or
any repository the owner does not control — unless the owner has explicitly
approved that specific action in the current conversation.**

This is a hard stop, not a preference. It applies to every agent (Claude Code,
Copilot, Cursor, and any other) and to every harness.

- Before running `gh pr create`, check the target repository. If it is not
  `deadwax-ai-omnigent/omnigent`, stop and ask first.
- State plainly that the action is **public and upstream**, name the target
  repository, and wait for a clear yes. Silence, a prior approval, or a general
  "go ahead" on other work is not approval.
- Creating a branch or writing a commit intended for upstream is **not**
  authorization to open the PR. Do that work, then stop and ask.
- Fork-internal PRs into `deadwax` need none of this ceremony.

Rationale: an upstream PR is public, permanent, and attributed to the repository
owner. It cannot be quietly undone. This rule exists because an agent once
opened one on the owner's behalf without telling them.

If — and only if — upstream contribution has been approved: branch from
`upstream/main`, never `deadwax`, follow upstream's issue and PR process, and
reference the issue from the PR.
