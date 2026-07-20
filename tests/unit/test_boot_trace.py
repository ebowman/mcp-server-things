"""
Unit tests for the boot_trace diagnostic marker helper.

Tests that boot_marker() writes a well-formed, timestamped line to stderr
and never raises even if stderr is unwritable, since these markers are
used to diagnose cold-start hangs where zero other stderr is produced.
"""

import io
from datetime import datetime

import pytest

from things_mcp.boot_trace import boot_marker


class TestBootMarker:
    """Test boot_marker() behavior."""

    def test_writes_line_with_phase_and_elapsed(self, monkeypatch):
        """boot_marker writes a line containing the marker prefix, phase, and elapsed field."""
        fake_stderr = io.StringIO()
        monkeypatch.setattr("sys.stderr", fake_stderr)

        boot_marker("my-test-phase")

        output = fake_stderr.getvalue()
        assert "things-mcp boot:" in output
        assert "my-test-phase" in output
        assert "+" in output and "s " in output
        assert output.endswith("\n")

    def test_flushes_stderr(self, monkeypatch):
        """boot_marker flushes stderr after writing."""
        flushed = {"called": False}

        class TrackingStream(io.StringIO):
            def flush(self):
                flushed["called"] = True
                return super().flush()

        fake_stderr = TrackingStream()
        monkeypatch.setattr("sys.stderr", fake_stderr)

        boot_marker("flush-phase")

        assert flushed["called"] is True

    def test_swallows_oserror_from_write(self, monkeypatch):
        """boot_marker does not propagate OSError raised by sys.stderr.write."""

        class BrokenStream:
            def write(self, _text):
                raise OSError("broken pipe")

            def flush(self):
                pass

        monkeypatch.setattr("sys.stderr", BrokenStream())

        boot_marker("broken-phase")  # must not raise

    def test_swallows_valueerror_from_write(self, monkeypatch):
        """boot_marker does not propagate ValueError raised by sys.stderr.write (e.g. closed file)."""

        class ClosedStream:
            def write(self, _text):
                raise ValueError("I/O operation on closed file")

            def flush(self):
                pass

        monkeypatch.setattr("sys.stderr", ClosedStream())

        boot_marker("closed-phase")  # must not raise

    def test_line_contains_parseable_iso_timestamp(self, monkeypatch):
        """The timestamp embedded in the marker line is a valid ISO-8601 datetime."""
        fake_stderr = io.StringIO()
        monkeypatch.setattr("sys.stderr", fake_stderr)

        boot_marker("timestamp-phase")

        output = fake_stderr.getvalue()
        # Expected format: "things-mcp boot: <timestamp> +<elapsed>s <phase>\n"
        prefix = "things-mcp boot: "
        assert output.startswith(prefix)
        rest = output[len(prefix):]
        timestamp_str = rest.split(" +", 1)[0]
        # Should parse without raising.
        datetime.fromisoformat(timestamp_str)
