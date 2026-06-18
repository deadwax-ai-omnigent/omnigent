"""End-to-end tests for the Phase 3 sub-agent pipeline (mock LLM).

Covers ``sys_session_send`` (singular) dispatch:

* ``test_single_sub_agent_e2e`` — parent dispatches one sub-agent
  via sys_session_send, the result auto-delivers, and the parent
  quotes the marker in its final response.
* ``test_parallel_sub_agents_e2e`` — parent emits TWO
  sys_session_send tool calls in one response (the new
  parallelism idiom); both sub-agent markers reach the final reply.
* ``test_mixed_sub_agent_and_async_tool_e2e`` — parent
  dispatches one sub-agent and checks the unified
  async_work_complete drain handles the sub_agent kind.

All three tests use mock-LLM keyed queues. The sub-agent-test bundle
is uploaded (declaring sub-agent specs the runner needs) and mock
responses control each agent's behaviour deterministically.

Excluded from default ``pytest`` runs via ``--ignore=tests/e2e``.
Invoke with::

    pytest tests/e2e/test_sub_agent_phase3_e2e.py -v --timeout=60
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

# Each test is 3+ serial gateway turns (dispatch + sub-agent + auto-wake),
# so 600s absorbs potential backoff.
pytestmark = pytest.mark.timeout(600, method="signal")


@pytest.fixture(scope="session")
def sub_agent_test_agent(
    http_client: httpx.Client,
    databricks_workspace_host: str | None,
    databricks_profile_or_none: str | None,
) -> str:
    """Upload the sub-agent-test fixture (parent + 2 sub-agents).

    :param http_client: HTTP client pointed at the live server.
    :param databricks_workspace_host: Workspace host URL when
        ``--profile`` is set, else ``None``.
    :param databricks_profile_or_none: Active ``--profile`` value.
    :returns: Agent name ``"sub-agent-test"``.
    """
    return upload_agent(
        http_client,
        _SUB_AGENT_FIXTURE,
        rewrite_model_for_databricks=databricks_workspace_host is not None,
        databricks_profile=databricks_profile_or_none,
    )


# ─── Mock helpers ───────────────────────────────────────────


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


def _wait_for_markers(
    http_client: httpx.Client,
    session_id: str,
    *markers: str,
    timeout_s: float = 240.0,
) -> str:
    """Poll the session snapshot until every *marker* substring appears.

    ``sys_session_send`` is async: the sub-agent runs after the parent's
    dispatch turn ends, then auto-wakes the parent. The marker lands in
    the session AFTER the dispatch turn goes idle.

    :returns: The final serialized items blob.
    """
    deadline = time.monotonic() + timeout_s
    blob = ""
    while time.monotonic() < deadline:
        resp = http_client.get(f"/v1/sessions/{session_id}")
        resp.raise_for_status()
        blob = json.dumps(resp.json().get("items", []))
        if all(m in blob for m in markers):
            return blob
        time.sleep(POLL_INTERVAL_S)
    raise AssertionError(
        f"markers {markers!r} did not all surface in session {session_id} "
        f"within {timeout_s:.0f}s. Last items blob: {blob[:600]!r}"
    )


def _run_turn(
    http_client: httpx.Client,
    *,
    runner_id: str,
    agent_name: str,
    user_text: str,
    timeout_s: float = 240.0,
) -> tuple[dict, str]:
    """Drive one turn through a fresh runner-bound session."""
    session_id = create_runner_bound_session(
        http_client,
        agent_name=agent_name,
        runner_id=runner_id,
    )
    response_id = send_user_message_to_session(
        http_client,
        session_id=session_id,
        content=user_text,
    )
    body = poll_session_until_terminal(
        http_client,
        session_id=session_id,
        response_id=response_id,
        timeout=timeout_s,
    )
    return body, session_id


# ─── Tests ───────────────────────────────────────────────────


def test_single_sub_agent_e2e(
    http_client: httpx.Client,
    sub_agent_test_agent: str,
    live_runner_id: str,
    mock_llm_server_url: str,
) -> None:
    """Parent dispatches one sub-agent; its marker surfaces via auto-wake.

    Mock flow:
    1. Parent LLM -> sys_session_send(researcher)
    2. Parent LLM -> "Dispatched, waiting."
    3. Child (researcher) LLM -> text with RESEARCHER_MARKER_2025
    4. Parent auto-wake continuation -> text quoting the marker
    """
    reset_mock_llm(mock_llm_server_url)
    # All agents share the "default" queue (model gpt-5.4 maps to default).
    # Queue order: parent dispatch, parent ack, child response, parent auto-wake.
    configure_mock_llm(
        mock_llm_server_url,
        [
            {
                "tool_calls": [
                    _sys_session_send_tool_call("researcher", "auth", "Research auth patterns"),
                ],
            },
            {"text": "Dispatched researcher, waiting for result."},
            {"text": "Research complete. RESEARCHER_MARKER_2025"},
            {"text": "The researcher returned: RESEARCHER_MARKER_2025"},
        ],
        key="default",
    )

    body, session_id = _run_turn(
        http_client,
        runner_id=live_runner_id,
        agent_name=sub_agent_test_agent,
        user_text="Dispatch the researcher sub-agent.",
    )
    assert body["status"] == "completed", (
        f"sub-agent turn did not complete: status={body.get('status')!r}, "
        f"error={body.get('error')!r}"
    )

    # The marker surfaces via auto-wake (async).
    _wait_for_markers(http_client, session_id, "RESEARCHER_MARKER_2025")


def test_parallel_sub_agents_e2e(
    http_client: httpx.Client,
    sub_agent_test_agent: str,
    live_runner_id: str,
    mock_llm_server_url: str,
) -> None:
    """Parent dispatches both sub-agents in parallel; both markers surface.

    Mock flow:
    1. Parent -> two sys_session_send tool calls (researcher + summarizer)
    2. Parent -> "Dispatched both, waiting."
    3. Child researcher -> text with RESEARCHER_MARKER_2025
    4. Child summarizer -> text with SUMMARIZER_MARKER_2025
    5. Parent auto-wake -> text quoting both markers
    """
    reset_mock_llm(mock_llm_server_url)
    # All agents share the "default" queue. Queue order:
    # parent dispatch, parent ack, two children, parent auto-wake.
    configure_mock_llm(
        mock_llm_server_url,
        [
            {
                "tool_calls": [
                    _sys_session_send_tool_call(
                        "researcher", "auth", "Research auth", call_id="call_1"
                    ),
                    _sys_session_send_tool_call(
                        "summarizer", "summary", "Summarize findings", call_id="call_2"
                    ),
                ],
            },
            {"text": "Dispatched both sub-agents, waiting."},
            {"text": "Research done. RESEARCHER_MARKER_2025"},
            {"text": "Summary done. SUMMARIZER_MARKER_2025"},
            {
                "text": (
                    "Results: RESEARCHER_MARKER_2025 and SUMMARIZER_MARKER_2025"
                )
            },
        ],
        key="default",
    )

    body, session_id = _run_turn(
        http_client,
        runner_id=live_runner_id,
        agent_name=sub_agent_test_agent,
        user_text="Dispatch BOTH the researcher AND the summarizer in parallel.",
    )
    assert body["status"] == "completed", (
        f"parallel turn did not complete: status={body.get('status')!r}, "
        f"error={body.get('error')!r}"
    )

    _wait_for_markers(
        http_client,
        session_id,
        "RESEARCHER_MARKER_2025",
        "SUMMARIZER_MARKER_2025",
    )


def test_mixed_sub_agent_and_async_tool_e2e(
    http_client: httpx.Client,
    sub_agent_test_agent: str,
    live_runner_id: str,
    mock_llm_server_url: str,
) -> None:
    """Sub-agent dispatch through the unified async_work_complete drain.

    Same as single sub-agent dispatch -- the E2E layer proves the
    real-LLM flow doesn't regress on the kind discriminator path.
    """
    reset_mock_llm(mock_llm_server_url)
    configure_mock_llm(
        mock_llm_server_url,
        [
            {
                "tool_calls": [
                    _sys_session_send_tool_call("researcher", "task", "Research something"),
                ],
            },
            {"text": "Dispatched researcher, waiting."},
            {"text": "Done. RESEARCHER_MARKER_2025"},
            {"text": "Researcher returned: RESEARCHER_MARKER_2025"},
        ],
        key="default",
    )

    body, session_id = _run_turn(
        http_client,
        runner_id=live_runner_id,
        agent_name=sub_agent_test_agent,
        user_text="Dispatch the researcher sub-agent.",
    )
    assert body["status"] == "completed"

    _wait_for_markers(http_client, session_id, "RESEARCHER_MARKER_2025")
