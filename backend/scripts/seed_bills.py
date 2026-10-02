"""Seed approved bill history so the Bills page, vendor memory and audit trail have data.

    python scripts/seed_bills.py --table ledgerline-dev

Writes BILL# records for June-August 2026 that already went through the normal flow
(extracted -> rules -> approved -> posted -> scheduled), with a dated audit trail, and
bumps each vendor's billCount. That makes Orion Software a "recognized vendor" before the
live demo uploads its September invoices.

These bills do NOT post to the ledger: seed_ddb.py already booked those months' expenses
as aggregate journals, so posting again would double-count. Each bill says so in
`ledgerNote`. Bill ids are fixed, so re-running skips bills that exist.
"""
import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

PARTNER = "raj@harborpoint.example"
OWNER = "maya@harborpoint.example"
OPS = "dev@harborpoint.example"

# (vendor name, gl, invoice number, invoice date, amount, documentId or None)
HISTORY = [
    ("Orion Software LLC", "6300", "ORN-2026-06", "2026-06-02", 450.00, None),
    ("Orion Software LLC", "6300", "ORN-2026-07", "2026-07-02", 450.00, None),
    ("Orion Software LLC", "6300", "ORN-2026-07A", "2026-07-15", 1850.00, None),
    ("Orion Software LLC", "6300", "ORN-2026-08", "2026-08-03", 450.00, None),
    ("Seaport Office Partners", "6200", "SOP-0626", "2026-06-01", 9800.00, None),
    ("Seaport Office Partners", "6200", "SOP-0726", "2026-07-01", 12200.00, None),
    ("Seaport Office Partners", "6200", "SOP-0826", "2026-08-01", 12200.00, None),
    ("LPL Financial", "6400", "LPL-PF-2606", "2026-06-28", 21500.00, None),
    ("LPL Financial", "6400", "LPL-PF-2607", "2026-07-28", 21500.00, None),
    ("LPL Financial", "6400", "LPL-PF-2608", "2026-08-28", 21500.00, None),
    ("Clearwater Compliance Advisors (FICTIONAL)", "6600", "CCA-2607", "2026-07-05", 2550.00,
     "doc_compliance_invoice_2026_07"),
    ("Clearwater Compliance Advisors (FICTIONAL)", "6600", "CCA-2608", "2026-08-05", 2550.00,
     "doc_compliance_invoice_2026_08"),
]

APPROVAL_LIMIT = 1000  # matches the default "Bills over $1,000 need partner approval" rule


def _at(day: str, hour: int, minute: int = 0) -> str:
    return f"{day}T{hour:02d}:{minute:02d}:00+00:00"


def _plus_days(day: str, days: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def bill_id(invoice_number: str) -> str:
    return "bill_seed_" + invoice_number.lower().replace("-", "_")


def build_bill(vendor: dict, gl: str, invoice: str, invoice_date: str, amount: float, doc_id):
    from shared import coa

    needs_partner = amount > APPROVAL_LIMIT
    approve_day = _plus_days(invoice_date, 1)
    pay_day = _plus_days(invoice_date, 10)
    hits = ([{"ruleId": "rule_large_bill", "name": "Bills over $1,000 need partner approval",
              "action": "require_approval", "approverRole": "partner",
              "reason": "Amount is over $1,000"}] if needs_partner else [])
    approver = PARTNER if needs_partner else "Rules engine"
    audit = [
        {"at": _at(invoice_date, 14), "actor": "Ledgerline AI", "action": "extracted",
         "detail": "Extracted with 97% confidence"},
        {"at": _at(invoice_date, 14, 1), "actor": "Rules engine",
         "action": "routed" if needs_partner else "auto_approved",
         "detail": "Amount is over $1,000" if needs_partner else "No rules hit"},
    ]
    if needs_partner:
        audit.append({"at": _at(approve_day, 10, 12), "actor": PARTNER, "action": "approved",
                      "detail": "Approved"})
    audit += [
        {"at": _at(approve_day, 10, 13), "actor": "Ledger", "action": "posted",
         "detail": f"Dr {gl} / Cr 2000 Accounts payable"},
        {"at": _at(approve_day, 10, 14), "actor": "Payments", "action": "scheduled",
         "detail": f"Mock ACH MOCK-{invoice.replace('-', '')[-8:]} on {pay_day}"},
    ]
    return {
        "billId": bill_id(invoice),
        "documentId": doc_id,
        "vendorId": vendor["vendorId"],
        "vendorName": vendor["name"],
        "amount": Decimal(str(amount)),
        "currency": "USD",
        "invoiceNumber": invoice,
        "invoiceDate": invoice_date,
        "dueDate": _plus_days(invoice_date, 15),
        "glAccount": gl,
        "glAccountName": coa.name(gl),
        "lineItems": [],
        "confidence": Decimal("0.97"),
        "requiresReceipt": False,
        "received": True,
        "isDuplicate": False,
        "status": "scheduled",
        "decision": "needs_approval" if needs_partner else "auto_approve",
        "ruleHits": hits,
        "requiredApprovers": ["partner"] if needs_partner else [],
        "approvedBy": approver,
        "payment": {"method": "ACH (mock)", "scheduledFor": pay_day,
                    "confirmation": f"MOCK-{invoice.replace('-', '')[-8:]}",
                    "bankLast4": vendor.get("bankLast4")},
        "createdBy": OPS,
        "createdAt": _at(invoice_date, 14),
        "updatedAt": _at(approve_day, 10, 14),
        "audit": audit,
        "seeded": True,
        "ledgerNote": "History bill: its expense is already in seed_ddb.py's monthly journal.",
    }


def seed(practice_id: str) -> tuple[int, int]:
    from shared import repo

    created = skipped = 0
    for name, gl, invoice, invoice_date, amount, doc_id in HISTORY:
        if repo.get_bill(practice_id, bill_id(invoice)):
            skipped += 1
            continue
        vendor = repo.find_vendor_by_name(practice_id, name) or repo.create_vendor(
            practice_id, name, default_gl_account=gl, hasW9=True, hasVoidCheck=True)
        bill = build_bill(vendor, gl, invoice, invoice_date, amount, doc_id)
        repo.put_bill(practice_id, bill)
        repo.increment_vendor_bill_count(practice_id, vendor["vendorId"])
        if doc_id and repo.get_document(practice_id, doc_id):
            repo.update_document(practice_id, doc_id, billId=bill["billId"],
                                 vendorId=vendor["vendorId"])
        created += 1
    return created, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--practice", default="p1")
    args = ap.parse_args()
    os.environ["TABLE_NAME"] = args.table
    created, skipped = seed(args.practice)
    print(f"Bill history: {created} created, {skipped} already there.")


if __name__ == "__main__":
    main()
