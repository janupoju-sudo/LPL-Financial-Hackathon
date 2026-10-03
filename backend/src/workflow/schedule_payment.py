"""ApproveBill: schedule a MOCK payment and post Dr 2000 Accounts payable / Cr 1000 Operating cash.

No real money moves - money transmission is out of scope for the hackathon.
"""
import uuid

from botocore.exceptions import ClientError

from shared import ledger, repo
from shared.ddb import today_iso


def _result(bill):
    payment = bill.get("payment") or {}
    return {
        "status": bill["status"],
        "scheduledFor": payment.get("scheduledFor"),
        "confirmation": payment.get("confirmation"),
    }


def handler(event, context=None):
    practice_id, bill_id = event["practiceId"], event["billId"]
    bill = repo.get_bill(practice_id, bill_id)
    if bill.get("status") == "scheduled":
        return _result(bill)
    if bill.get("status") != "approved":
        if bill.get("status") == "scheduling":
            pass
        elif bill.get("status") in {"voiding", "voided", "withdrawn"}:
            return _result(bill)
        else:
            raise ValueError(f"Bill cannot be scheduled from status {bill.get('status')}")
    else:
        try:
            repo.update_bill(
                practice_id, bill_id,
                set_fields={"status": "scheduling"},
                condition="#s0 = :approved",
                extra_values={":approved": "approved"},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            bill = repo.get_bill(practice_id, bill_id)
            if bill.get("status") in {"voiding", "voided", "withdrawn"}:
                return _result(bill)
            if bill.get("status") != "scheduling":
                raise ValueError(f"Bill cannot be scheduled from status {bill.get('status')}") from exc

    bill = repo.get_bill(practice_id, bill_id)
    today = today_iso()
    payment = bill.get("payment") or {}
    pay_date = payment.get("scheduledFor") or (
        bill.get("dueDate") if (bill.get("dueDate") or "") > today else today
    )
    journal_id = f"j-{bill_id}-payment"
    ledger.post_journal(
        practice_id, journal_id, pay_date, ledger.bill_payment_lines(bill["amount"]),
        memo=f"Mock ACH to {bill.get('vendorName', 'vendor')}",
        source_doc_id=bill.get("documentId"), source_type="bill_payment", source_id=bill_id,
    )
    confirmation = payment.get("confirmation") or f"MOCK-{uuid.uuid4().hex[:8].upper()}"
    try:
        repo.update_bill(
            practice_id, bill_id,
            set_fields={"status": "scheduled", "paymentJournalId": journal_id,
                        "payment": {"method": "ACH (mock)", "scheduledFor": pay_date,
                                    "confirmation": confirmation,
                                    "bankLast4": (repo.get_vendor(practice_id, bill.get("vendorId")) or {}).get("bankLast4")}},
            audit=repo.audit_event("Payments", "scheduled", f"Mock ACH {confirmation} on {pay_date}"),
            condition="#s0 = :scheduling",
            extra_values={":scheduling": "scheduling"},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        bill = repo.get_bill(practice_id, bill_id)
        if bill.get("status") in {"scheduled", "voiding", "voided", "withdrawn"}:
            return _result(bill)
        raise
    return {"status": "scheduled", "scheduledFor": pay_date, "confirmation": confirmation}
