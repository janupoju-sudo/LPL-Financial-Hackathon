"""ApproveBill: schedule a MOCK payment and post Dr 2000 Accounts payable / Cr 1000 Operating cash.

No real money moves - money transmission is out of scope for the hackathon.
"""
import uuid

from shared import ledger, repo
from shared.ddb import today_iso


def handler(event, context=None):
    practice_id, bill_id = event["practiceId"], event["billId"]
    bill = repo.get_bill(practice_id, bill_id)
    today = today_iso()
    pay_date = bill.get("dueDate") if (bill.get("dueDate") or "") > today else today
    journal_id = f"j-{bill_id}-payment"
    ledger.post_journal(
        practice_id, journal_id, pay_date, ledger.bill_payment_lines(bill["amount"]),
        memo=f"Mock ACH to {bill.get('vendorName', 'vendor')}",
        source_doc_id=bill.get("documentId"), source_type="bill_payment", source_id=bill_id,
    )
    confirmation = bill.get("payment", {}).get("confirmation") or f"MOCK-{uuid.uuid4().hex[:8].upper()}"
    repo.update_bill(
        practice_id, bill_id,
        set_fields={"status": "scheduled", "paymentJournalId": journal_id,
                    "payment": {"method": "ACH (mock)", "scheduledFor": pay_date,
                                "confirmation": confirmation,
                                "bankLast4": (repo.get_vendor(practice_id, bill.get("vendorId")) or {}).get("bankLast4")}},
        audit=repo.audit_event("Payments", "scheduled", f"Mock ACH {confirmation} on {pay_date}"),
    )
    return {"status": "scheduled", "scheduledFor": pay_date, "confirmation": confirmation}
