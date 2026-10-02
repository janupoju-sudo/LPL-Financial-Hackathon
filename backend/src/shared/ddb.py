"""DynamoDB access helpers for the single-table design (see docs/PLAN.md section 4)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from . import config

_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(config.TABLE_NAME)
    return _table


def reset_clients():
    """Used by tests so each test gets a fresh (mocked) table handle."""
    global _table
    _table = None


def pk(practice_id: str) -> str:
    return f"PRACTICE#{practice_id}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


def to_ddb(value):
    """Recursively convert floats to Decimal so boto3 accepts them."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_ddb(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [to_ddb(v) for v in value]
    return value


def from_ddb(value):
    """Recursively convert Decimal to int/float for JSON responses."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_ddb(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [from_ddb(v) for v in value]
    return value


def money(value) -> Decimal:
    """Parse any numeric input into a 2-decimal-place Decimal."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def get_item(practice_id: str, sk: str):
    return table().get_item(Key={"PK": pk(practice_id), "SK": sk}).get("Item")


def put_item(practice_id: str, sk: str, item: dict, condition=None):
    full = to_ddb({**item, "PK": pk(practice_id), "SK": sk})
    kwargs = {"Item": full}
    if condition:
        kwargs["ConditionExpression"] = condition
    table().put_item(**kwargs)
    return full


def query_prefix(practice_id: str, prefix: str):
    """Return every item under the practice whose SK begins with prefix (handles paging)."""
    items, kwargs = [], {
        "KeyConditionExpression": Key("PK").eq(pk(practice_id)) & Key("SK").begins_with(prefix)
    }
    while True:
        resp = table().query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def update_item(practice_id, sk, set_fields=None, remove=None, append=None, condition=None, extra_values=None,
                extra_names=None):
    """Build and run an UpdateExpression.

    set_fields: {attr: value} to SET
    remove:     [attr, ...] to REMOVE
    append:     {attr: [items]} appended to a list attribute (created if missing)
    condition:  ConditionExpression using #names from the fields above or extra_names, :values in extra_values
    """
    set_fields, remove, append = set_fields or {}, remove or [], append or {}
    names, values, sets = {}, {}, []
    for i, (k, v) in enumerate(set_fields.items()):
        names[f"#s{i}"] = k
        values[f":s{i}"] = to_ddb(v)
        sets.append(f"#s{i} = :s{i}")
    for i, (k, v) in enumerate(append.items()):
        names[f"#a{i}"] = k
        values[f":a{i}"] = to_ddb(list(v))
        values[":empty"] = []
        sets.append(f"#a{i} = list_append(if_not_exists(#a{i}, :empty), :a{i})")
    expr = []
    if sets:
        expr.append("SET " + ", ".join(sets))
    if remove:
        rem = []
        for i, k in enumerate(remove):
            names[f"#r{i}"] = k
            rem.append(f"#r{i}")
        expr.append("REMOVE " + ", ".join(rem))
    if extra_values:
        values.update(to_ddb(extra_values))
    if extra_names:
        names.update(extra_names)
    kwargs = {
        "Key": {"PK": pk(practice_id), "SK": sk},
        "UpdateExpression": " ".join(expr),
        "ExpressionAttributeNames": names,
        "ReturnValues": "ALL_NEW",
    }
    if values:
        kwargs["ExpressionAttributeValues"] = values
    if condition:
        kwargs["ConditionExpression"] = condition
    return table().update_item(**kwargs)["Attributes"]


def public(item: dict, hide=("PK", "SK", "taskToken")) -> dict:
    """Strip internal keys and convert Decimals for API output."""
    if item is None:
        return None
    return from_ddb({k: v for k, v in item.items() if k not in hide})


# ---------- read helpers for Financials (role D) ----------

def _ledger_line(item: dict) -> dict:
    keys = ("journalId", "lineNo", "date", "account", "debit", "credit", "sourceDocId", "memo",
            "sourceType", "sourceId")
    out = {k: item.get(k) for k in keys}
    out["debit"], out["credit"] = int(item.get("debit", 0)), int(item.get("credit", 0))
    out["lineNo"] = int(item.get("lineNo", 0))
    return out


def get_ledger_entries(practice_id: str, start_date: str, end_date: str) -> list:
    """All ledger lines with start_date <= date <= end_date (ISO dates, inclusive).

    Amounts are integer cents. Sorted by date, journalId, lineNo.
    """
    items, kwargs = [], {
        "KeyConditionExpression": Key("PK").eq(pk(practice_id))
        & Key("SK").between(f"LEDGER#{start_date[:7]}", f"LEDGER#{end_date[:7]}#~"),
    }
    while True:
        resp = table().query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    lines = [_ledger_line(i) for i in items if start_date <= i.get("date", "") <= end_date]
    return sorted(lines, key=lambda l: (l["date"], l["journalId"] or "", l["lineNo"]))


def get_practice(practice_id: str):
    """PRACTICE#<id> / META item, Decimals converted (whole numbers -> int, rates -> float).

    Fields read by Financials (D): clientCount, top10Share, feeSchedule (list; amounts and aum
    in integer cents, annualRate as a fraction e.g. 0.01). META.aum is in dollars.
    """
    item = get_item(practice_id, "META")
    return public(item) if item else None


def _months_in(period: str) -> list:
    """'2026-09' -> ['2026-09'];  '2026-Q3' -> ['2026-07','2026-08','2026-09'];  '2026' -> 12 months."""
    period = period.strip().upper()
    if len(period) == 7 and period[4] == "-" and period[5] != "Q":
        return [period]
    if len(period) == 7 and period[5] == "Q" and period[6] in "1234":
        q = int(period[6])
        return [f"{period[:4]}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    if len(period) == 4 and period.isdigit():
        return [f"{period}-{m:02d}" for m in range(1, 13)]
    raise ValueError(f"Unrecognized period {period!r}; use YYYY-MM, YYYY-Qn or YYYY")


def get_revenue_lines(practice_id: str, period: str) -> list:
    """RevenueLine items (SK REV#<yyyy-mm>#<id>) for a month; also accepts YYYY-Qn or YYYY.

    Each line: {"id", "period", "source", "ref", "label", "actual" (int cents), "docId", ...}
    """
    lines = []
    for month in _months_in(period):
        lines.extend(public(i) for i in query_prefix(practice_id, f"REV#{month}#"))
    return sorted(lines, key=lambda l: (l.get("period", ""), l.get("id", "")))
