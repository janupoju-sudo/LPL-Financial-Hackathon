"""Card transactions API (C11).

POST /transactions/import   raw CSV body (Content-Type: text/csv)            (owner, ops, lpl_bookkeeper)

CSV: a header row with a date column (Date | Transaction Date | Posted Date), a description column
(Description | Merchant | Payee) and an amount column (Amount | Debit). Optional: Transaction ID, Card.
Dates YYYY-MM-DD or MM/DD/YYYY. Positive amounts are charges; zero/negative rows (payments, refunds)
are skipped.

Per charge: category from vendor memory (vendor name or alias inside the description), else merchant
keywords, else 6900 Other. Posts journal j-card-<txnId> (Dr expense / Cr 2100), idempotent, so
re-importing the same file books nothing twice. Matches a processed receipt document with the same
amount dated within 5 days and links it both ways.

Response: {imported, alreadyImported, skipped, categorized, matchedReceipts, transactions[]}
"""
import base64
import csv
import hashlib
import io
import re
from datetime import date, datetime

from shared import coa, ledger, repo
from shared.auth import get_caller, require_role
from shared.ddb import get_item
from shared.http import HttpError, router

MAX_ROWS = 500
RECEIPT_WINDOW_DAYS = 5

DATE_COLUMNS = ("date", "transaction date", "posted date", "post date")
DESCRIPTION_COLUMNS = ("description", "merchant", "payee", "name")
AMOUNT_COLUMNS = ("amount", "debit")
ID_COLUMNS = ("transaction id", "transactionid", "id", "reference")

# Merchant keyword -> expense account. Checked in order; first hit wins.
KEYWORDS = [
    # Marketing first so "Google Ads" / "LinkedIn Ads" don't fall into Technology.
    (("linkedin", "facebook", "meta ads", "google ads", "mailchimp", "vistaprint", "brightline",
      "marketing"), "6500"),
    (("zoom", "microsoft", "google", "adobe", "aws", "dropbox", "slack", "docusign", "salesforce",
      "redtail", "orion", "riskalyze", "emoney", "software"), "6300"),
    (("delta", "united", "american air", "southwest", "jetblue", "airline", "air", "marriott", "hilton",
      "hyatt", "hotel", "cafe", "restaurant", "uber", "lyft", "taxi", "amtrak", "hertz", "avis", "parking"), "6700"),
    (("finra", "sec", "nasaa", "cfp board", "compliance", "smarsh"), "6600"),
    (("lpl",), "6400"),
    (("wework", "regus", "rent"), "6200"),
]


def _raw_body(event) -> str:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8-sig")
    return raw.lstrip("﻿")


def _column(headers: dict, names) -> str:
    for name in names:
        if name in headers:
            return headers[name]
    return None


def _parse_date(value: str, row_no: int) -> str:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise HttpError(400, f"Row {row_no}: unrecognized date {text!r} (use YYYY-MM-DD or MM/DD/YYYY)")


def _parse_amount(value: str, row_no: int) -> float:
    text = (value or "").strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return round(float(text), 2)
    except ValueError:
        raise HttpError(400, f"Row {row_no}: amount {value!r} is not a number")


def parse_csv(text: str) -> list:
    if not text.strip():
        raise HttpError(400, "CSV body is empty")
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower(): h for h in (reader.fieldnames or [])}
    date_col = _column(headers, DATE_COLUMNS)
    desc_col = _column(headers, DESCRIPTION_COLUMNS)
    amount_col = _column(headers, AMOUNT_COLUMNS)
    if not (date_col and desc_col and amount_col):
        raise HttpError(400, "CSV needs Date, Description and Amount columns")
    id_col = _column(headers, ID_COLUMNS)

    rows, seen = [], {}
    for row_no, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        if len(rows) >= MAX_ROWS:
            raise HttpError(400, f"CSV has more than {MAX_ROWS} transactions; split the file")
        entry = {
            "date": _parse_date(row.get(date_col), row_no),
            "description": " ".join((row.get(desc_col) or "").split()),
            "amount": _parse_amount(row.get(amount_col), row_no),
        }
        ref = (row.get(id_col) or "").strip() if id_col else ""
        if not ref:
            # Deterministic id so re-importing the same statement is a no-op; identical rows stay distinct.
            key = f"{entry['date']}|{entry['description'].lower()}|{entry['amount']:.2f}"
            seen[key] = seen.get(key, 0) + 1
            ref = hashlib.sha1(f"{key}|{seen[key]}".encode()).hexdigest()[:12]
        entry["txnId"] = "".join(c for c in ref if c.isalnum() or c in "-_")[:40]
        rows.append(entry)
    return rows


