"""Pure table filtering helpers, kept independent from the GUI toolkit."""

from __future__ import annotations

from collections.abc import Sequence


def matches_filter(values: Sequence[object], query: str, column_index: int | None = None) -> bool:
    """Return whether a row matches a case-insensitive text filter."""
    needle = query.strip().casefold()
    if not needle:
        return True
    fields = [str(value).casefold() for value in values]
    if column_index is not None:
        return 0 <= column_index < len(fields) and needle in fields[column_index]
    return any(needle in field for field in fields)


def matches_filters(values: Sequence[object], filters: dict[int, str]) -> bool:
    """Return whether a row matches all active column filters."""
    return all(matches_filter(values, query, column_index) for column_index, query in filters.items())
