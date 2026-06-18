"""End-to-end test: a sub-agent's approval prompt surfaces on the parent.

This test exercises the native-CLI harnesses (claude-native, codex-native)
in PROMPTING permission mode, where the worker raises a real approval that
must be forwarded and answered from the parent session.

SKIPPED for mock-LLM migration: the native CLI harnesses (claude, codex)
authenticate via their own OAuth / CLI binary, not through the mock-LLM
server. The test also modifies real developer config files
(~/.codex/config.toml, ~/.claude/settings.json) to force prompting mode.
These tests cannot be meaningfully mocked -- they exist specifically to
exercise the real native-CLI approval plumbing. The existing env-var gate
(OMNIGENT_E2E_SUBAGENT_ELICIT=1) already keeps them off CI.

The approval-forwarding invariant is covered at the unit/integration level
by tests in tests/runner/test_app_sessions_native.py. This e2e test is
retained as an opt-in dev-box CUJ for when the native CLIs are available.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "sub-agent elicitation forwarding e2e requires real native CLI "
        "harnesses (claude/codex) with OAuth authentication and developer "
        "config file toggling -- cannot run against mock LLM. "
        "Set OMNIGENT_E2E_SUBAGENT_ELICIT=1 and restore the original test "
        "to run against a real Databricks workspace."
    ),
)


def test_subagent_prompt_surfaces_on_parent_and_resolves_via_child() -> None:
    """Placeholder -- see module-level skip marker."""
