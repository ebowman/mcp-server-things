"""SIGINT/SIGTERM must terminate the real CLI promptly with clean teardown (hq-kz0)."""

import os
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest


def _run_and_signal(sig, tmp_path, transport="stdio", ready_marker="calling-mcp.run"):
    env = dict(os.environ)
    env["THINGS_MCP_BOOT_WATCHDOG_SECS"] = "0"
    env["THINGSDB"] = str(tmp_path / "nonexistent.thingsdatabase")
    args = ["--transport", transport]
    if transport == "http":
        with socket.socket() as sk:
            sk.bind(("127.0.0.1", 0))
            args += ["--port", str(sk.getsockname()[1])]
    proc = subprocess.Popen(
        [sys.executable, "-m", "things_mcp.main", *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True,
    )
    lines = []
    ready = threading.Event()

    def pump():
        for line in proc.stderr:
            lines.append(line)
            if ready_marker in line:
                ready.set()

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    try:
        assert ready.wait(30), "server never reached run phase:\n" + "".join(lines)
        time.sleep(1.0)  # let the event loop start serving
        proc.send_signal(sig)
        start = time.monotonic()
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("server did not exit within 5s of signal:\n" + "".join(lines))
        elapsed = time.monotonic() - start
    finally:
        if proc.poll() is None:
            proc.kill()
        t.join(5)
        proc.stdin.close()
        proc.stdout.close()
    return rc, "".join(lines), elapsed


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_terminates_cli_cleanly(sig, tmp_path):
    rc, err, elapsed = _run_and_signal(sig, tmp_path)
    assert rc == 0, err
    assert elapsed < 5
    assert "Traceback" not in err


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_runs_lifespan_teardown_http(sig, tmp_path):
    """HTTP transport exits gracefully: uvicorn's lifespan shutdown completes."""
    rc, err, elapsed = _run_and_signal(
        sig, tmp_path, transport="http", ready_marker="Application startup complete"
    )
    assert rc == 0, err
    assert elapsed < 5
    assert "Application shutdown complete" in err
    assert "Traceback" not in err
    assert "forcing exit" not in err
