"""Guard packaging entry points against drift/breakage.

These tests lock down that `pyproject.toml`'s `[project.scripts]` entry
points (`mcp-server-things`, `things-mcp`) resolve to real, callable
functions, that `python -m things_mcp` and the console-script call path both
work and print the version, and (best-effort) that a built wheel's
entry_points.txt matches what we expect and doesn't leak `src/`-prefixed
paths.
"""

import importlib
import os
import subprocess
import sys
import tempfile
import zipfile

import pytest

tomllib = pytest.importorskip("tomllib")  # stdlib on 3.11+; skip cleanly on older Pythons
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

EXPECTED_SCRIPT_NAMES = {"mcp-server-things", "things-mcp"}


def _load_project_scripts() -> dict:
    with open(PYPROJECT_PATH, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["scripts"]


def test_project_scripts_section_has_expected_names():
    """[project.scripts] must define exactly mcp-server-things and things-mcp."""
    scripts = _load_project_scripts()
    assert set(scripts.keys()) == EXPECTED_SCRIPT_NAMES

    for name, target in scripts.items():
        assert ":" in target, f"{name} target {target!r} is not 'module:function'"
        module, _, func = target.partition(":")
        assert module.startswith("things_mcp"), (
            f"{name} target module {module!r} does not start with 'things_mcp' "
            "(should not be prefixed with 'src.')"
        )
        assert not module.startswith("src."), (
            f"{name} target module {module!r} leaks a 'src.' prefix"
        )
        assert func, f"{name} target {target!r} has no function name"


def test_project_scripts_targets_are_importable_and_callable():
    """Each [project.scripts] target must import and be callable."""
    scripts = _load_project_scripts()
    for name, target in scripts.items():
        module_name, _, func_name = target.partition(":")
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name, None)
        assert func is not None, f"{name}: {module_name} has no attribute {func_name!r}"
        assert callable(func), f"{name}: {target} is not callable"


def test_module_invocation_prints_version():
    """`python -m things_mcp --version` should exit 0 and print the version."""
    from things_mcp import __version__

    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(
        [sys.executable, "-m", "things_mcp", "--version"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert __version__ in combined_output, (
        f"version {__version__!r} not found in output:\n{combined_output}"
    )


def test_console_script_function_path_prints_version():
    """Invoking things_mcp.main:main directly (as the console script shim
    does) with argv simulating the console script should exit 0 and print
    the version."""
    from things_mcp import __version__

    env = {**os.environ, "PYTHONPATH": "src"}
    code = (
        "from things_mcp.main import main\n"
        "import sys\n"
        "sys.argv = ['mcp-server-things', '--version']\n"
        "rc = main()\n"
        "sys.exit(rc if isinstance(rc, int) else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert __version__ in combined_output, (
        f"version {__version__!r} not found in output:\n{combined_output}"
    )


def test_wheel_build_entry_points_and_no_src_prefix():
    """Best-effort: build a wheel and inspect its entry_points.txt.

    Skips gracefully if the build environment (network/backend availability)
    doesn't support building here, rather than failing the suite.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", tmpdir, "."],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=110,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            pytest.skip(f"wheel build could not run in this environment: {e}")

        if result.returncode != 0:
            pytest.skip(
                "wheel build failed in this environment (likely missing network/"
                f"build backend access): rc={result.returncode}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )

        wheels = list(Path(tmpdir).glob("*.whl"))
        if not wheels:
            pytest.skip("wheel build reported success but produced no .whl file")

        wheel_path = wheels[0]
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()

            # No top-level src/ entries should leak into the wheel.
            src_entries = [n for n in names if n.startswith("src/")]
            assert not src_entries, f"wheel contains leaked src/ entries: {src_entries}"

            entry_points_names = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
            assert entry_points_names, f"no entry_points.txt found in wheel: {names}"

            entry_points_text = zf.read(entry_points_names[0]).decode("utf-8")

        assert "mcp-server-things = things_mcp.main:main" in entry_points_text, (
            f"entry_points.txt missing mcp-server-things mapping:\n{entry_points_text}"
        )
        assert "things-mcp = things_mcp.main:main" in entry_points_text, (
            f"entry_points.txt missing things-mcp mapping:\n{entry_points_text}"
        )
