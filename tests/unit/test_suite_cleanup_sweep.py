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


class GetFake:
    """Fake things.get: records map id -> record or None; raises for ids in `boom`."""

    def __init__(self, records, boom=()):
        self.records = records
        self.boom = set(boom)

    def get(self, uuid, **kw):
        if "trashed" in kw and uuid.startswith("area"):
            raise TypeError("areas do not accept trashed=")
        if uuid in self.boom:
            raise RuntimeError("db unreadable")
        return self.records.get(uuid)


def _run_delete_all(fake, todos=(), projects=(), areas=(), **kw):
    calls = []

    def fake_batch(kind, ids, budget):
        calls.append((kind, list(ids)))
        return len(list(ids)), []

    with patch.dict(sys.modules, {"things": fake}), \
            patch.object(sc, "delete_batch", side_effect=fake_batch), \
            patch.object(sc, "log") as lg:
        res = sc.delete_all(todos, projects, areas, sc.Budget(), **kw)
    return res, dict(calls), [c.args[0] for c in lg.call_args_list]


def test_already_trashed_project_skipped_and_logged():
    fake = GetFake({"p1": {"trashed": True}, "p2": {"trashed": False}})
    res, calls, logs = _run_delete_all(fake, projects=["p1", "p2"])
    assert calls["project"] == ["p2"]
    assert res["projects"] == (1, [])
    assert any("skipped 1 already-trashed/missing project" in m for m in logs)
    assert not any("NOT DELETED" in m for m in logs)


def test_missing_id_skipped():
    _res, calls, _logs = _run_delete_all(GetFake({}), todos=["gone"])
    assert calls["todo"] == []


def test_active_id_attempted():
    _res, calls, logs = _run_delete_all(GetFake({"t": {"uuid": "t"}}), todos=["t"])
    assert calls["todo"] == ["t"]
    assert not any("skipped" in m for m in logs)


def test_area_never_passes_trashed_kwarg():
    fake = GetFake({"area1": {"uuid": "area1"}})
    _res, calls, _logs = _run_delete_all(fake, areas=["area1", "area2"])
    assert calls["area"] == ["area1"]  # area2 missing -> skipped; no TypeError


def test_read_exception_keeps_id_active():
    fake = GetFake({}, boom=["t"])
    _res, calls, logs = _run_delete_all(fake, todos=["t"])
    assert calls["todo"] == ["t"]
    assert sum("read failed" in m for m in logs) == 1


def test_prefilter_false_attempts_everything():
    fake = GetFake({"p1": {"trashed": True}})
    _res, calls, _logs = _run_delete_all(fake, projects=["p1"], prefilter=False)
    assert calls["project"] == ["p1"]
