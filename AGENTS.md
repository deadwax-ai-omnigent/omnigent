# Agent guidance

Guidance for AI agents (Claude Code, Copilot, Cursor, etc.) working in this
repository. See `CONTRIBUTING.md` for the full contributor workflow.

## Committing

Run the `pre-commit` hook before committing (`pre-commit run --all-files`, or
let it run on staged files via `git commit`). Fix any issues it reports so the
commit lands clean — CI runs the same checks.

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
- `main` mirrors the latest stable upstream release tag (currently `v0.6.0`).
- `deadwax` is a linear stack of fork customizations on that release.
- Short-lived change branches target `deadwax` and are squash-merged.

The weekly `deadwax-upstream-sync.yml` workflow advances the clean `main`
mirror to the newest stable release and alerts on the open `deadwax` → `main`
tracking PR when `deadwax` needs a manual rebase (or opens an issue if
repository issues are enabled). Scheduled workflows run from the repository's
default branch, which must remain `deadwax` for this fork-only workflow to
execute.

Keep one `deadwax` → `main` PR permanently open as a view of the fork's custom
diff. Do not merge it.

Every other inherited upstream workflow is disabled at the repo level to keep
the Actions bill down. A sync that replaces the workflow files re-registers them
under new IDs in state `active`, so re-run the disable sweep in
[`docs/deadwax-github-actions.md`](docs/deadwax-github-actions.md) after every
major upstream sync.

To update the fork, fetch upstream tags, create dated recovery refs, move
`main` to the latest stable release, and rebase the Deadwax stack from its old
release tag onto the new tag. Resolve conflicts by keeping upstream behavior
and porting the branding into the current UI structure. Publish rewritten
`deadwax` history only with `--force-with-lease`.

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
