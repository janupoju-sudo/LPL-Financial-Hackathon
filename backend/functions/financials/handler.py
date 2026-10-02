"""Lambda entry points for GET /financials and GET /revenue/reconciliation."""

import json
from datetime import date

from . import api, periods, reconciliation

PRACTICE_ID = "p1"


def _reply(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def _period(event, default: str) -> str:
    p = (event.get("queryStringParameters") or {}).get("period") or default
    periods.parse(p)  # raises ValueError on a bad period
    return p


def _current_quarter() -> str:
    t = date.today()
    return f"{t.year}-Q{(t.month - 1) // 3 + 1}"


def financials_handler(event, _context):
    from shared import ddb  # C1
    try:
        period = _period(event, _current_quarter())
    except ValueError as e:
        return _reply(400, {"error": str(e)})
    _, end = periods.parse(period)
    entries = ddb.get_ledger_entries(PRACTICE_ID, date(2000, 1, 1), end)
    return _reply(200, api.build_financials(entries, period, ddb.get_practice(PRACTICE_ID) or {}))


def reconciliation_handler(event, _context):
    from shared import ddb  # C1
    t = date.today()
    try:
        period = _period(event, f"{t.year}-{t.month:02d}")
    except ValueError as e:
        return _reply(400, {"error": str(e)})
    schedule = (ddb.get_practice(PRACTICE_ID) or {}).get("feeSchedule", [])
    lines = ddb.get_revenue_lines(PRACTICE_ID, period)
    return _reply(200, reconciliation.response(schedule, lines, period))
