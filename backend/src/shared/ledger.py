"""Double-entry ledger - format agreed with Financials (role D).

ONE DynamoDB item per journal LINE:
  PK = PRACTICE#<practiceId>
  SK = LEDGER#<yyyy-mm>#<journalId>#<lineNo>      (query a month with begins_with LEDGER#2026-09)
  {
    "journalId": "j-bill_ab12-accrual",   # same on every line of one journal
    "date": "2026-09-30",
    "account": "6300",                    # shared/coa.py
    "debit": 124000, "credit": 0,         # INTEGER CENTS
    "sourceDocId": "doc_123" | null,
    "memo": "Brightline IT Services INV-2291",
    "lineNo": 1, "sourceType": "bill", "sourceId": "bill_ab12", "createdAt": "..."
  }
A journal is written atomically (TransactWriteItems) and must balance. Re-posting the same
journalId (e.g. a Step Functions retry) is a no-op.
"""
from decimal import ROUND_HALF_UP, Decimal

from botocore.exceptions import ClientError

from . import coa
from .ddb import now_iso, pk, table, to_ddb


class LedgerError(ValueError):
    pass


def to_cents(dollars) -> int:
    """Dollars (int/float/str/Decimal) -> integer cents."""
    return int((Decimal(str(dollars)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_journal(journal_id, entry_date, lines, memo, source_doc_id=None, source_type=None, source_id=None):
    """lines: [{"account": "6300", "debit": <cents>} | {"account": "2000", "credit": <cents>}]"""
    if not journal_id:
        raise LedgerError("journalId is required")
    if len(lines) < 2:
        raise LedgerError("A journal needs at least two lines")
    out, total_dr, total_cr = [], 0, 0
    for n, line in enumerate(lines, start=1):
        account = str(line["account"])
        if not coa.is_valid(account):
            raise LedgerError(f"Unknown account {account}")
        debit, credit = line.get("debit", 0), line.get("credit", 0)
        if not isinstance(debit, int) or not isinstance(credit, int) or isinstance(debit, bool):
            raise LedgerError("Amounts must be integer cents")
        if debit < 0 or credit < 0 or (debit > 0) == (credit > 0):
            raise LedgerError("Each line needs exactly one positive debit or credit")
        total_dr += debit
        total_cr += credit
        out.append({
            "journalId": journal_id, "lineNo": n, "date": entry_date, "account": account,
            "debit": debit, "credit": credit, "sourceDocId": source_doc_id, "memo": memo,
            "sourceType": source_type, "sourceId": source_id, "createdAt": now_iso(),
        })
    if total_dr != total_cr:
        raise LedgerError(f"Journal {journal_id} is unbalanced: debits {total_dr} != credits {total_cr}")
    return out


def line_sk(line) -> str:
    return f"LEDGER#{line['date'][:7]}#{line['journalId']}#{line['lineNo']:03d}"


def post_journal(practice_id, journal_id, entry_date, lines, memo,
                 source_doc_id=None, source_type=None, source_id=None):
    built = build_journal(journal_id, entry_date, lines, memo, source_doc_id, source_type, source_id)
    client = table().meta.client
    items = []
    for line in built:
        item = {k: v for k, v in line.items()}
        item.update(PK=pk(practice_id), SK=line_sk(line))
        items.append({"Put": {"TableName": table().name, "Item": to_ddb_keep_nulls(item),
                              "ConditionExpression": "attribute_not_exists(SK)"}})
    try:
        client.transact_write_items(TransactItems=items)
    except ClientError as err:
        reasons = err.response.get("CancellationReasons") or []
        if err.response["Error"]["Code"] == "TransactionCanceledException" and any(
                r.get("Code") == "ConditionalCheckFailed" for r in reasons):
            return built  # already posted
        raise
    return built


def to_ddb_keep_nulls(item):
    """to_ddb drops None; D expects sourceDocId to be present (null) on every line."""
    clean = to_ddb(item)
    for k, v in item.items():
        if v is None:
            clean[k] = None
    return clean


# ---- journal templates (amounts in dollars in, cents out) ----

def bill_accrual_lines(amount, expense_account):
    """Bill approved: Dr <expense> / Cr 2000 Accounts payable."""
    c = to_cents(amount)
    return [{"account": str(expense_account), "debit": c}, {"account": coa.ACCOUNTS_PAYABLE, "credit": c}]


def bill_payment_lines(amount):
    """Mock payment: Dr 2000 Accounts payable / Cr 1000 Operating cash."""
    c = to_cents(amount)
    return [{"account": coa.ACCOUNTS_PAYABLE, "debit": c}, {"account": coa.CASH, "credit": c}]


def payout_lines(amounts_by_type: dict):
    """Payout statement: Dr 1000 (total) / Cr 4100, 4200, 4300 (one line per revenue type).

    amounts_by_type: {"advisory": 41000.00, "commission": 3200.50, "trail": 1875.25}
    """
    credits = [{"account": coa.REVENUE_ACCOUNTS[t], "credit": to_cents(a)}
               for t, a in amounts_by_type.items() if a and to_cents(a) > 0]
    if not credits:
        raise LedgerError("Payout has no revenue lines")
    return [{"account": coa.CASH, "debit": sum(c["credit"] for c in credits)}] + credits


def card_spend_lines(amount, expense_account):
    """Card spend (P1): Dr <expense> / Cr 2100 Credit card payable."""
    c = to_cents(amount)
    return [{"account": str(expense_account), "debit": c}, {"account": coa.CREDIT_CARD_PAYABLE, "credit": c}]


def account_balances(lines) -> dict:
    """{account: debit - credit} in cents."""
    out = {}
    for line in lines:
        out[line["account"]] = out.get(line["account"], 0) + int(line["debit"]) - int(line["credit"])
    return out
