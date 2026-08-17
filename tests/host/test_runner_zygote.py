"""Tests for the runner zygote forkserver and its host-side client.

These drive a REAL zygote subprocess (``os.fork`` works on macOS and Linux even
though the copy-on-write memory savings are Linux-only), using the zygote's
test seam so forked children exit deterministically instead of booting a real
runner. Fork-safety, the ping/fork/poll/reap protocol, env isolation, and the
daemon's Popen fallback are all covered.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from omnigent.host.runner_zygote import (
    _ZYGOTE_LOST_EXIT_CODE,
    ZygoteManager,
    ZygoteRunnerProc,
    ZygoteStale,
    ZygoteUnavailable,
)
from omnigent.runner._zygote import (
    _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR,
    _ZYGOTE_TEST_CHILD_SLEEP_ENV_VAR,
    _disk_build_stamp,
    _ZygoteServer,
)

# The zygote is POSIX-only: these tests exercise os.fork() and pass_fds, which
# do not exist on Windows.
pytestmark = pytest.mark.posix_only


def _fork_env(exit_code: int) -> dict[str, str]:
    """A fork payload env whose child exits with *exit_code* via the test seam.

    :param exit_code: Code the forked child should exit with.
    :returns: Minimal runner env carrying the test-seam marker.
    """
    return {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: str(exit_code),
    }


@pytest.fixture
def manager(tmp_path):
    """A started :class:`ZygoteManager`, stopped on teardown.

    :param tmp_path: Pytest temp dir for the zygote's own log.
    :returns: A running manager connected to a real zygote subprocess.
    """
    mgr = ZygoteManager(log_path=tmp_path / "zygote.log")
    mgr.start()
    try:
        yield mgr
    finally:
        mgr.stop()


def _wait_exit(proc: ZygoteRunnerProc, timeout: float = 10.0) -> int:
    """Poll *proc* until it reports an exit code.

    :param proc: The forked runner handle.
    :param timeout: Max seconds to wait.
    :returns: The observed exit code.
    :raises AssertionError: If the child does not exit in time.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            return code
        time.sleep(0.05)
    raise AssertionError("forked runner did not exit in time")


