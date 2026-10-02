"""Create a Bill from extracted document data. Called by the ingest pipeline (role B).

Input (from the IngestDocument state machine or a direct Lambda invoke):
{
  "practiceId": "p1",                    # optional, defaults to DEFAULT_PRACTICE_ID
  "documentId": "doc_...",               # required
  "vendorId": "ven_...",                 # from vendor matching; or pass vendorName to auto-create
  "vendorName": "Orion Software LLC",
  "amount": 1850.00,                     # required for auto-processing
  "currency": "USD",
  "invoiceNumber": "INV-2041", "invoiceDate": "2026-09-28", "dueDate": "2026-10-28",
  "glAccount": "6300",                   # optional 6xxx code; falls back to vendor default
  "lineItems": [{"description": "...", "amount": 1850.00}],
  "confidence": 0.93,                    # < REVIEW_CONFIDENCE_THRESHOLD -> pending_review
  "requiresReceipt": false
}
Output: {"billId": "...", "status": "processing" | "pending_review", "isDuplicate": bool}
"""
from shared import coa, config, repo, workflow
from shared.ddb import money, new_id, now_iso, from_ddb


def handler(event, context=None):
    practice_id = event.get("practiceId") or config.DEFAULT_PRACTICE_ID
    document_id = event["documentId"]
    doc = repo.get_document(practice_id, document_id) or {}

    vendor = repo.get_vendor(practice_id, event.get("vendorId"))
    if not vendor and event.get("vendorName"):
        vendor = repo.find_or_create_vendor(practice_id, event["vendorName"])

    amount = None
    if event.get("amount") not in (None, ""):
        amount = money(event["amount"])

    gl = str(event.get("glAccount") or (vendor or {}).get("defaultGlAccount") or coa.DEFAULT_EXPENSE)
    if not coa.is_expense(gl):
        gl = coa.DEFAULT_EXPENSE

    confidence = float(event.get("confidence", 1.0))
    invoice_number = event.get("invoiceNumber")
    vendor_id = vendor["vendorId"] if vendor else None
    is_dup = repo.is_duplicate_invoice(practice_id, vendor_id, invoice_number)

    can_auto = bool(vendor and amount and amount > 0 and confidence >= config.REVIEW_CONFIDENCE_THRESHOLD)
    bill_id = new_id("bill")
    bill = {
        "billId": bill_id,
        "documentId": document_id,
        "vendorId": vendor_id,
        "vendorName": vendor["name"] if vendor else event.get("vendorName"),
        "amount": amount,
        "currency": event.get("currency", "USD"),
        "invoiceNumber": invoice_number,
        "invoiceDate": event.get("invoiceDate"),
        "dueDate": event.get("dueDate"),
        "glAccount": gl,
        "glAccountName": coa.name(gl),
        "lineItems": event.get("lineItems") or [],
        "confidence": confidence,
        "requiresReceipt": bool(event.get("requiresReceipt", False)),
        "received": bool(event.get("received", False)),
        "isDuplicate": is_dup,
        "status": "processing" if can_auto else "pending_review",
        "createdBy": doc.get("uploadedBy", "system"),
        "createdAt": now_iso(),
        "audit": [repo.audit_event("Ledgerline AI", "extracted",
                                   f"Extracted with {round(confidence * 100)}% confidence")],
    }
    repo.put_bill(practice_id, bill)
    if vendor_id:
        repo.increment_vendor_bill_count(practice_id, vendor_id)
    if doc:
        repo.update_document(practice_id, document_id, billId=bill_id, vendorId=vendor_id,
                             vendorName=bill["vendorName"], amount=amount)

    if can_auto:
        workflow.start_approval(practice_id, bill_id)
    return from_ddb({"billId": bill_id, "status": bill["status"], "isDuplicate": is_dup})
