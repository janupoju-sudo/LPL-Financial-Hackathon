"""Bills & approvals API.

GET  /bills?status=a,b        list (newest first)
GET  /bills/{id}              detail incl. audit trail
POST /bills/{id}/decision     {decision: approve|reject, comment}  -> resumes the Step Functions task
POST /bills/{id}/confirm      {amount?, vendorName?, vendorId?, dueDate?, glAccount?, invoiceNumber?, invoiceDate?}
                              human review for low-confidence extractions; starts the workflow
POST /bills/{id}/receive      marks goods/services received; re-evaluates a held bill
"""
from botocore.exceptions import ClientError

from shared import coa, config, repo, workflow
from shared.auth import get_caller
from shared.ddb import money, public
from shared.http import HttpError, parse_body, path_param, query_param, router


def _load(caller, bill_id):
    bill = repo.get_bill(caller.practice_id, bill_id)
    if not bill:
        raise HttpError(404, "Bill not found")
    return bill


def list_bills(event):
    caller = get_caller(event)
    raw = query_param(event, "status")
    statuses = [s.strip() for s in raw.split(",")] if raw else None
    return 200, [repo.bill_summary(b) for b in repo.list_bills(caller.practice_id, statuses)]


def get_bill(event):
    caller = get_caller(event)
    return 200, public(_load(caller, path_param(event, "id")))


def _claim_task(caller, bill, new_status, audit):
    """Atomically take the task token so two approvers can't both act on one bill."""
    token = bill.get("taskToken")
    if not token:
        raise HttpError(409, f"Bill is not waiting for a decision (status: {bill.get('status')})")
    try:
        repo.update_bill(
            caller.practice_id, bill["billId"],
            set_fields={"status": new_status}, remove=["taskToken"], audit=audit,
            condition="taskToken = :tok", extra_values={":tok": token},
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HttpError(409, "Someone else already acted on this bill")
        raise
    return token


def _resume_or_restore(caller, bill, token, output):
    try:
        workflow.resume(token, output)
    except ClientError as err:
        code = err.response["Error"]["Code"]
        repo.update_bill(caller.practice_id, bill["billId"],
                         set_fields={"status": bill["status"], "taskToken": token})
        if code in ("TaskTimedOut", "InvalidToken", "TaskDoesNotExist"):
            raise HttpError(409, f"Workflow task is no longer active ({code})")
        raise


def decide(event):
    caller = get_caller(event)
    bill = _load(caller, path_param(event, "id"))
    body = parse_body(event)
    decision = body.get("decision")
    comment = (body.get("comment") or "").strip()[:500]
    if decision not in ("approve", "reject"):
        raise HttpError(400, "decision must be 'approve' or 'reject'")

    status = bill.get("status")
    if status == "pending_approval":
        allowed = set(bill.get("requiredApprovers") or ["owner"]) | {"owner"}
    elif status == "pending_docs":
        # Override a hold: only the owner may approve; owner or partner may reject.
        allowed = {"owner"} if decision == "approve" else {"owner", "partner"}
    else:
        raise HttpError(409, f"Bill is not waiting for a decision (status: {status})")
    if not caller.has_any(*allowed):
        raise HttpError(403, f"Only {', '.join(sorted(allowed))} can {decision} this bill")
    if decision == "approve" and bill.get("createdBy") == caller.sub and not config.ALLOW_SELF_APPROVAL:
        raise HttpError(403, "Segregation of duties: you can't approve a bill you submitted")

    audit = repo.audit_event(caller.label, f"{decision}d" if decision == "approve" else "rejected", comment)
    token = _claim_task(caller, bill, "processing", audit)
    _resume_or_restore(caller, bill, token, {
        "decision": decision, "approver": caller.label, "approverSub": caller.sub, "comment": comment,
    })
    return 200, {"billId": bill["billId"], "status": "processing", "decision": decision}


def confirm(event):
    caller = get_caller(event)
    bill = _load(caller, path_param(event, "id"))
    if bill.get("status") != "pending_review":
        raise HttpError(409, f"Only bills in pending_review can be confirmed (status: {bill.get('status')})")
    body = parse_body(event)
    fields = {}

    vendor = None
    if body.get("vendorId"):
        vendor = repo.get_vendor(caller.practice_id, body["vendorId"])
        if not vendor:
            raise HttpError(400, "Unknown vendorId")
    elif body.get("vendorName"):
        vendor = repo.find_or_create_vendor(caller.practice_id, body["vendorName"])
    elif bill.get("vendorId"):
        vendor = repo.get_vendor(caller.practice_id, bill["vendorId"])
    if not vendor:
        raise HttpError(400, "A vendor is required (vendorId or vendorName)")
    if vendor["vendorId"] != bill.get("vendorId"):
        fields.update(vendorId=vendor["vendorId"], vendorName=vendor["name"])
        repo.increment_vendor_bill_count(caller.practice_id, vendor["vendorId"])

    if "amount" in body:
        try:
            fields["amount"] = money(body["amount"])
        except Exception:
            raise HttpError(400, "amount must be a number")
    amount = fields.get("amount", bill.get("amount"))
    if amount is None or money(amount) <= 0:
        raise HttpError(400, "amount must be greater than 0")

    if "glAccount" in body:
        if not coa.is_expense(body["glAccount"]):
            raise HttpError(400, "glAccount must be an expense (6xxx) account")
        fields.update(glAccount=str(body["glAccount"]), glAccountName=coa.name(body["glAccount"]))
    for key in ("dueDate", "invoiceDate", "invoiceNumber"):
        if body.get(key):
            fields[key] = str(body[key])

    invoice = fields.get("invoiceNumber", bill.get("invoiceNumber"))
    fields["isDuplicate"] = repo.is_duplicate_invoice(caller.practice_id, vendor["vendorId"], invoice, bill["billId"])
    fields.update(status="processing", reviewedBy=caller.label)
    repo.update_bill(caller.practice_id, bill["billId"], set_fields=fields,
                     audit=repo.audit_event(caller.label, "confirmed", "Reviewed extracted fields"))
    workflow.start_approval(caller.practice_id, bill["billId"])
    return 200, {"billId": bill["billId"], "status": "processing"}


def receive(event):
    caller = get_caller(event)
    bill = _load(caller, path_param(event, "id"))
    repo.update_bill(caller.practice_id, bill["billId"], set_fields={"received": True},
                     audit=repo.audit_event(caller.label, "marked_received"))
    if bill.get("status") == "pending_docs" and bill.get("taskToken"):
        token = _claim_task(caller, bill, "processing", None)
        _resume_or_restore(caller, bill, token, {"decision": "reevaluate", "by": caller.label})
        return 200, {"billId": bill["billId"], "status": "processing", "received": True}
    return 200, {"billId": bill["billId"], "status": bill.get("status"), "received": True}


handler = router({
    "GET /bills": list_bills,
    "GET /bills/{id}": get_bill,
    "POST /bills/{id}/decision": decide,
    "POST /bills/{id}/confirm": confirm,
    "POST /bills/{id}/receive": receive,
})
