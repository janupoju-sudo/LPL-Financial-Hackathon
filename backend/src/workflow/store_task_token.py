"""ApproveBill wait states (lambda:invoke.waitForTaskToken).

Input {practiceId, billId, taskToken, waitingFor: "approval"|"documents", requiredApprovers}
Stores the token on the bill; the API (or resume_held_bills) later calls SendTaskSuccess with
{"decision": "approve" | "reject" | "reevaluate", ...}.
"""
from shared import events, repo


def handler(event, context=None):
    practice_id, bill_id = event["practiceId"], event["billId"]
    waiting_for = event.get("waitingFor", "approval")
    status = "pending_approval" if waiting_for == "approval" else "pending_docs"
    approvers = event.get("requiredApprovers") or (["owner"] if waiting_for == "approval" else [])
    detail = (f"Waiting for {', '.join(approvers)} approval" if waiting_for == "approval"
              else "On hold until requirements are met")
    repo.update_bill(
        practice_id, bill_id,
        set_fields={"status": status, "taskToken": event["taskToken"], "requiredApprovers": approvers,
                    "waitingSince": repo.now_iso()},
        audit=repo.audit_event("Workflow", status, detail),
    )
    events.put_event("BillAwaitingAction", {
        "practiceId": practice_id, "billId": bill_id, "status": status, "requiredApprovers": approvers,
    })
    return {"status": status}
