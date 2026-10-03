"""ApproveBill terminal failure state. Input {"input": <full state>}."""
from shared import events, repo


def _reason(state: dict) -> str:
    if state.get("error"):
        return "Approval window expired"
    approval = state.get("approval") or state.get("hold") or {}
    if approval.get("decision") == "reject":
        comment = f": {approval['comment']}" if approval.get("comment") else ""
        return f"Rejected by {approval.get('approver', 'approver')}{comment}"
    evaluation = state.get("evaluation") or {}
    if evaluation.get("decision") == "blocked":
        return "; ".join(h["reason"] for h in evaluation.get("hits", []) if h["action"] == "block")
    return "Rejected"


def handler(event, context=None):
    state = event.get("input", event)
    practice_id, bill_id = state["practiceId"], state["billId"]
    reason = _reason(state)
    decision = state.get("approval") or state.get("hold") or {}
    withdrawn = decision.get("decision") == "withdraw"
    status = "withdrawn" if withdrawn else "rejected"
    bill = repo.get_bill(practice_id, bill_id) if withdrawn else None
    if withdrawn:
        actor = decision.get("approver", "Uploader")
        reason = f"Withdrawn by {actor}" + (f": {decision['comment']}" if decision.get("comment") else "")
    repo.update_bill(
        practice_id, bill_id,
        set_fields={
            "status": status,
            ("withdrawalReason" if withdrawn else "rejectionReason"): reason,
            ("withdrawnAt" if withdrawn else "rejectedAt"): repo.now_iso(),
        },
        remove=["taskToken"],
        audit=repo.audit_event(
            decision.get("approver", "Workflow") if withdrawn else "Workflow",
            "withdrawn" if withdrawn else "rejected",
            reason,
        ),
    )
    if withdrawn:
        if bill and bill.get("documentId"):
            repo.update_document(
                practice_id,
                bill["documentId"],
                status="withdrawn",
                audit=repo.audit_event(decision.get("approver", "Uploader"), "withdrawn", reason),
            )
        events.put_event("BillWithdrawn", {"practiceId": practice_id, "billId": bill_id, "reason": reason})
    else:
        events.put_event("BillRejected", {"practiceId": practice_id, "billId": bill_id, "reason": reason})
    return {"status": status, "reason": reason}
