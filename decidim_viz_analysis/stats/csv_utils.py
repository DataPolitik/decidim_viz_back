"""Helpers shared by the commands that import Decidim open-data CSV exports."""
from datetime import datetime, timezone

_DATETIME_FORMATS = ('%Y-%m-%d %H:%M:%S %Z', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S')


def parse_datetime(value):
    """Parse a Decidim export timestamp ("2022-01-31 10:00:00 UTC") into an aware datetime.

    Returns None for empty values. Timestamps without an offset are taken as UTC.
    """
    value = (value or '').strip()
    if not value:
        return None
    for fmt in _DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ValueError('Unrecognised date format: {!r}'.format(value))


def split_names(value):
    """Split a comma-separated list of user names, dropping blanks.

    An empty cell gives an empty list (``''.split(',')`` would give ``['']``).
    """
    return [name.strip() for name in (value or '').split(',') if name.strip()]


def blank_to_none(value):
    value = (value or '').strip()
    return value or None