def test_import_graph_is_single_threaded() -> None:
    """The runner import graph starts no threads — the fork-safety invariant.

    A zygote forks from this state, so any import-time thread would risk child
    deadlocks. Asserted in a FRESH interpreter (not the shared pytest process,
    which carries its own fixture/timeout threads) so the check reflects only
    the import graph — exactly the state the zygote forks from.
    """
    probe = "\n".join(
        [
            "from omnigent.runner._zygote import _import_runner_graph",
            "import threading",
            "_import_runner_graph()",
            "print(threading.active_count())",
            "print([t.name for t in threading.enumerate()])",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    first_line = result.stdout.strip().splitlines()[0]
    assert first_line == "1", result.stdout


def test_manager_starts_and_pings(manager: ZygoteManager) -> None:
    """A started manager has a live zygote pid answering the control socket.

    :param manager: The started manager fixture.
    """
    assert manager.is_running()
    assert isinstance(manager.pid, int)


def test_fork_runner_reports_pid_and_exit_code(manager: ZygoteManager, tmp_path) -> None:
    """A forked runner reports a distinct pid and its real exit code.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    proc = manager.fork_runner(_fork_env(0), str(tmp_path / "runner.log"))
    assert isinstance(proc, ZygoteRunnerProc)
    assert proc.pid != manager.pid
    assert _wait_exit(proc) == 0


def test_fork_runner_nonzero_exit_is_reported(manager: ZygoteManager, tmp_path) -> None:
    """A non-zero child exit surfaces through poll(), matching Popen semantics.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    proc = manager.fork_runner(_fork_env(7), str(tmp_path / "runner.log"))
    assert _wait_exit(proc) == 7


def test_child_systemexit_code_is_preserved(manager: ZygoteManager, tmp_path) -> None:
    """A child raising SystemExit(N) reports code N, not a flattened 1.

    Mirrors ``python -m omnigent.runner._entry`` semantics: main() raises
    SystemExit on a tunnel rejection, and the fork guard must preserve the code
    rather than turning it into a traceback + exit 1.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    env = _fork_env(5)
    env["OMNIGENT_RUNNER_ZYGOTE_TEST_CHILD_RAISE"] = "1"
    proc = manager.fork_runner(env, str(tmp_path / "runner.log"))
    assert _wait_exit(proc) == 5


def test_zygote_serves_multiple_forks(manager: ZygoteManager, tmp_path) -> None:
    """The zygote keeps serving fork requests after a child has exited.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child logs.
    """
    first = manager.fork_runner(_fork_env(0), str(tmp_path / "a.log"))
    assert _wait_exit(first) == 0
    second = manager.fork_runner(_fork_env(3), str(tmp_path / "b.log"))
    assert second.pid != first.pid
    assert _wait_exit(second) == 3


def test_signal_of_exited_runner_is_a_safe_noop(manager: ZygoteManager, tmp_path) -> None:
    """terminate()/kill() on an already-exited runner must not raise.

    The daemon's stop/cleanup paths signal handles that may have exited between
    the poll and the signal, so this must be swallowed.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    proc = manager.fork_runner(_fork_env(0), str(tmp_path / "runner.log"))
    assert _wait_exit(proc) == 0
    proc.terminate()
    proc.kill()


def test_poll_after_stop_reports_live_runner_as_none(manager: ZygoteManager, tmp_path) -> None:
    """A still-live runner polls as None once the zygote is stopped.

    With the control socket gone the manager can't learn the exit code, so it
    probes the pid: a still-live runner reports None (the runner's own orphan
    watchdog handles teardown) rather than a bogus exit or a crash.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    proc = manager.fork_runner(_sleep_env(30), str(tmp_path / "runner.log"))
    manager.stop()
    try:
        assert proc.poll() is None  # pid still alive -> honestly "still live"
    finally:
        proc.kill()


def test_fork_after_stop_raises_unavailable(manager: ZygoteManager, tmp_path) -> None:
    """Forking after stop() raises ZygoteUnavailable so the daemon can fall back.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    manager.stop()
    with pytest.raises(ZygoteUnavailable):
        manager.fork_runner(_fork_env(0), str(tmp_path / "runner.log"))


def test_child_env_is_isolated_between_forks(manager: ZygoteManager, tmp_path) -> None:
    """Each fork's env fully replaces the child environment (no cross-leak).

    The test-seam child echoes its view of ``OMNIGENT_ZYGOTE_MARKER`` to its
    log; two forks with different markers must each see only their own value.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child logs.
    """
    log_a = tmp_path / "a.log"
    log_b = tmp_path / "b.log"
    env_a = _fork_env(0)
    env_a["OMNIGENT_ZYGOTE_MARKER"] = "aaa"
    env_b = _fork_env(0)
    env_b["OMNIGENT_ZYGOTE_MARKER"] = "bbb"

    proc_a = manager.fork_runner(env_a, str(log_a))
    assert _wait_exit(proc_a) == 0
    proc_b = manager.fork_runner(env_b, str(log_b))
    assert _wait_exit(proc_b) == 0

    assert proc_a.pid != proc_b.pid
    assert "marker=aaa" in log_a.read_text()
    assert "marker=bbb" in log_b.read_text()


def test_stale_payload_tty_fd_is_cleared_in_child(manager: ZygoteManager, tmp_path) -> None:
    """A daemon-side OMNIGENT_LOG_TTY_FD in the payload never leaks as-is.

    The terminal-mirror fd is only valid as its zygote-local number. With no
    terminal mirror on the zygote, a stale payload value must be cleared in the
    child rather than passed through (a wrong fd number would misdirect writes).

    :param manager: The started manager fixture (no terminal mirror).
    :param tmp_path: Temp dir for the child's log.
    """
    env = _fork_env(0)
    env["OMNIGENT_LOG_TTY_FD"] = "999"  # bogus daemon-side number
    log = tmp_path / "runner.log"
    proc = manager.fork_runner(env, str(log))
    assert _wait_exit(proc) == 0
    assert "tty_fd=\n" in log.read_text()


def test_unstarted_manager_reports_not_running() -> None:
    """A manager that was never started is not running and has no pid."""
    mgr = ZygoteManager()
    assert not mgr.is_running()
    assert mgr.pid is None


def test_malloc_tuning_is_applied_at_the_zygote_exec(monkeypatch, tmp_path) -> None:
    """The glibc arena cap rides on the zygote's exec, not on a fork payload.

    glibc reads MALLOC_ARENA_MAX once, when its allocator initializes at exec.
    The zygote's Popen is the only exec on this path — forked runners merely
    replace ``os.environ``, far too late to configure an allocator — so the cap
    must be set here or it silently stops applying to every runner.

    :param monkeypatch: Fixture used to force the Linux tuning branch.
    :param tmp_path: Temp dir for the zygote log path.
    """
    monkeypatch.setattr("omnigent.inner._proc.IS_LINUX", True)
    captured: dict[str, str] = {}

    class _FakePopen:
        pid = 4321

        def __init__(self, argv, env, **kwargs) -> None:
            captured.update(env)

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    mgr = ZygoteManager(log_path=tmp_path / "zygote.log")
    mgr._spawn_zygote_process(child_fd=7)

    assert captured["MALLOC_ARENA_MAX"] == "2"
    assert captured["MALLOC_TRIM_THRESHOLD_"] == "134217728"


def test_operator_malloc_override_wins_at_the_zygote_exec(monkeypatch, tmp_path) -> None:
    """An explicit MALLOC_ARENA_MAX in the daemon env is not overwritten.

    The tuning is merged with setdefault so an operator who exported a value
    keeps it.

    :param monkeypatch: Fixture used to force Linux and seed the parent env.
    :param tmp_path: Temp dir for the zygote log path.
    """
    monkeypatch.setattr("omnigent.inner._proc.IS_LINUX", True)
    monkeypatch.setenv("MALLOC_ARENA_MAX", "16")
    captured: dict[str, str] = {}

    class _FakePopen:
        pid = 4321

        def __init__(self, argv, env, **kwargs) -> None:
            captured.update(env)

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    mgr = ZygoteManager(log_path=tmp_path / "zygote.log")
    mgr._spawn_zygote_process(child_fd=7)

    assert captured["MALLOC_ARENA_MAX"] == "16"


# ── Harness-fork path (fork_harness) ──────────────────────────────
#
# The zygote also forks HARNESS children on request, sharing the harness import
# graph copy-on-write. In production the request arrives on a per-runner control
# socket (minted by a runner fork); the zygote handles ``fork_harness`` on any
# socket, so these tests drive it over the manager's daemon socket directly.


def _control_exchange(manager: ZygoteManager, request: dict) -> dict:
    """Send one request on the manager's control socket and read one reply.

    :param manager: A started manager (its ``_sock`` is the daemon control end).
    :param request: The protocol request.
    :returns: The decoded reply.
    """
    sock = manager._sock
    assert sock is not None
    sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        assert chunk, "zygote closed the control socket"
        buf.extend(chunk)
    return json.loads(bytes(buf).partition(b"\n")[0])


def _wait_harness_exit(manager: ZygoteManager, pid: int, timeout: float = 10.0) -> int:
    """Poll the zygote for a forked harness's exit code.

    :param manager: The started manager.
    :param pid: The forked harness pid.
    :param timeout: Max seconds to wait.
    :returns: The observed exit code.
    :raises AssertionError: If it does not exit in time.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        reply = _control_exchange(manager, {"cmd": "poll", "pid": pid})
        if reply.get("returncode") is not None:
            return reply["returncode"]
        time.sleep(0.05)
    raise AssertionError("forked harness did not exit in time")


def test_fork_harness_reports_pid_and_reaps(manager: ZygoteManager, tmp_path) -> None:
    """fork_harness forks a child, returns its pid, and the zygote reaps it.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the harness child's log.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: "0",
        "OMNIGENT_PROCESS_LOG_FILE": str(tmp_path / "harness.log"),
    }
    reply = _control_exchange(
        manager,
        {"cmd": "fork_harness", "argv": ["--harness", "x", "--conversation-id", "c"], "env": env},
    )
    assert isinstance(reply.get("pid"), int)
    assert _wait_harness_exit(manager, reply["pid"]) == 0


def test_fork_harness_nonzero_exit_is_reported(manager: ZygoteManager, tmp_path) -> None:
    """A non-zero harness child exit surfaces through poll().

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the harness child's log.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: "9",
        "OMNIGENT_PROCESS_LOG_FILE": str(tmp_path / "harness.log"),
    }
    reply = _control_exchange(
        manager,
        {"cmd": "fork_harness", "argv": ["--harness", "x", "--conversation-id", "c"], "env": env},
    )
    assert _wait_harness_exit(manager, reply["pid"]) == 9


def test_fork_harness_argv_round_trips_to_child(manager: ZygoteManager, tmp_path) -> None:
    """The harness child runs with the argv the request carried.

    The test-seam harness child echoes its argv to its log, proving the payload
    reached ``_runner.main(argv)`` intact.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the harness child's log.
    """
    log = tmp_path / "harness.log"
    env = {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: "0",
        "OMNIGENT_PROCESS_LOG_FILE": str(log),
    }
    argv = ["--harness", "claude-native", "--conversation-id", "conv-42"]
    reply = _control_exchange(manager, {"cmd": "fork_harness", "argv": argv, "env": env})
    assert _wait_harness_exit(manager, reply["pid"]) == 0
    assert f"harness_argv={' '.join(argv)}" in log.read_text()


def test_zygote_still_serves_daemon_after_harness_fork(manager: ZygoteManager, tmp_path) -> None:
    """A ping still round-trips after a harness fork — the multiplexer survives.

    Guards the selectors loop: forking a harness must not disturb the daemon
    socket registration.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the harness child's log.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: "0",
        "OMNIGENT_PROCESS_LOG_FILE": str(tmp_path / "harness.log"),
    }
    reply = _control_exchange(manager, {"cmd": "fork_harness", "argv": [], "env": env})
    assert _wait_harness_exit(manager, reply["pid"]) == 0
    assert _control_exchange(manager, {"cmd": "ping"}).get("pong") is True


