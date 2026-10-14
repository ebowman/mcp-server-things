"""hq-8vx: safety guards and selection for tests/regression/suite_cleanup.py."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regression import suite_cleanup as sc  # noqa: E402

P = "hq-gbl-reg "


class FakeThings:
    """Hierarchy: prefixed area A (project 'plain' with todo t_in_plain,
    direct todo t_direct); non-prefixed area B (project pb, todo tb);
    prefixed project PP (todo t_pp, heading h -> t_h); loose prefixed todo."""

    def __init__(self, extra_todos=0):
        self.extra = extra_todos

    def areas(self):
        return [{"uuid": "A", "title": P + "area"}, {"uuid": "B", "title": "Work"}]

    def projects(self, area=None, status=None):
        allp = [
            {"uuid": "plain", "title": "plain", "area": "A"},
            {"uuid": "pb", "title": "pb", "area": "B"},
            {"uuid": "PP", "title": P + "proj", "area": None},
        ]
        return [p for p in allp if area is None or p["area"] == area]

    def todos(self, area=None, status=None):
        if area == "A":
            return [{"uuid": "t_direct", "title": "d"}]
        if area == "B":
            return [{"uuid": "tb", "title": "b"}]
        return [{"uuid": "loose", "title": P + "loose"}, {"uuid": "tb", "title": "b"}] + [
            {"uuid": f"x{i}", "title": P + str(i)} for i in range(self.extra)
        ]

    def tasks(self, project=None, heading=None, type=None, status=None):
        if project == "plain":
            return [{"uuid": "t_in_plain", "type": "to-do"}]
        if project == "pb":
            return [{"uuid": "tb_in_pb", "type": "to-do"}]
        if project == "PP":
            return [{"uuid": "t_pp", "type": "to-do"}, {"uuid": "h", "type": "heading"}]
        if heading == "h":
            return [{"uuid": "t_h", "type": "to-do"}]
        return []


def test_selection_collects_area_project_children_and_excludes_other_areas():
    with patch.dict(sys.modules, {"things": FakeThings()}):
        todos, projects, areas = sc.select_sweep_targets(P)
    assert set(todos) == {"loose", "t_direct", "t_in_plain", "t_pp", "t_h"}
    assert set(projects) == {"plain", "PP"}
    assert areas == ["A"]
    assert "tb" not in todos and "tb_in_pb" not in todos and "pb" not in projects


@pytest.mark.parametrize("bad", ["", None, "   ", "short", "  abc   "])
def test_bad_prefix_refused_no_osascript(bad):
    with patch("subprocess.run") as run, patch.dict(sys.modules, {"things": FakeThings()}):
        with pytest.raises(ValueError):
            sc.sweep_prefix(bad, "t", sc.Budget())
    run.assert_not_called()


def test_cap_exceeded_deletes_nothing_and_records_failure():
    sc.FAILURES.clear()
    with patch("subprocess.run") as run, patch.dict(
        sys.modules, {"things": FakeThings(extra_todos=600)}
    ):
        counts = sc.sweep_prefix(P, "t", sc.Budget())
    run.assert_not_called()
    assert counts == {"todos": 0, "projects": 0, "areas": 0}
    assert len(sc.FAILURES) == 1 and "ABORTED" in sc.FAILURES[0]
    sc.FAILURES.clear()
