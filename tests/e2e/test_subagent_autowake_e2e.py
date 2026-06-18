"""End-to-end test for sub-agent auto-wake (mock LLM).

When a sub-agent finishes, the runner delivers its result to the parent's
inbox AND posts a ``[System: ... waiting in inbox]`` wake notice to the
parent's event stream, so an idle orchestrator takes a continuation turn and
surfaces the result -- without the user sending another message.

The wake notice substring ``waiting in inbox`` is produced ONLY by the
auto-wake path (``_format_subagent_wake_notice``); it is distinct from the
``sys_read_inbox`` drain message. So its presence is an auto-wake-specific
signal.

All tests use mock-LLM keyed queues. The sub-agent-test bundle is uploaded
and mock responses control each agent's behaviour deterministically.

Excluded from default ``pytest`` runs via ``--ignore=tests/e2e``. Invoke
with::

    pytest tests/e2e/test_subagent_autowake_e2e.py -v --timeout=60
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from tests.e2e.conftest import (
    configure_mock_llm,
    create_runner_bound_session,
    poll_session_until_terminal,
    reset_mock_llm,
    send_user_message_to_session,
    upload_agent,
)
from tests.e2e.helpers import POLL_INTERVAL_S

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "_fixtures" / "agents"
_SUB_AGENT_FIXTURE = _FIXTURES_DIR / "sub-agent-test"

# The auto-wake notice is the ONLY place this substring is emitted.
_WAKE_NOTICE_SIGNATURE = "waiting in inbox"
_RESEARCHER_MARKER = "RESEARCHER_MARKER_2025"

# Each test is 3+ serial gateway turns, so 600s absorbs potential backoff.
pytestmark = pytest.mark.timeout(600, method="signal")


@pytest.fixture(scope="session")
def sub_agent_test_agent(
    http_client: httpx.Client,
    databricks_workspace_host: str | None,
    databricks_profile_or_none: str | None,
) -> str:
    """Upload the sub-agent-test fixture (parent + researcher/summarizer).

    :param http_client: HTTP client pointed at the live server.
    :param databricks_workspace_host: Workspace host URL when ``--profile``
        is set, else ``None``.
    :param databricks_profile_or_none: Active ``--profile`` value.
    :returns: Agent name ``"sub-agent-test"``.
    """
    return upload_agent(
        http_client,
        _SUB_AGENT_FIXTURE,
        rewrite_model_for_databricks=databricks_workspace_host is not None,
        databricks_profile=databricks_profile_or_none,
    )


# ─── Mock helpers ────────────────────────────────────────────


def _sys_session_send_tool_call(
    agent: str,
    title: str,
    child_args: str,
    *,
    call_id: str = "call_1",
) -> dict:
    """Build a tool_calls response entry for ``sys_session_send``."""
    return {
        "call_id": call_id,
        "name": "sys_session_send",
        "arguments": json.dumps({"agent": agent, "title": title, "args": child_args}),
    }


def _session_items_blob(http_client: httpx.Client, session_id: str) -> str:
    """Return all items in a session snapshot as one JSON string."""
    resp = http_client.get(f"/v1/sessions/{session_id}")
    resp.raise_for_status()
    return json.dumps(resp.json().get("items", []))


def _count_wake_notices(http_client: httpx.Client, session_id: str) -> int:
    """Count auto-wake notices in a session snapshot."""
    return _session_items_blob(http_client, session_id).count(_WAKE_NOTICE_SIGNATURE)


def _configure_dispatch_flow(mock_url: str) -> None:
    """Configure mock queues for a single dispatch-and-autowake flow.

    Queues responses on the ``"default"`` key:
    1. Parent dispatch: sys_session_send tool call.
    2. Parent after tool result: text acknowledging dispatch.
    3. Child turn: text containing the marker.
    4. Parent auto-wake continuation: text quoting the marker.
    """
    configure_mock_llm(
        mock_url,
        [
            {
                "tool_calls": [
                    _sys_session_send_tool_call("researcher", "auth", "Research auth patterns"),
                ],
            },
            {"text": "Dispatched researcher, waiting for result."},
            # Child (researcher) response -- shares queue.
            {"text": f"Research complete. {_RESEARCHER_MARKER}"},
            # Parent auto-wake continuation.
            {"text": f"The researcher returned: {_RESEARCHER_MARKER}"},
        ],
        key="default",
    )


# ─── Tests ───────────────────────────────────────────────────


def test_subagent_completion_auto_wakes_idle_parent(
    http_client: httpx.Client,
    live_runner_id: str,
    sub_agent_test_agent: str,
    mock_llm_server_url: str,
) -> None:
    """Dispatching a sub-agent then sending nothing else still surfaces its
    result, because the parent is auto-woken when the sub-agent completes.

    Flow:
    1. One user message tells the parent to dispatch the researcher.
    2. The dispatch turn goes terminal (sub-agent runs async).
    3. With NO further user input, the sub-agent completes, the runner
       posts the wake notice, and the parent takes a continuation turn.
    """
    reset_mock_llm(mock_llm_server_url)
    _configure_dispatch_flow(mock_llm_server_url)

    session_id = create_runner_bound_session(
        http_client,
        agent_name=sub_agent_test_agent,
        runner_id=live_runner_id,
    )
    dispatch_response_id = send_user_message_to_session(
        http_client,
        session_id=session_id,
        content="Dispatch the researcher sub-agent.",
    )

    # Dispatch turn goes terminal on its own.
    poll_session_until_terminal(
        http_client,
        session_id=session_id,
        response_id=dispatch_response_id,
        timeout=180,
    )

    # From here we send NOTHING. The wake notice and marker can only
    # appear via the auto-wake continuation turn.
    deadline = time.monotonic() + 240
    wake_seen = False
    marker_seen = False
    while time.monotonic() < deadline:
        blob = _session_items_blob(http_client, session_id)
        wake_seen = wake_seen or _WAKE_NOTICE_SIGNATURE in blob
        marker_seen = _RESEARCHER_MARKER in blob
        if wake_seen and marker_seen:
            break
        time.sleep(POLL_INTERVAL_S)

    assert wake_seen, (
        f"No auto-wake notice ({_WAKE_NOTICE_SIGNATURE!r}) appeared in session "
        f"{session_id} after the dispatch turn ended."
    )
    assert marker_seen, (
        f"Researcher marker {_RESEARCHER_MARKER!r} never surfaced in session "
        f"{session_id}."
    )


def test_subagent_completion_auto_wakes_parent_on_a_second_round(
    http_client: httpx.Client,
    live_runner_id: str,
    sub_agent_test_agent: str,
    mock_llm_server_url: str,
) -> None:
    """Re-dispatching the SAME sub-agent in a second round wakes the parent again.

    Coarse CUJ for the multi-round auto-wake path: round 1 dispatches and
    the parent is auto-woken; round 2 re-dispatches and the parent must be
    auto-woken AGAIN, asserted by the wake-notice count strictly increasing.
    """
    reset_mock_llm(mock_llm_server_url)

    # Queue responses for round 1 AND round 2 (8 total on default queue).
    configure_mock_llm(
        mock_llm_server_url,
        [
            # Round 1: dispatch
            {
                "tool_calls": [
                    _sys_session_send_tool_call("researcher", "round1", "Research round 1"),
                ],
            },
            {"text": "Dispatched, waiting."},
            # Round 1: child
            {"text": f"Round 1 done. {_RESEARCHER_MARKER}"},
            # Round 1: parent auto-wake continuation
            {"text": f"Round 1 result: {_RESEARCHER_MARKER}"},
            # Round 2: dispatch
            {
                "tool_calls": [
                    _sys_session_send_tool_call("researcher", "round2", "Research round 2"),
                ],
            },
            {"text": "Re-dispatched, waiting."},
            # Round 2: child
            {"text": f"Round 2 done. {_RESEARCHER_MARKER}"},
            # Round 2: parent auto-wake continuation
            {"text": f"Round 2 result: {_RESEARCHER_MARKER}"},
        ],
        key="default",
    )

    session_id = create_runner_bound_session(
        http_client,
        agent_name=sub_agent_test_agent,
        runner_id=live_runner_id,
    )

    # ── Round 1 ──
    round1_response_id = send_user_message_to_session(
        http_client,
        session_id=session_id,
        content="Dispatch the researcher sub-agent.",
    )
    poll_session_until_terminal(
        http_client,
        session_id=session_id,
        response_id=round1_response_id,
        timeout=180,
    )

    deadline = time.monotonic() + 240
    round1_wakes = 0
    marker_seen = False
    while time.monotonic() < deadline:
        round1_wakes = _count_wake_notices(http_client, session_id)
        marker_seen = _RESEARCHER_MARKER in _session_items_blob(http_client, session_id)
        if round1_wakes >= 1 and marker_seen:
            break
        time.sleep(POLL_INTERVAL_S)

    assert round1_wakes >= 1 and marker_seen, (
        f"Round 1 did not auto-wake the parent in session {session_id} "
        f"(wakes={round1_wakes}, marker_seen={marker_seen})."
    )

    # ── Round 2: re-dispatch ──
    round2_response_id = send_user_message_to_session(
        http_client,
        session_id=session_id,
        content="Dispatch the researcher sub-agent again.",
    )
    poll_session_until_terminal(
        http_client,
        session_id=session_id,
        response_id=round2_response_id,
        timeout=180,
    )

    deadline = time.monotonic() + 240
    round2_wakes = round1_wakes
    while time.monotonic() < deadline:
        round2_wakes = _count_wake_notices(http_client, session_id)
        if round2_wakes > round1_wakes:
            break
        time.sleep(POLL_INTERVAL_S)

    assert round2_wakes > round1_wakes, (
        f"No NEW auto-wake notice for round 2 in session {session_id} "
        f"(round1_wakes={round1_wakes}, round2_wakes={round2_wakes})."
    )