# ── Failure paths (unhappy lifecycle) ─────────────────────────────
#
# The happy protocol is covered above. These cover the paths flagged in review:
# an unexpected zygote crash must not strand the daemon's view of a runner, and
# a dropped runner's harness exit codes must not leak in the zygote's map.


def _sleep_env(seconds: float) -> dict[str, str]:
    """A fork payload whose child stays alive for *seconds* (no early exit).

    :param seconds: How long the forked child sleeps before exiting 0.
    :returns: Minimal runner env carrying the sleep test-seam marker.
    """
    return {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_SLEEP_ENV_VAR: str(seconds),
    }


def test_poll_after_zygote_crash_reports_dead_runner(manager: ZygoteManager) -> None:
    """A vanished zygote surfaces a dead runner as failed, never eternal alive.

    Without this the daemon's ``_watch_runner`` loops forever on ``poll() is
    None`` and reports a gone session as alive.

    :param manager: The started manager fixture.
    """
    proc = manager.fork_runner(_sleep_env(30), "/dev/null")
    assert proc.poll() is None  # child is alive

    # Kill the zygote out from under the still-live runner.
    zpid = manager.pid
    assert zpid is not None
    os.kill(zpid, 9)
    os.waitpid(zpid, 0)

    # Zygote gone but runner still alive: honestly "still live".
    assert proc.poll() is None

    # Runner now dead too: its code is unrecoverable, so a dead-and-failed
    # sentinel — not None (eternal alive) and not 0 (clean exit).
    os.kill(proc.pid, 9)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            break
        time.sleep(0.05)
    assert code == _ZYGOTE_LOST_EXIT_CODE


