"""Resume bills that are on hold for a vendor once its documents arrive.

Triggered by the EventBridge `VendorUpdated` event (emitted by repo.record_vendor_docs),
or invoked directly with {"practiceId": "p1", "vendorId": "ven_..."}.
Each held bill's workflow loops back to EvaluateRules.
"""
from botocore.exceptions import ClientError

from shared import config, repo, workflow


def handler(event, context=None):
    detail = event.get("detail", event)
    practice_id = detail.get("practiceId") or config.DEFAULT_PRACTICE_ID
    vendor_id = detail["vendorId"]
    resumed = []
    for bill in repo.list_bills_for_vendor(practice_id, vendor_id, ["pending_docs"]):
        token = bill.get("taskToken")
        if not token:
            continue
        try:
            repo.update_bill(
                practice_id, bill["billId"], set_fields={"status": "processing"}, remove=["taskToken"],
                audit=repo.audit_event("Workflow", "resumed", "Vendor documents updated - re-checking rules"),
                condition="taskToken = :tok", extra_values={":tok": token},
            )
            workflow.resume(token, {"decision": "reevaluate", "by": "system"})
            resumed.append(bill["billId"])
        except ClientError as err:
            print(f"[resume] could not resume {bill['billId']}: {err}")
    return {"resumed": resumed}
