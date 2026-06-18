# UI diff snapshot tests

A single visual-regression baseline of the empty landing state (`/`,
`NewChatLandingScreen` — "What should we do?"), gated in CI.

- Test: [`test_landing_snapshot.py`](test_landing_snapshot.py)
- Baseline (committed): `snapshots/test_landing_snapshot/test_empty_landing_matches_baseline/test_empty_landing_matches_baseline[chromium][linux].png`
- Gate workflow: [`.github/workflows/ui-snapshot.yml`](../../../.github/workflows/ui-snapshot.yml)
- Plugin: [`pytest-playwright-visual-snapshot`](https://github.com/iloveitaly/pytest-playwright-visual-snapshot)

## Why CI is the only renderer

Screenshots differ across operating systems (font rasterizer, hinting,
anti-aliasing), and no diff threshold can reconcile two rendering engines. So we
never compare across OSes: the baseline and the PR comparison are both produced
on a **pinned `ubuntu-24.04`** GitHub runner. That is the single source of
truth. You do not need Docker or a Linux machine locally.

The test is marked `@pytest.mark.visual`; the main e2e-ui suite (unpinned
`ubuntu-latest`) excludes it via `-m "not visual"`. Only `ui-snapshot.yml` runs
it.

## How the gate behaves

- On every PR, `ui-snapshot.yml` renders `/` and compares it to the committed
  baseline. Any pixel difference fails the check and uploads
  `actual_/expected_/diff_` PNGs as the `ui-snapshot-diff-*` artifact.
- The baseline is **never** changed automatically. The only way to change it is
  the explicit update flow below.

## Updating the baseline (when a UI change is intentional)

1. Push your branch.
2. Trigger the update job: GitHub → Actions → **UI Snapshot** → **Run
   workflow**, set `ref` to your branch. This runs the test with
   `--update-snapshots` on the same pinned runner (it intentionally fails — that
   is expected) and uploads the regenerated PNG as the `ui-snapshot-baseline`
   artifact.
   - CLI equivalent: `gh workflow run ui-snapshot.yml -f ref=<your-branch>`
3. Download the `ui-snapshot-baseline` artifact, **review the image**, and copy
   the PNG over the committed baseline at the path above.
4. Commit the updated baseline and push. The PR compare job now passes.

## Running locally (debugging only — do not commit the result)

You can exercise the test locally, but a baseline rendered on any machine other
than the CI runner will not match it, so never commit a locally generated PNG.

```bash
uv sync --extra all --extra dev
uv run playwright install --with-deps chromium
cd ap-web && npm ci --legacy-peer-deps && npm run build && cd ..
# First run with no baseline creates one (and fails); subsequent runs compare:
uv run pytest tests/e2e_ui/visual -m visual --ui-skip-build
```