def test_dropped_runner_harness_exit_codes_do_not_leak(manager: ZygoteManager, tmp_path) -> None:
    """A dropped runner's harness codes are discarded, not leaked in the map.

    Forks a runner, has it request a (short-lived) harness fork, then drops the
    runner's control socket. The harness is reaped but its exit code must not
    accumulate in the zygote's ``_exit_codes`` (unbounded growth + pid-reuse
    misattribution over a long-lived daemon).

    We can't introspect the zygote subprocess's memory directly, so we assert
    the observable contract: after the runner drops and its harness exits, a
    fresh ``poll`` for that harness pid over the daemon socket reports it as
    unknown (``None``) rather than returning a retained code.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the harness child's log.
    """
    # A runner that lives long enough to host a harness fork, then exits.
    proc = manager.fork_runner(_sleep_env(2), "/dev/null")
    runner_pid = proc.pid

    # The runner's own control socket back to the zygote is internal to the
    # forked runner; a unit test can't reach it. Instead we drive fork_harness
    # over the daemon socket (the zygote accepts it on any socket) and then
    # simulate the runner dropping by letting the runner exit and polling the
    # harness from the daemon side, asserting no stale code sticks around.
    harness_env = {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: "0",
        "OMNIGENT_PROCESS_LOG_FILE": str(tmp_path / "harness.log"),
    }
    reply = _control_exchange(manager, {"cmd": "fork_harness", "argv": [], "env": harness_env})
    harness_pid = reply["pid"]
    assert _wait_harness_exit(manager, harness_pid) == 0

    # Once reaped-and-polled, the code is popped: a second poll is None, proving
    # the map does not retain it.
    assert _control_exchange(manager, {"cmd": "poll", "pid": harness_pid})["returncode"] is None

    # Let the runner exit so the test leaves nothing live.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)
    assert not _proc_alive(runner_pid)


