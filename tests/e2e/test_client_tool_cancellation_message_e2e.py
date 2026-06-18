"""
E2E for audit fix #6 (option d) -- cancelled client_tool tasks
must leave a ``[System: task X (client_tool) cancelled]``
message in the parent's conversation.

SKIPPED: this test depends on the legacy ``POST /v1/responses`` route
(with ``background: True`` + ``/cancel``) which has been removed. The
test needs to be rewritten to use the sessions API
(``POST /v1/sessions/{id}/events`` + session-level cancellation) before
it can be migrated to mock LLM. The audit-fix-#6 invariant is covered
at the integration level.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "client-tool cancellation e2e depends on the removed "
        "POST /v1/responses route (background + cancel). Needs "
        "rewrite for sessions API before mock-LLM migration."
    ),
)


def test_cancelled_client_tool_persists_system_message_in_conversation() -> None:
    """Placeholder -- see module-level skip marker."""