def categorize(description: str, vendors: list):
    """Returns (glAccount, categorizedBy, vendorId)."""
    text = repo.normalize_name(description)
    padded = f" {text} "
    for v in vendors:
        names = [v.get("normalizedName")] + list(v.get("aliases") or [])
        if any(n and f" {n} " in padded for n in names):
            gl = v.get("defaultGlAccount")
            if coa.is_expense(gl):
                return gl, "vendor", v.get("vendorId")
    lowered = description.lower()
    for words, account in KEYWORDS:
        if any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in words):
            return account, "keyword", None
    return coa.DEFAULT_EXPENSE, None, None


def _receipt_candidates(practice_id) -> list:
    out = []
    for doc in repo.list_documents(practice_id, doc_type="receipt"):
        extracted = doc.get("extracted") or {}
        if doc.get("cardTxnId") or extracted.get("amount") is None:
            continue
        out.append(doc)
    return out


def _match_receipt(txn: dict, receipts: list):
    best, best_gap = None, None
    for doc in receipts:
        extracted = doc["extracted"]
        if abs(float(extracted["amount"]) - txn["amount"]) >= 0.005:
            continue
        receipt_date = extracted.get("invoiceDate") or extracted.get("date")
        if not receipt_date:
            continue
        gap = abs((date.fromisoformat(receipt_date) - date.fromisoformat(txn["date"])).days)
        if gap <= RECEIPT_WINDOW_DAYS and (best_gap is None or gap < best_gap):
            best, best_gap = doc, gap
    return best


def import_transactions(event):
    caller = get_caller(event)
    require_role(caller, "owner", "ops", "lpl_bookkeeper")
    p = caller.practice_id
    rows = parse_csv(_raw_body(event))

    vendors = repo.list_vendors(p)
    receipts = _receipt_candidates(p)
    result = {"imported": 0, "alreadyImported": 0, "skipped": 0, "categorized": 0,
              "matchedReceipts": 0, "transactions": []}

    for txn in rows:
        if txn["amount"] <= 0:
            result["skipped"] += 1
            continue
        journal_id = f"j-card-{txn['txnId']}"
        if get_item(p, ledger.line_sk({"date": txn["date"], "journalId": journal_id, "lineNo": 1})):
            result["alreadyImported"] += 1
            continue

        gl, how, vendor_id = categorize(txn["description"], vendors)
        receipt = _match_receipt(txn, receipts)
        receipt_id = receipt["documentId"] if receipt else None
        ledger.post_journal(p, journal_id, txn["date"], ledger.card_spend_lines(txn["amount"], gl),
                            memo=f"Card: {txn['description']}", source_doc_id=receipt_id,
                            source_type="card", source_id=txn["txnId"])
        if receipt:
            receipts.remove(receipt)
            repo.update_document(p, receipt_id, cardTxnId=txn["txnId"])
            result["matchedReceipts"] += 1

        result["imported"] += 1
        result["categorized"] += 1 if how else 0
        result["transactions"].append({
            **txn, "glAccount": gl, "glAccountName": coa.name(gl), "categorizedBy": how,
            "vendorId": vendor_id, "receiptDocumentId": receipt_id, "journalId": journal_id,
        })
    return 200, result


handler = router({
    "POST /transactions/import": import_transactions,
})