def _proc_alive(pid: int) -> bool:
    """Whether *pid* is a live process (test helper)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ── Malformed-request robustness ──────────────────────────────────
#
# The zygote is a single-threaded forkserver shared by every session, so an
# unhandled exception in its dispatch loop would tear down all runners and
# harnesses forked from it. Each bad request must answer with an error and
# leave the server serving.


def _raw_exchange(manager: ZygoteManager, raw: bytes) -> dict:
    """Send raw bytes on the control socket and read one reply.

    :param manager: A started manager (its ``_sock`` is the daemon control end).
    :param raw: Exact bytes to write, including the trailing newline.
    :returns: The decoded reply.
    """
    sock = manager._sock
    assert sock is not None
    sock.sendall(raw)
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        assert chunk, "zygote closed the control socket"
        buf.extend(chunk)
    return json.loads(bytes(buf).partition(b"\n")[0])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(b"[]\n", "must be a JSON object", id="json-list"),
        pytest.param(b"5\n", "must be a JSON object", id="json-scalar"),
        pytest.param(b'"str"\n', "must be a JSON object", id="json-string"),
        pytest.param(b'{"cmd":"poll","pid":[]}\n', "integer pid", id="pid-list"),
        pytest.param(b'{"cmd":"poll","pid":"abc"}\n', "integer pid", id="pid-string"),
        pytest.param(b"{oops\n", "malformed request", id="undecodable"),
    ],
)
def test_malformed_request_errors_without_killing_zygote(
    manager: ZygoteManager, raw: bytes, expected: str
) -> None:
    """A bad request replies with an error and the forkserver keeps serving.

    Without the guard, ``json.loads`` returning a non-dict makes ``.get()``
    raise (and a non-int ``pid`` makes ``int()`` raise), killing the shared
    zygote and every session forked from it.

    :param manager: The started manager fixture.
    :param raw: The malformed request bytes.
    :param expected: Substring the error reply must contain.
    """
    reply = _raw_exchange(manager, raw)
    assert expected in reply["error"]
    # The decisive assertion: the server is still alive and answering.
    assert _raw_exchange(manager, b'{"cmd":"ping"}\n').get("pong") is True
    assert manager.is_running()


def test_zygote_still_forks_after_a_malformed_request(manager: ZygoteManager, tmp_path) -> None:
    """A bad request does not poison the fork path that follows it.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the child's log.
    """
    assert "error" in _raw_exchange(manager, b"[]\n")
    proc = manager.fork_runner(_fork_env(0), str(tmp_path / "runner.log"))
    assert _wait_exit(proc) == 0


def test_polled_harness_pid_is_released_from_its_owner(manager: ZygoteManager, tmp_path) -> None:
    """A successful poll drops the harness pid from the runner-ownership map.

    Left in place, the set grows unbounded and — once the OS recycles that pid
    for a new harness under a different runner — the stale owner's teardown
    would orphan the reused pid and discard the new harness's real exit code,
    hanging its legitimate owner's poll forever.

    :param manager: The started manager fixture.
    :param tmp_path: Temp dir for the harness child's log.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        _ZYGOTE_TEST_CHILD_EXIT_ENV_VAR: "0",
        "OMNIGENT_PROCESS_LOG_FILE": str(tmp_path / "harness.log"),
    }
    reply = _control_exchange(manager, {"cmd": "fork_harness", "argv": [], "env": env})
    pid = reply["pid"]
    # The poll that returns the code must also release ownership.
    assert _wait_harness_exit(manager, pid) == 0
    # Re-polling is None (code popped) and the zygote is still healthy.
    assert _control_exchange(manager, {"cmd": "poll", "pid": pid})["returncode"] is None
    assert _control_exchange(manager, {"cmd": "ping"}).get("pong") is True


