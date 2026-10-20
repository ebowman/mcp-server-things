"""Guard the x86_64 macOS cryptography pin in pyproject.toml (hq-usx)."""

from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
EXPECTED = (
    "cryptography<49; sys_platform == 'darwin' and platform_machine == 'x86_64'"
)


def test_cryptography_x86_64_darwin_pin_present() -> None:
    """cryptography 49+ has no x86_64 macOS wheels; the pin must stay marked."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert EXPECTED in deps
    # No unmarked cryptography constraint that would affect arm64/Linux.
    unmarked = [
        d for d in deps if d.startswith("cryptography") and ";" not in d
    ]
    assert unmarked == []
