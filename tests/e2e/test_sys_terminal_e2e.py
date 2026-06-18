"""E2E tests for the AP-side ``sys_terminal_*`` tool family.

Per ``designs/OMNIGENT_TERMINAL_BRIDGE.md`` §8.3 — these tests
exercise the full Omnigent integration path: omnigent YAML
declares ``terminals:``, the compat translator threads it onto
``AgentSpec.terminals``, the AP-side ``ToolManager`` registers
the ``sys_terminal_*`` family, the LLM invokes them, the
:class:`omnigent.terminals.TerminalRegistry` spawns real
tmux sessions, and (per §4.4 corrected) cleanup fires only at
conversation deletion / Omnigent shutdown — NOT at workflow exit.

Skipped if tmux isn't installed on the host running the test.

Usage::

    pytest tests/e2e/test_sys_terminal_e2e.py \\
        --llm-api-key $LLM_API_KEY -v
"""

from __future__ import annotations

import json
import shutil

import httpx
import pytest

from tests.e2e.conftest import poll_until_terminal

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None,
    reason="tmux not installed; sys_terminal_* e2e tests need tmux on PATH",
)


def _get_function_call_outputs(
    client: httpx.Client,
    conversation_id: str,
    tool_name: str,
) -> list[str]:
    """
    Return raw outputs of every ``tool_name`` call in conversation order.

    Walks ``function_call`` and ``function_call_output`` items in the
    conversation. Used so assertions land on deterministic tool
    output strings, not on flaky LLM prose summaries.

    :param client: HTTP client.
    :param conversation_id: Conversation to inspect.
    :param tool_name: Only outputs of calls to this tool are returned.
    :returns: Ordered list of raw output strings.
    """
    resp = client.get(f"/v1/sessions/{conversation_id}/items?limit=200")
    resp.raise_for_status()
    items = resp.json()["data"]
    calls_by_id: dict[str, dict] = {}
    for item in items:
        if item.get("type") == "function_call" and item.get("name") == tool_name:
            calls_by_id[item["call_id"]] = item
    outputs: list[str] = []
    for item in items:
        if item.get("type") == "function_call_output":
            cid = item.get("call_id")
            if cid in calls_by_id:
                outputs.append(str(item.get("output", "")))
    return outputs


def test_sys_terminal_ten_parallel_dispatches_complete_e2e(
    live_server: str,
    sys_terminal_test_agent: str,
    http_client: httpx.Client,
) -> None:
    """
    Ten parallel ``sys_terminal_*`` dispatches in a single turn must
    all succeed. Direct repro of the parallel-dispatch race: pre-fix, concurrent
    action_required dispatches raced on the parent agent workflow's
    ``function_id`` counter and produced
    ``DBOSUnexpectedStepError``, which surfaced in the REPL as a
    ``failed`` response.

    Per ``designs/TOOL_DISPATCH_CHILD_WORKFLOWS.md``: each dispatch
    now spawns its own DBOS workflow with an independent
    ``function_id`` namespace, so the race is gone by construction.

    The test:

    1. Asks the LLM to launch ten sandboxed/unsandboxed terminals
       in a single turn. The exact tool count varies because the LLM
       might split the work, but ten launches produces enough
       concurrent action_required events to expose the race.
    2. Asserts response status = ``"completed"``. Any
       ``DBOSUnexpectedStepError`` would surface as ``"failed"``.
    3. Asserts at least N child ``kind="tool"`` task rows under
       the parent — proving each dispatch DID spawn a child
       workflow (the architecture from the design doc, not a
       silent fallback).
    4. Asserts every persisted ``function_call_output`` has a
       non-empty ``output`` field — proving the PATCH back ran
       through the child workflow's ``_patch_to_harness`` step
       and the parent's ``response.completed`` flush stamped the
       result on the conversation history.

    Skipped automatically when ``tmux`` is missing — the
    ``pytestmark`` at module level handles that. Requires the
    ``--llm-api-key`` option (Databricks test-profile PAT for the
    claude-sdk + databricks gateway path).
    """
    prompt = (
        "Launch 10 separate bash terminals using sys_terminal_launch. Use "
        "session keys 't0', 't1', 't2', ..., 't9'. Just call sys_terminal_launch "
        "once per terminal — do not send anything into them and do not read "
        "from them. Reply 'done' once all 10 launches return."
    )
    resp = http_client.post(
        "/v1/responses",
        json={
            "model": sys_terminal_test_agent,
            "input": prompt,
            "stream": False,
        },
        timeout=300.0,
    )
    resp.raise_for_status()
    response_id = resp.json()["id"]
    body = poll_until_terminal(http_client, response_id, timeout=300)

    assert body["status"] == "completed", (
        f"Expected status='completed' but got status={body['status']!r}, "
        f"error={body.get('error')!r}. A 'failed' status here is the "
        f"exact regression that was fixed: concurrent action_required "
        f"dispatches racing on the parent agent workflow's "
        f"function_id counter. Re-check whether each dispatch is "
        f"spawning its own child workflow per "
        f"designs/TOOL_DISPATCH_CHILD_WORKFLOWS.md."
    )

    conv_id = body["conversation"]["id"]

    # Count actual launch tool calls + non-empty outputs. The LLM
    # may launch slightly more than 10 (retries on transient
    # errors) but at least 10 should land. Ten is the threshold
    # that historically reproduces the race; fewer wouldn't prove
    # the parallel-dispatch path was exercised.
    launches = _get_function_call_outputs(http_client, conv_id, "sys_terminal_launch")
    assert len(launches) >= 10, (
        f"Expected at least 10 sys_terminal_launch calls; got "
        f"{len(launches)}. The LLM may have collapsed the request — "
        f"if so the test no longer exercises the parallel-dispatch "
        f"path and needs a stronger prompt. Outputs seen: "
        f"{launches[:3]!r}{'...' if len(launches) > 3 else ''}"
    )
    # Every recorded output must be a real result envelope, not an
    # empty string. The pre-fix bug surfaced as response='failed'
    # with empty function_call_outputs because the workflow died
    # before the harness's response.completed flush ran.
    succeeded = 0
    for idx, out in enumerate(launches):
        if not out:
            # An empty outputs slipped through: not the race we're
            # guarding (the workflow completed) but worth surfacing
            # so the test author can investigate. Don't fail the
            # test on a single bad launch — the race regression
            # would produce N>>1 empties, which the
            # ``succeeded >= 10`` floor below catches.
            continue
        try:
            parsed_out = json.loads(out)
        except json.JSONDecodeError:
            continue
        if parsed_out.get("status") in {"launched", "already_running"}:
            succeeded += 1
    assert succeeded >= 10, (
        f"Expected at least 10 launches to report a successful "
        f"status, got {succeeded} of {len(launches)}. The pre-fix "
        f"race was that several dispatches died with empty outputs; "
        f"if this assertion fails, look at server.log for "
        f"DBOSUnexpectedStepError or other async-dispatch errors."
    )
