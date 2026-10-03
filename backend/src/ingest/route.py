from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from .common import state_context


def _document_fields(event: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    upload = state_context(event)
    normalized = event["normalization"]["data"]["normalized"]
    return upload, normalized


def _bill_confidence(normalized: Mapping[str, Any]) -> float:
    return min(
        normalized.get("confidence", 0.0),
        normalized.get("vendorConfidence", 0.0),
    )


def prepare_bill(
    event: Mapping[str, Any], context: Any = None
) -> dict[str, Any]:
    from shared import coa

    upload, normalized = _document_fields(event)
    vendor = event.get("vendorMatch", {}).get("data", {}).get("vendor")
    extracted_gl = normalized.get("glAccount")
    vendor_gl = (vendor or {}).get("defaultGlAccount")
    if coa.is_expense(extracted_gl):
        gl_account = str(extracted_gl)
        gl_account_reason = "Suggested from invoice details during document extraction."
    elif coa.is_expense(vendor_gl):
        gl_account = str(vendor_gl)
        gl_account_reason = (
            f"Matched vendor memory: {vendor.get('name')} uses expense account {gl_account}."
        )
    else:
        gl_account = coa.DEFAULT_EXPENSE
        gl_account_reason = (
            f"No valid invoice account or vendor history was available; "
            f"used default expense account {gl_account}."
        )
    request: dict[str, Any] = {
        "practiceId": upload["practiceId"],
        "documentId": upload["documentId"],
        "vendorName": (vendor or {}).get("name") or normalized.get("vendorName"),
        "amount": normalized.get("amount"),
        "invoiceNumber": normalized.get("invoiceNumber"),
        "invoiceDate": normalized.get("invoiceDate"),
        "dueDate": normalized.get("dueDate"),
        "lineItems": normalized.get("lineItems", []),
        "confidence": _bill_confidence(normalized),
        "glAccount": gl_account,
        "glAccountReason": gl_account_reason,
    }
    vendor_id = (vendor or {}).get("vendorId")
    if vendor_id:
        request["vendorId"] = vendor_id
    return request


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    if "createdBill" in event:
        return complete_bill_handler(event, context)

    from shared import ledger, repo

    upload, normalized = _document_fields(event)
    practice_id = upload["practiceId"]
    document_id = upload["documentId"]
    document_type = normalized["type"]
    confidence = normalized.get("confidence", 0.0)
    vendor_match = event.get("vendorMatch", {}).get("data", {}).get("vendor")
    extracted = dict(normalized)

    if document_type in {"w9", "void_check"}:
        if confidence < 0.8 or not normalized.get("vendorName"):
            reason = "Vendor identity confidence too low or vendor name missing"
            repo.update_document(
                practice_id,
                document_id,
                type=document_type,
                status="needs_review",
                confidence=confidence,
                extracted={**extracted, "reviewReason": reason},
            )
            return {"status": "needs_review", "reason": reason}
        vendor = vendor_match
        if not vendor or not vendor.get("vendorId"):
            vendor = repo.find_or_create_vendor(practice_id, normalized["vendorName"])
        kwargs: dict[str, Any] = {"document_id": document_id}
        if document_type == "w9":
            kwargs["has_w9"] = True
        else:
            kwargs["has_void_check"] = True
            if normalized.get("bankLast4"):
                kwargs["bank_last4"] = normalized["bankLast4"]
        repo.record_vendor_docs(practice_id, vendor["vendorId"], **kwargs)
        repo.update_document(
            practice_id,
            document_id,
            type=document_type,
            status="processed",
            confidence=confidence,
            extracted=extracted,
            vendorId=vendor["vendorId"],
            vendorName=vendor["name"],
        )
        return {"status": "processed", "vendorId": vendor["vendorId"]}

    if document_type == "payout_statement":
        period = normalized.get("period")
        lines = normalized.get("revenueLines", [])
        if confidence < 0.8 or not period or not lines:
            reason = "Payout period, extracted lines, or confidence require review"
            repo.update_document(
                practice_id,
                document_id,
                type=document_type,
                status="needs_review",
                confidence=confidence,
                extracted={**extracted, "reviewReason": reason},
            )
            return {"status": "needs_review", "reason": reason}

        for line in lines:
            if line.get("docId") != document_id:
                raise ValueError("Revenue line docId does not match the uploaded document")
            if line.get("source") not in {"advisory", "commission", "trail", "other"}:
                raise ValueError("Revenue line has an unsupported source")
            if isinstance(line.get("actual"), bool) or not isinstance(
                line.get("actual"), int
            ):
                raise ValueError("Revenue line actual must be integer cents")
        repo.put_revenue_lines(practice_id, period, document_id, lines)

        if any(line["actual"] < 0 for line in lines) or not any(
            line["actual"] > 0 for line in lines
        ):
            reason = "Negative or zero-only payout lines are saved but need ledger review"
            repo.update_document(
                practice_id,
                document_id,
                type=document_type,
                status="needs_review",
                confidence=confidence,
                extracted={**extracted, "reviewReason": reason},
            )
            return {"status": "needs_review", "reason": reason}

        dollars_by_type: dict[str, Decimal] = {}
        for line in lines:
            source = line["source"]
            dollars_by_type[source] = dollars_by_type.get(source, Decimal(0)) + (
                Decimal(line["actual"]) / 100
            )
        year, month = (int(part) for part in period.split("-"))
        entry_date = date(year, month, monthrange(year, month)[1]).isoformat()
        ledger.post_journal(
            practice_id,
            f"j-payout-{document_id}",
            entry_date,
            ledger.payout_lines(dollars_by_type),
            memo=f"LPL payout statement {period}",
            source_doc_id=document_id,
            source_type="payout",
            source_id=document_id,
        )
        repo.update_document(
            practice_id,
            document_id,
            type=document_type,
            status="processed",
            confidence=confidence,
            extracted=extracted,
        )
        return {"status": "processed", "period": period, "lineCount": len(lines)}

    reason = normalized.get("reviewReason", "Unknown document type")
    repo.update_document(
        practice_id,
        document_id,
        type="unknown",
        status="needs_review",
        confidence=confidence,
        extracted={**extracted, "reviewReason": reason},
    )
    return {"status": "needs_review", "reason": reason}


def complete_bill_handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    from shared import config, repo

    upload, normalized = _document_fields(event)
    bill_response = event["createdBill"]["data"]
    bill = bill_response.get("bill", bill_response)
    effective_confidence = _bill_confidence(normalized)
    status = (
        "needs_review"
        if bill.get("status") == "pending_review"
        or effective_confidence < config.REVIEW_CONFIDENCE_THRESHOLD
        else "processed"
    )
    extracted = dict(normalized)
    if status == "needs_review" and not extracted.get("reviewReason"):
        if normalized.get("vendorConfidence", 0.0) < config.REVIEW_CONFIDENCE_THRESHOLD:
            extracted["reviewReason"] = "Vendor identity confidence requires confirmation"
        else:
            extracted["reviewReason"] = "Bill was created in pending review"
    repo.update_document(
        upload["practiceId"],
        upload["documentId"],
        type=normalized["type"],
        status=status,
        confidence=effective_confidence,
        extracted=extracted,
        billId=bill.get("billId"),
    )
    return {"status": status, "billId": bill.get("billId")}
