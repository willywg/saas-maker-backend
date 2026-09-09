"""Time helpers.

The database columns are naive ``DateTime`` (no timezone), so we keep naive
UTC datetimes everywhere. ``datetime.utcnow()`` is deprecated since Python 3.12;
this helper produces the same value without the warning.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.now(UTC).replace(tzinfo=None)
