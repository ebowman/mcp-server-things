"""Built-in list references must be locale-independent (German Things etc.)."""

import re
from pathlib import Path

import pytest

from things_mcp.list_refs import list_ref

EXPECTED = {
    "inbox": "TMInboxListSource",
    "today": "TMTodayListSource",
    "anytime": "TMNextListSource",
    "upcoming": "TMCalendarListSource",
    "someday": "TMSomedayListSource",
    "logbook": "TMLogbookListSource",
    "trash": "TMTrashListSource",
}


@pytest.mark.parametrize("name,list_id", EXPECTED.items())
def test_mapping(name, list_id):
    assert list_ref(name) == f'list id "{list_id}"'
    assert list_ref(name.upper()) == list_ref(name)


def test_unknown_list_raises():
    with pytest.raises(ValueError):
        list_ref("bogus")


def test_no_hardcoded_english_list_names_in_source():
    """Guard: `list "Someday"` etc. fail on non-English Things installs."""
    src = Path(__file__).resolve().parents[2] / "src" / "things_mcp"
    pattern = re.compile(r'\blist "(?:inbox|today|anytime|upcoming|someday|logbook|trash)"', re.I)
    offenders = []
    for path in src.rglob("*.py"):
        if path.name == "reliable_scheduling.py":
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line) and not line.lstrip().startswith(("#", "*")) and "`" not in line:
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, offenders
