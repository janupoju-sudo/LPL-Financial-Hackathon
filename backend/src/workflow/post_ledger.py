"""ApproveBill: post the accrual journal (Dr <bill.glAccount> / Cr 2000). Idempotent."""
from shared import ledger, repo
from shared.ddb import today_iso


def handler(event, context=None):
    practice_id, bill_id = event["practiceId"], event["billId"]
    bill = repo.get_bill(practice_id, bill_id)
    journal_id = f"j-{bill_id}-accrual"
    ledger.post_journal(
        practice_id, journal_id, bill.get("invoiceDate") or today_iso(),
        ledger.bill_accrual_lines(bill["amount"], bill["glAccount"]),
        memo=f"{bill.get('vendorName', 'Vendor')} {bill.get('invoiceNumber') or ''}".strip(),
        source_doc_id=bill.get("documentId"), source_type="bill", source_id=bill_id,
    )
    repo.update_bill(
        practice_id, bill_id,
        set_fields={"status": "approved", "approvedAt": repo.now_iso(), "accrualJournalId": journal_id},
        remove=["taskToken"],
        audit=repo.audit_event("Ledger", "posted", f"Dr {bill['glAccount']} / Cr 2000 Accounts payable"),
    )
    return {"entryId": journal_id}
