"""
E2E reproduction of audit-fix-#1: sub-agent's async client-tool
result routing.

SKIPPED: this test depends on the legacy ``POST /v1/responses`` route
(with ``background: True`` + ``PATCH /v1/responses/{id}/async_tool_results``)
which has been removed. The test needs to be rewritten to use the sessions API
(``POST /v1/sessions/{id}/events`` + session-level tool result delivery)
before it can be migrated to mock LLM. The audit-fix-#1 routing invariant
is covered at the integration level.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "sub-agent async client-tool routing e2e depends on the removed "
        "POST /v1/responses route (background + PATCH). Needs rewrite "
        "for sessions API before mock-LLM migration."
    ),
)


def test_sub_agent_async_client_tool_signal_routes_to_worker_drain() -> None:
    """Placeholder -- see module-level skip marker."""
