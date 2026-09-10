"""Unit-suite-only guard: force ``THINGSDB`` at a nonexistent path.

The unit suite must never touch a real Things 3 SQLite database - every
call into things.py should be mocked. If a test accidentally exercises a
real, unmocked ``things.py`` call, it should fail loudly with
``sqlite3.OperationalError: unable to open database file`` rather than
silently passing (or failing in a confusing, machine-dependent way) against
whatever real database happens to exist on the developer's machine.

things.py's ``things.database.Database`` reads the ``THINGSDB`` environment
variable at *construction* time (each call into things.py, e.g.
``things.areas()``, ``things.todos()``, constructs a fresh ``Database``
instance internally) - it is not read once at import time. That means a
session-scoped autouse fixture that sets the variable before any test body
runs is sufficient; there is no module-level ``things.database.Database()``
construction anywhere in ``src/things_mcp`` that would run before this
fixture takes effect (verified via `grep -rn "things.database.Database("
src/things_mcp`, and `src/things_mcp/things_import.py`'s ``LazyThingsProxy``
only caches the imported *module* object, not any database connection).

This fixture unconditionally overrides ``THINGSDB`` to a nonexistent path
under ``tmp_path_factory`` for the whole session, regardless of any
pre-existing value (unset, pointing at a real database, or already
nonexistent), restoring whatever value was previously set (or unsetting it
entirely) once the session ends.

The only opt-out is ``THINGS_MCP_UNIT_TESTS_ALLOW_REAL_DB=1``: when set, the
fixture leaves ``THINGSDB`` untouched entirely and emits a single pytest
warning ("unit tests may read a real Things database") so a developer who
intentionally wants to run the unit suite against a real database can do so,
while still being warned loudly that this is happening.

This fixture only applies to ``tests/unit`` (conftest.py placement scopes
it to this directory) - ``tests/live``, ``tests/regression``, and
``tests/integration`` are unaffected and continue to use whatever real (or
locally configured) Things database the environment provides.
"""

import os
import warnings

import pytest


@pytest.fixture(scope="session", autouse=True)
def _force_nonexistent_things_db(tmp_path_factory):
    """Point THINGSDB at a nonexistent path for the whole unit test session.

    Unconditionally overrides any pre-existing THINGSDB value (restoring it
    afterward), unless THINGS_MCP_UNIT_TESTS_ALLOW_REAL_DB=1 is set, in which
    case THINGSDB is left untouched and a warning is emitted instead.
    """
    if os.environ.get("THINGS_MCP_UNIT_TESTS_ALLOW_REAL_DB") == "1":
        warnings.warn(
            "THINGS_MCP_UNIT_TESTS_ALLOW_REAL_DB=1 is set: unit tests may "
            "read a real Things database.",
            stacklevel=1,
        )
        yield
        return

    fake_db_dir = tmp_path_factory.mktemp("things_mcp_nonexistent_db")
    fake_db_path = str(fake_db_dir / "Things.sqlite")

    previous = os.environ.get("THINGSDB")
    os.environ["THINGSDB"] = fake_db_path
    yield
    if previous is None:
        os.environ.pop("THINGSDB", None)
    else:
        os.environ["THINGSDB"] = previous
