"""CLI validation of --timeout/--retry-count on utility subcommands (hq-m0i)."""
from unittest.mock import AsyncMock, patch

import pytest

from things_mcp import main as main_mod


def run(argv, capsys):
    with patch("sys.argv", ["mcp-server-things", *argv]), \
         patch.object(main_mod, "perform_health_check", new=AsyncMock(return_value=0)) as hc, \
         patch.object(main_mod, "test_applescript_connectivity", new=AsyncMock(return_value=0)) as ta:
        code = main_mod.main()
    return code, capsys.readouterr().err, hc, ta


FLAGS = ["--health-check", "--test-applescript"]


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize(
    "extra,needle",
    [
        (["--retry-count", "11"], "--retry-count"),
        (["--retry-count", "-1"], "--retry-count"),
        (["--timeout", "0"], "--timeout"),
        (["--timeout", "301"], "--timeout"),
    ],
)
def test_invalid_overrides_exit_2(flag, extra, needle, capsys):
    code, err, hc, ta = run([flag, *extra], capsys)
    assert code == 2
    assert needle in err and "allowed range" in err
    assert "Traceback" not in err
    hc.assert_not_called()
    ta.assert_not_called()


@pytest.mark.parametrize("flag", FLAGS)
def test_missing_env_file_exit_2(flag, tmp_path, capsys):
    missing = tmp_path / "nope.env"
    code, err, hc, ta = run([flag, "--env-file", str(missing)], capsys)
    assert code == 2
    assert f"env file not found: {missing}" in err
    hc.assert_not_called()
    ta.assert_not_called()


@pytest.mark.parametrize("flag", FLAGS)
def test_valid_overrides_forwarded(flag, capsys):
    code, err, hc, ta = run([flag, "--timeout", "2.5", "--retry-count", "0"], capsys)
    assert code == 0
    target = hc if flag == "--health-check" else ta
    other = ta if flag == "--health-check" else hc
    target.assert_awaited_once_with(2.5, 0)
    assert isinstance(target.await_args.args[0], float)
    other.assert_not_called()


@pytest.mark.parametrize("flag", FLAGS)
def test_invalid_env_file_value_exit_2(flag, tmp_path, monkeypatch, capsys):
    # Env-file loading mutates os.environ; setenv first so monkeypatch restores it.
    monkeypatch.setenv("THINGS_MCP_APPLESCRIPT_RETRY_COUNT", "2")
    env = tmp_path / "bad.env"
    env.write_text("THINGS_MCP_APPLESCRIPT_RETRY_COUNT=99\n")
    code, err, hc, ta = run([flag, "--env-file", str(env)], capsys)
    assert code == 2
    assert "invalid value for" in err and "RETRY_COUNT" in err
    assert "Traceback" not in err
    hc.assert_not_called()
    ta.assert_not_called()
