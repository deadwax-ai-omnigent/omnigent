from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github/scripts/fork-e2e/should-mirror.sh"


def _run(
    tmp_path: Path,
    *,
    approvers: str = "",
    maintainers: str = "alice bob",
) -> dict[str, str]:
    """
    Run should-mirror.sh against a mocked ``gh`` and return its outputs.

    The approval-based gate makes exactly one ``gh`` call, which the mock answers:

    - ``api repos/{repo}/pulls/{pr}/reviews ...`` -> *approvers*, the login(s) of
      accounts whose latest non-COMMENTED review state is APPROVED (empty if none).

    :param tmp_path: Pytest tmp dir for the mock + output file.
    :param approvers: Space-separated logins the reviews mock returns as
        approvers; empty means no approving reviews.
    :param maintainers: Space-separated maintainer logins (as
        load-maintainers.sh would emit); empty means none.
    :returns: Parsed ``key=value`` GITHUB_OUTPUT lines, e.g.
        ``{"mirror": "true", "reason": "..."}``.
    """
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -uo pipefail\n"
        # gh api repos/{repo}/pulls/{pr}/reviews --paginate --jq '...'
        'if [[ "$1" == "api" ]]; then\n'
        '  case "$2" in\n'
        '    *pulls/*reviews*) [[ -n "$MOCK_APPROVERS" ]]'
        ' && printf "%s\\n" $MOCK_APPROVERS; exit 0 ;;\n'
        "  esac\n"
        "fi\n"
        'echo "unexpected gh invocation: $*" >&2\n'
        "exit 1\n"
    )
    gh.chmod(0o755)

    out_file = tmp_path / "gh_output"
    out_file.touch()

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "GH_TOKEN": "unused",
            "REPO": "test/repo",
            "PR": "7",
            "MAINTAINERS": maintainers,
            "GITHUB_OUTPUT": str(out_file),
            "MOCK_APPROVERS": approvers,
        }
    )
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"script failed: {proc.stderr}"
    outputs: dict[str, str] = {}
    for line in out_file.read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            outputs[key] = value
    return outputs


def test_approved_by_maintainer_mirrors(tmp_path: Path) -> None:
    """A maintainer's approving review opens the gate.

    The whole contract: secret-bearing e2e runs only after a maintainer approves.
    Asserts ``mirror=true`` and that the reason names the approving maintainer.
    """
    out = _run(tmp_path, approvers="bob")
    assert out["mirror"] == "true"
    assert "approved by maintainer" in out["reason"]


def test_maintainer_match_is_case_insensitive(tmp_path: Path) -> None:
    """Approver vs MAINTAINER comparison is case-insensitive.

    GitHub logins are compared lowercased, so an approver ``Bob`` still
    opens the gate against a ``bob`` MAINTAINER entry.
    """
    out = _run(tmp_path, approvers="Bob", maintainers="alice bob")
    assert out["mirror"] == "true"


def test_no_approvals_does_not_mirror(tmp_path: Path) -> None:
    """Without any approving reviews the gate stays shut.

    No approval means no secret-bearing e2e on a fork PR. Asserts
    ``mirror=false`` and an awaiting-approval reason.
    """
    out = _run(tmp_path, approvers="")
    assert out["mirror"] == "false"
    assert "awaiting approval" in out["reason"]


def test_approved_by_non_maintainer_does_not_mirror(tmp_path: Path) -> None:
    """An approval from a NON-maintainer must not open the gate.

    Write access lets non-maintainers submit approving reviews, so approval
    alone is insufficient: the approver must be in MAINTAINER. ``eve`` approves
    but isn't a maintainer, so ``mirror=false``.
    """
    out = _run(tmp_path, approvers="eve", maintainers="alice bob")
    assert out["mirror"] == "false"
    assert "no approving review from a maintainer" in out["reason"]


def test_no_maintainers_loaded_does_not_mirror(tmp_path: Path) -> None:
    """An empty MAINTAINER list fails closed.

    With no maintainers to verify against, even a valid approval can't be
    trusted, so the gate stays shut regardless of the approver.
    """
    out = _run(tmp_path, approvers="bob", maintainers="")
    assert out["mirror"] == "false"
    assert "no maintainers" in out["reason"]


def test_multiple_approvers_first_maintainer_wins(tmp_path: Path) -> None:
    """When multiple users approve, the first matching maintainer opens the gate."""
    out = _run(tmp_path, approvers="eve alice", maintainers="alice bob")
    assert out["mirror"] == "true"
    assert "@alice" in out["reason"]
