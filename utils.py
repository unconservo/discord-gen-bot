"""Small pure-function helpers shared across cogs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def format_time(days: float) -> str:
    """Render a float `days` value as a compact human string (e.g. "1d 4h")."""
    total_minutes = max(0, int(days * 24 * 60))

    d = total_minutes // (24 * 60)
    h = (total_minutes % (24 * 60)) // 60
    m = total_minutes % 60

    if d > 0:
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def parse_iso_utc(raw: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp and return a timezone-aware UTC datetime.

    Bug fix #6 — the previous implementation used naive `datetime.utcnow()`
    and blew up on TZ-aware timestamps. This helper normalises both cases.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def now_utc() -> datetime:
    """Timezone-aware UTC 'now'. Never use `datetime.utcnow()` in this bot."""
    return datetime.now(timezone.utc)


def effective_days(stored_days: float, updated_at_raw: Optional[str]) -> float:
    """Compute remaining days given the last stored value and update time.

    Clamps to zero (bug fix #6). Silently returns the stored value if the
    timestamp is missing or unparsable.
    """
    if updated_at_raw is None:
        return max(0.0, stored_days)

    last_update = parse_iso_utc(updated_at_raw)
    if last_update is None:
        return max(0.0, stored_days)

    elapsed_days = (now_utc() - last_update).total_seconds() / 86400.0
    elapsed_days = max(0.0, elapsed_days)  # clamp negatives (clock skew)
    return max(0.0, stored_days - elapsed_days)