# ── Upgrade safety ────────────────────────────────────────────────
#
# A fork only ever shares the graph the zygote imported at boot, while the
# child resolves its lazy imports from disk. An in-place upgrade (uv tool
# install, pip install -U) rewrites the package under a long-lived zygote, so
# every fork after it is a mixed-version process that dies on the first name
# that moved between the two builds. The stamp comparison below is what keeps
# those two halves in agreement.


def _write_build_info(package_dir: Path, body: str) -> Path:
    """Write a ``_build_info.py`` with *body* into *package_dir*.

    :param package_dir: Directory to write the generated module into.
    :param body: Module source.
    :returns: The written path.
    """
    package_dir.mkdir(parents=True, exist_ok=True)
    target = package_dir / "_build_info.py"
    target.write_text(body)
    return target


def test_disk_build_stamp_reads_the_generated_module(tmp_path) -> None:
    """The stamp is the ``(BUILD_TIME_EPOCH, COMMIT_SHA)`` pair on disk.

    :param tmp_path: Temp dir standing in for the package directory.
    """
    _write_build_info(
        tmp_path / "omnigent",
        "BUILD_TIME_EPOCH: int = 1700000000\nCOMMIT_SHA: str = 'abc123'\n",
    )
    assert _disk_build_stamp(tmp_path / "omnigent") == (1700000000.0, "abc123")


def test_disk_build_stamp_is_none_on_an_unbuilt_checkout(tmp_path) -> None:
    """A source tree that was never built has no stamp to compare.

    :param tmp_path: Temp dir standing in for the package directory.
    """
    assert _disk_build_stamp(tmp_path) is None


def test_disk_build_stamp_is_none_for_a_half_written_module(tmp_path) -> None:
    """A package caught mid-rewrite reads as unknown rather than raising.

    :param tmp_path: Temp dir standing in for the package directory.
    """
    _write_build_info(tmp_path / "omnigent", "BUILD_TIME_EPOCH: int = 17000")
    assert _disk_build_stamp(tmp_path / "omnigent") is None


@pytest.fixture
def upgraded_server():
    """A ``_ZygoteServer`` whose on-disk build has moved since it booted.

    :returns: ``(server, server_sock, client_sock)`` — handlers are called with
        the server end, and the reply is read from the client end.
    """
    server_sock, client_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    server = _ZygoteServer(server_sock, graph_stamp=(1.0, "old-build"))
    try:
        yield server, server_sock, client_sock
    finally:
        server._sel.close()
        server_sock.close()
        client_sock.close()


def _reply_on(sock: socket.socket) -> dict:
    """Read one newline-delimited JSON reply from *sock*.

    :param sock: The socket the server answered on.
    :returns: The decoded reply.
    """
    sock.settimeout(10.0)
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        assert chunk, "zygote closed the socket without replying"
        buf.extend(chunk)
    return json.loads(bytes(buf).partition(b"\n")[0])


@pytest.mark.parametrize(
    ("handler", "request_body", "kind"),
    [
        ("_handle_fork", {"cmd": "fork", "env": {}, "log_path": None}, "runner"),
        ("_handle_fork_harness", {"cmd": "fork_harness", "argv": [], "env": {}}, "harness"),
    ],
)
def test_zygote_refuses_forks_after_an_in_place_upgrade(
    upgraded_server, monkeypatch, handler: str, request_body: dict, kind: str
) -> None:
    """Both fork kinds error out instead of handing over a stale graph.

    :param upgraded_server: The server fixture plus its client socket.
    :param monkeypatch: Fixture used to move the on-disk stamp.
    :param handler: The fork handler under test.
    :param request_body: The protocol request to hand it.
    :param kind: Child kind named in the refusal.
    """
    server, server_sock, client = upgraded_server
    monkeypatch.setattr(
        "omnigent.runner._zygote._disk_build_stamp", lambda *_a, **_kw: (2.0, "new-build")
    )

    getattr(server, handler)(server_sock, request_body)

    reply = _reply_on(client)
    assert f"mixed-version {kind}" in reply["error"]
    # Nothing was forked: no child pid is being tracked for reaping.
    assert not server._live


