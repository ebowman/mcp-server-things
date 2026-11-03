"""Guard the URL-scheme id-lookup poll budget (hq-nye)."""
from things_mcp.scheduling.todo_operations import TodoOperations


def test_url_scheme_lookup_deadline_budget():
    # hq-nye: 3s was too short under load (CREATE_UNCONFIRMED false-failures);
    # guard against the budget regressing.
    assert TodoOperations._URL_SCHEME_LOOKUP_DEADLINE_SECS == 10.0
