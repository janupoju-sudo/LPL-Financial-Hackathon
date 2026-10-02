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
    repo.update_bill(
        practice_id, bill_id,
        set_fields={"status": "rejected", "rejectionReason": reason, "rejectedAt": repo.now_iso()},
        remove=["taskToken"],
        audit=repo.audit_event("Workflow", "rejected", reason),
    )
    events.put_event("BillRejected", {"practiceId": practice_id, "billId": bill_id, "reason": reason})
    return {"status": "rejected", "reason": reason}
