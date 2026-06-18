"""E2E test: Claude SDK executor with client-side tools.

SKIPPED: this test depends on the legacy ``POST /v1/responses`` route
(with ``background: True`` + ``PATCH /v1/responses/{id}``) which has been
removed. The test needs to be rewritten to use the sessions API before it
can be migrated to mock LLM. The client-tool park/resume invariant for
claude-sdk is covered at the integration level.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "claude-sdk client-tool e2e depends on the removed "
        "POST /v1/responses route (background + PATCH). Needs "
        "rewrite for sessions API before mock-LLM migration."
    ),
)


def test_claude_sdk_parks_client_tool_call() -> None:
    """Placeholder -- see module-level skip marker."""
