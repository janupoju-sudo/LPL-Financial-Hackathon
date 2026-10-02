"""GET /financials and GET /revenue/reconciliation (D2-D4, D7)."""

from datetime import date

from shared import ddb
from shared.auth import get_caller
from shared.http import HttpError, query_param, router

from . import api, periods, reconciliation


def _period(event, default: str) -> str:
    period = query_param(event, "period") or default
    try:
        periods.parse(period)
    except ValueError as e:
        raise HttpError(400, str(e))
    return period


def financials(event):
    caller = get_caller(event)
    t = date.today()
    period = _period(event, f"{t.year}-Q{(t.month - 1) // 3 + 1}")
    _, end = periods.parse(period)
    # Full history: the balance sheet and trailing-12-month valuation need it.
    entries = ddb.get_ledger_entries(caller.practice_id, "0000-01-01", end.isoformat())
    return 200, api.build_financials(entries, period, ddb.get_practice(caller.practice_id) or {})


def revenue_reconciliation(event):
    caller = get_caller(event)
    t = date.today()
    period = _period(event, f"{t.year}-{t.month:02d}")
    schedule = (ddb.get_practice(caller.practice_id) or {}).get("feeSchedule", [])
    lines = ddb.get_revenue_lines(caller.practice_id, period)
    return 200, reconciliation.response(schedule, lines, period)


handler = router({
    "GET /financials": financials,
    "GET /revenue/reconciliation": revenue_reconciliation,
})
