"""Visual-regression snapshot of the empty landing state ("/").

A single committed baseline of the ``NewChatLandingScreen`` ("What should we
do?") rendered at ``/``. The gate lives in ``.github/workflows/ui-snapshot.yml``
and runs on a *pinned* ``ubuntu-24.04`` runner so the committed baseline and the
PR comparison are produced by the exact same renderer (screenshots differ across
OSes; no diff threshold can reconcile two rendering engines, so CI is the single
source of truth). To update the baseline, run that workflow via
``workflow_dispatch``, download the ``ui-snapshot-baseline`` artifact, review the
image, and commit it — see ``tests/e2e_ui/visual/README.md``.

The test is marked ``@pytest.mark.visual`` so the main e2e_ui suite (which runs
on the unpinned ``ubuntu-latest``) excludes it via ``-m 'not visual'``; only the
dedicated pinned gate runs it.

Capture choices for determinism:

* We screenshot the ``new-chat-landing`` region (not the whole viewport) so the
  left sidebar's volatile chrome (account area, host/connection status) never
  enters the baseline. The hero + composer *is* the empty-state content.
* The composer footer surfaces environment-specific values (hostname, working
  directory, git repo/branch, selected agent). Those are masked — they would
  never match between the CI runner and a regenerating run.
* A fixed viewport pins layout; the plugin captures with ``animations="disabled"``;
  we force-focus the input and hide the text caret so the focused border state
  and the blinking caret are deterministic.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

# data-testids of the composer chrome that reflect the host environment and so
# can never be part of a stable cross-run baseline. Masked (painted a solid
# colour) before comparison. See ap-web/src/shell/NewChatDialog.tsx.
_VOLATILE_SELECTORS = [
    '[data-testid="new-chat-landing-host-chip"]',
    '[data-testid="new-chat-landing-workspace-chip"]',
    '[data-testid="new-chat-landing-repo-chip"]',
    '[data-testid="new-chat-landing-branch-chip"]',
    '[data-testid="new-chat-landing-agent-select"]',
]


@pytest.mark.visual
def test_empty_landing_matches_baseline(
    page: Page,
    live_server: str,
    assert_snapshot,
) -> None:
    """The empty "/" landing renders pixel-identical to the committed baseline.

    :param page: pytest-playwright page (fresh context per test).
    :param live_server: Base URL of the spawned ``omnigent server`` serving the
        built SPA. No LLM turn is dispatched, so no model credentials are needed.
    :param assert_snapshot: ``pytest-playwright-visual-snapshot`` fixture; writes
        the baseline under ``--update-snapshots`` and otherwise compares against
        it, failing (and emitting actual/expected/diff PNGs) on any mismatch.
    """
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server}/")

    landing = page.get_by_test_id("new-chat-landing")
    # Generous timeout: the SPA runs a short boot probe before the landing paints.
    expect(landing).to_be_visible(timeout=30_000)

    # The composer toolbar's agent control is async: until the agent catalog
    # fetch resolves, the picker renders a "No agents" placeholder (no
    # agent-select element) and the Advanced chip is hidden, so a capture taken
    # before the fetch lands differs structurally from one taken after. Wait for
    # the loaded state (agent picker present) so the toolbar is deterministic --
    # this is also what makes the agent-select mask below resolve to an element.
    expect(page.get_by_test_id("new-chat-landing-agent-select")).to_be_visible(timeout=30_000)

    # Settle web fonts so glyph metrics don't shift mid-capture. The expression
    # must *return* the Promise so Playwright's sync API awaits it; an arrow
    # function that calls .then() returns undefined and never waits.
    page.evaluate("document.fonts.ready")

    # Pin the focused-composer border state and kill the blinking caret, both of
    # which are otherwise time-dependent.
    page.add_style_tag(content="* { caret-color: transparent !important; }")
    page.get_by_test_id("new-chat-landing-input").focus()

    assert_snapshot(landing, mask_elements=_VOLATILE_SELECTORS)
