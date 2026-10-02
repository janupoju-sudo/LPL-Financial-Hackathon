import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .common import invoke_bedrock_json, state_context
from .payout_parser import RevenueLine, parse_payout_lines


def _confidence(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Extraction confidence must be a number")
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Extraction confidence must be a number") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("Extraction confidence must be between 0 and 1")
    return confidence


def _money(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip().replace(",", "").replace("$", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a dollar amount") from exc
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a finite dollar amount")
    return float(amount)


def _date_or_none(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _period(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("Payout statement period must be YYYY-MM")
    month = int(value[5:])
    if not 1 <= month <= 12:
        raise ValueError("Payout statement period has an invalid month")
    return value


def normalize_invoice(
    document_type: str, result: Mapping[str, Any]
) -> dict[str, Any]:
    if document_type not in {"invoice", "receipt"}:
        raise ValueError(f"Not an invoice or receipt: {document_type}")
    vendor_name = result.get("vendorName")
    if vendor_name is not None and not isinstance(vendor_name, str):
        raise ValueError("vendorName must be a string or null")
    line_items = result.get("lineItems") or []
    if not isinstance(line_items, list):
        raise ValueError("lineItems must be a list")
    normalized_items = []
    for item in line_items:
        if not isinstance(item, Mapping):
            raise ValueError("Each line item must be an object")
        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Each line item needs a description")
        amount = _money(item.get("amount"), "line item amount")
        if amount is None:
            raise ValueError("Each line item needs an amount")
        normalized_items.append({"description": description.strip(), "amount": amount})

    gl_account = result.get("glAccount")
    if gl_account not in (None, ""):
        if not isinstance(gl_account, str) or not re.fullmatch(r"6\d{3}", gl_account):
            raise ValueError("glAccount must be a 6xxx expense code")

    confidence = _confidence(result.get("confidence"))
    vendor_confidence = _confidence(result.get("vendorConfidence"))
    return {
        "type": document_type,
        "confidence": min(confidence, vendor_confidence),
        "vendorConfidence": vendor_confidence,
        "vendorName": vendor_name.strip() if vendor_name else None,
        "amount": _money(result.get("amount"), "amount"),
        "invoiceNumber": result.get("invoiceNumber") or None,
        "invoiceDate": _date_or_none(result.get("invoiceDate"), "invoiceDate"),
        "dueDate": _date_or_none(result.get("dueDate"), "dueDate"),
        "glAccount": gl_account or None,
        "lineItems": normalized_items,
    }


def _normalized_vendor_document(
    document_type: str, result: Mapping[str, Any]
) -> dict[str, Any]:
    vendor_name = result.get("vendorName")
    if vendor_name is not None and not isinstance(vendor_name, str):
        raise ValueError("vendorName must be a string or null")
    bank_last4 = result.get("bankLast4")
    if bank_last4 not in (None, ""):
        digits = re.sub(r"\D", "", str(bank_last4))
        if len(digits) < 4:
            raise ValueError("bankLast4 must contain at least four digits")
        bank_last4 = digits[-4:]
    else:
        bank_last4 = None
    return {
        "type": document_type,
        "confidence": _confidence(result.get("confidence")),
        "vendorName": vendor_name.strip() if vendor_name else None,
        "hasW9": document_type == "w9",
        "hasVoidCheck": document_type == "void_check",
        "bankLast4": bank_last4,
    }


def _textract_words(result: Mapping[str, Any]) -> str:
    return " ".join(
        block.get("Text", "")
        for block in result.get("Blocks", [])
        if block.get("BlockType") == "LINE" and isinstance(block.get("Text"), str)
    )


def _expense_context(result: Mapping[str, Any]) -> str:
    documents = []
    for document in result.get("ExpenseDocuments", []):
        summary = []
        for field in document.get("SummaryFields", []):
            summary.append(
                {
                    "type": field.get("Type", {}).get("Text"),
                    "value": field.get("ValueDetection", {}).get("Text"),
                }
            )
        items = []
        for group in document.get("LineItemGroups", []):
            for line in group.get("LineItems", []):
                items.append(
                    [
                        {
                            "type": item.get("Type", {}).get("Text"),
                            "value": item.get("ValueDetection", {}).get("Text"),
                        }
                        for item in line.get("LineItemExpenseFields", [])
                    ]
                )
        documents.append({"summaryFields": summary, "lineItems": items})
    return json.dumps(documents, separators=(",", ":"))


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    import boto3

    upload = state_context(event)
    classification = event["classification"]["data"]
    document_type = classification["documentType"]
    extraction_key = event["extraction"]["data"]["textractKey"]
    s3 = boto3.client("s3")
    raw = json.loads(
        s3.get_object(Bucket=upload["bucket"], Key=extraction_key)["Body"].read()
    )
    words = _textract_words(raw)

    try:
        if document_type in {"invoice", "receipt"}:
            schema = (
                '{"confidence": number, "vendorConfidence": number, '
                '"vendorName": string|null, "amount": number|null, '
                '"invoiceNumber": string|null, "invoiceDate": "YYYY-MM-DD"|null, '
                '"dueDate": "YYYY-MM-DD"|null, "glAccount": "6xxx"|null, '
                '"lineItems": [{"description": string, "amount": number}]}'
            )
            response = invoke_bedrock_json(
                f"Normalize these Textract invoice fields. Use only supplied evidence; "
                f"unknown fields are null. `confidence` is overall extraction confidence; "
                f"`vendorConfidence` is confidence that vendorName identifies the correct "
                f"vendor. Return JSON matching {schema}.\n"
                f"{_expense_context(raw)}"
            )
            normalized = normalize_invoice(document_type, response)
        elif document_type in {"w9", "void_check"}:
            schema = (
                '{"confidence": number, "vendorName": string|null, '
                '"bankLast4": string|null}'
            )
            response = invoke_bedrock_json(
                f"Extract vendor identity and, for a void check, the last four bank digits. "
                f"Return JSON matching {schema}; use only this OCR text:\n{words}"
            )
            normalized = _normalized_vendor_document(document_type, response)
        elif document_type == "payout_statement":
            lines: list[RevenueLine] = parse_payout_lines(raw, upload["documentId"])
            response = invoke_bedrock_json(
                "Find the statement period as YYYY-MM from this payout-statement OCR text. "
                "Return only JSON: {\"confidence\": number, \"period\": \"YYYY-MM\" or null}.\n"
                f"{words}"
            )
            normalized = {
                "type": document_type,
                "confidence": _confidence(response.get("confidence")),
                "period": _period(response.get("period")),
                "revenueLines": lines,
            }
        else:
            normalized = {
                "type": "unknown",
                "confidence": 0.0,
                "reviewReason": "Unsupported or unrecognized document type",
            }
    except ValueError as exc:
        normalized = {
            "type": document_type,
            "confidence": 0.0,
            "reviewReason": f"Extraction requires review: {exc}",
        }

    normalized["confidence"] = min(
        normalized["confidence"], _confidence(classification["confidence"])
    )
    return {"normalized": normalized}