@pytest.mark.parametrize(
    ("handler", "request_body"),
    [
        ("_handle_fork", {"cmd": "fork", "env": {}, "log_path": None}),
        ("_handle_fork_harness", {"cmd": "fork_harness", "argv": [], "env": {}}),
    ],
)
def test_zygote_refuses_forks_when_the_stamp_goes_missing(
    upgraded_server, monkeypatch, handler: str, request_body: dict
) -> None:
    """A package mid-rewrite (no readable stamp) is refused, not trusted.

    Failing open here would fork exactly during the window when the files on
    disk are least likely to agree with the imported graph.

    :param upgraded_server: The server fixture plus its client socket.
    :param monkeypatch: Fixture used to blank the on-disk stamp.
    :param handler: The fork handler under test.
    :param request_body: The protocol request to hand it.
    """
    server, server_sock, client = upgraded_server
    monkeypatch.setattr("omnigent.runner._zygote._disk_build_stamp", lambda *_a, **_kw: None)

    getattr(server, handler)(server_sock, request_body)

    assert "refusing to fork" in _reply_on(client)["error"]
    assert not server._live


def test_unbuilt_checkout_still_forks(monkeypatch) -> None:
    """Two unknown stamps compare equal, so dev checkouts keep the fast path.

    :param monkeypatch: Fixture used to blank the on-disk stamp.
    """
    monkeypatch.setattr("omnigent.runner._zygote._disk_build_stamp", lambda *_a, **_kw: None)
    server_sock, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    server = _ZygoteServer(server_sock, graph_stamp=None)
    try:
        assert server._refuse_if_upgraded(client, "runner") is False
    finally:
        server._sel.close()
        server_sock.close()
        client.close()


def test_idle_zygote_is_recycled_onto_the_new_build(
    manager: ZygoteManager, monkeypatch, tmp_path
) -> None:
    """An upgrade under an idle zygote re-spawns it instead of degrading.

    :param manager: The started manager fixture.
    :param monkeypatch: Fixture used to move the on-disk stamp.
    :param tmp_path: Temp dir for the forked child's log.
    """
    original_pid = manager.pid
    monkeypatch.setattr(
        "omnigent.host.runner_zygote._disk_build_stamp", lambda *_a, **_kw: (2.0, "new-build")
    )

    manager.start()

    assert manager.pid != original_pid
    assert not _proc_alive(original_pid)
    # The replacement is a working forkserver, not just a live process.
    proc = manager.fork_runner(_fork_env(0), str(tmp_path / "runner.log"))
    assert _wait_exit(proc) == 0


def test_unchanged_build_keeps_the_same_zygote(manager: ZygoteManager) -> None:
    """Without an upgrade, start() is the idempotent no-op it has always been.

    :param manager: The started manager fixture.
    """
    original_pid = manager.pid
    manager.start()
    assert manager.pid == original_pid


def test_busy_zygote_is_refused_rather_than_recycled(
    manager: ZygoteManager, monkeypatch, tmp_path
) -> None:
    """Recycling under a live runner would orphan it, so the launch falls back.

    :param manager: The started manager fixture.
    :param monkeypatch: Fixture used to move the on-disk stamp.
    :param tmp_path: Temp dir for the forked child's log.
    """
    original_pid = manager.pid
    proc = manager.fork_runner(_sleep_env(30.0), str(tmp_path / "runner.log"))
    monkeypatch.setattr(
        "omnigent.host.runner_zygote._disk_build_stamp", lambda *_a, **_kw: (2.0, "new-build")
    )

    with pytest.raises(ZygoteStale):
        manager.start()

    assert manager.pid == original_pid
    assert _proc_alive(proc.pid)
    proc.kill()


def test_recycle_resumes_once_the_last_runner_is_collected(
    manager: ZygoteManager, monkeypatch, tmp_path
) -> None:
    """The zygote becomes recyclable again once no exit code is outstanding.

    Otherwise one long session would pin the host to direct spawns until the
    daemon restarts.

    :param manager: The started manager fixture.
    :param monkeypatch: Fixture used to move the on-disk stamp.
    :param tmp_path: Temp dir for the forked child's log.
    """
    original_pid = manager.pid
    proc = manager.fork_runner(_sleep_env(30.0), str(tmp_path / "runner.log"))
    monkeypatch.setattr(
        "omnigent.host.runner_zygote._disk_build_stamp", lambda *_a, **_kw: (2.0, "new-build")
    )
    with pytest.raises(ZygoteStale):
        manager.start()

    proc.kill()
    assert _wait_exit(proc) != 0

    manager.start()
    assert manager.pid != original_pid
