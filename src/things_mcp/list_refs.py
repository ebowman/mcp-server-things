"""Locale-independent references to Things' built-in lists.

Things resolves ``list "<name>"`` using the UI language (German: "Irgendwann",
"Heute", ...), so hard-coded English names fail on non-English installs.
The internal ``TM…ListSource`` ids are the same in every locale.
"""

BUILTIN_LIST_IDS = {
    "inbox": "TMInboxListSource",
    "today": "TMTodayListSource",
    "anytime": "TMNextListSource",
    "upcoming": "TMCalendarListSource",
    "someday": "TMSomedayListSource",
    "logbook": "TMLogbookListSource",
    "trash": "TMTrashListSource",
}


def list_ref(name: str) -> str:
    """Return the AppleScript reference for a built-in list.

    Args:
        name: Logical list name (case-insensitive): inbox, today, anytime,
            upcoming, someday, logbook or trash.

    Returns:
        AppleScript fragment such as ``list id "TMSomedayListSource"``.

    Raises:
        ValueError: If ``name`` is not a built-in list.
    """
    key = name.strip().lower()
    try:
        return f'list id "{BUILTIN_LIST_IDS[key]}"'
    except KeyError:
        raise ValueError(f"Unknown built-in list: {name!r}") from None
