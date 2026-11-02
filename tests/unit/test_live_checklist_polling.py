"""Offline contracts for the live smoke checklist visibility assertion."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from live import test_smoke as smoke


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(now=0.0, sleeps=[])

    def sleep(seconds: float) -> None:
        state.sleeps.append(seconds)
        state.now += seconds

    monkeypatch.setattr(
        smoke,
        "time",
        SimpleNamespace(monotonic=lambda: state.now, sleep=sleep),
    )
    return state


def test_immediate_exact_content_does_not_sleep(
    monkeypatch: pytest.MonkeyPatch, clock: SimpleNamespace
) -> None:
    read = Mock(return_value=[{"title": "one"}, {"title": "two"}])
    monkeypatch.setattr(smoke.things, "checklist_items", read)

    smoke._wait_for_checklist_titles("owned-id", ["one", "two"])

    read.assert_called_once_with("owned-id")
    assert clock.sleeps == []


def test_waits_through_empty_and_partial_reads(
    monkeypatch: pytest.MonkeyPatch, clock: SimpleNamespace
) -> None:
    read = Mock(side_effect=[
        [],
        [{"title": "one"}],
        [{"title": "one"}, {"title": "two"}],
    ])
    monkeypatch.setattr(smoke.things, "checklist_items", read)

    smoke._wait_for_checklist_titles("owned-id", ["one", "two"])

    assert read.call_count == 3
    assert clock.sleeps == [0.25, 0.25]


@pytest.mark.parametrize("titles", [
    [],
    ["one"],
    ["two", "one"],
    ["one", "two", "two"],
])
def test_incorrect_content_fails_at_deadline(
    monkeypatch: pytest.MonkeyPatch, clock: SimpleNamespace, titles: list[str]
) -> None:
    read = Mock(return_value=[{"title": title} for title in titles])
    monkeypatch.setattr(smoke.things, "checklist_items", read)

    with pytest.raises(AssertionError, match="last observed"):
        smoke._wait_for_checklist_titles(
            "owned-id", ["one", "two"], timeout=0.6, interval=0.25
        )

    assert clock.now == pytest.approx(0.6)
    assert clock.sleeps == pytest.approx([0.25, 0.25, 0.1])
    assert read.call_count == 4


def test_reader_failure_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, clock: SimpleNamespace
) -> None:
    read = Mock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(smoke.things, "checklist_items", read)

    with pytest.raises(RuntimeError, match="database unavailable"):
        smoke._wait_for_checklist_titles("owned-id", ["one", "two"])

    read.assert_called_once_with("owned-id")
    assert clock.sleeps == []
