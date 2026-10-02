"""Parse period strings used by the API: "2026-09", "2026-Q3" or "2026"."""

import re
from datetime import date, timedelta


def parse(period: str) -> tuple[date, date]:
    """Return (start, end) dates, both inclusive."""
    if m := re.fullmatch(r"(\d{4})-(\d{2})", period):
        y, mo = int(m[1]), int(m[2])
        if not 1 <= mo <= 12:
            raise ValueError(f"Bad month in period {period!r}")
        return date(y, mo, 1), _month_end(y, mo)
    if m := re.fullmatch(r"(\d{4})-Q([1-4])", period):
        y, q = int(m[1]), int(m[2])
        return date(y, 3 * q - 2, 1), _month_end(y, 3 * q)
    if m := re.fullmatch(r"(\d{4})", period):
        y = int(m[1])
        return date(y, 1, 1), date(y, 12, 31)
    raise ValueError(f"Period must look like 2026-09, 2026-Q3 or 2026, got {period!r}")


def previous(period: str) -> str:
    """The period of the same length just before this one."""
    start, _ = parse(period)
    if "Q" in period:
        q = (start.month - 1) // 3 + 1
        return f"{start.year - 1}-Q4" if q == 1 else f"{start.year}-Q{q - 1}"
    if len(period) == 7:
        prev = start - timedelta(days=1)
        return f"{prev.year}-{prev.month:02d}"
    return str(start.year - 1)


def _month_end(y: int, mo: int) -> date:
    nxt = date(y + (mo == 12), mo % 12 + 1, 1)
    return nxt - timedelta(days=1)
