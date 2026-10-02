import re
from typing import Any, Mapping

from .common import DOCUMENT_TYPES, invoke_bedrock_json, upload_context


_IMAGE_FORMATS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png"}


def validate_classification(result: Mapping[str, Any]) -> tuple[str, float]:
    document_type = result.get("type")
    confidence = result.get("confidence")
    if not isinstance(document_type, str) or document_type not in DOCUMENT_TYPES:
        raise ValueError(f"Unsupported document type from classifier: {document_type!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, (float, int)):
        raise ValueError("Classifier confidence must be a number")
    confidence = float(confidence)
    if not 0 <= confidence <= 1:
        raise ValueError("Classifier confidence must be between 0 and 1")
    return document_type, confidence


def _bedrock_document(filename: str, body: bytes) -> dict[str, Any]:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", filename.rsplit(".", 1)[0])[:100]
    if extension == "pdf":
        return {
            "document": {
                "format": "pdf",
                "name": safe_name or "upload",
                "source": {"bytes": body},
            }
        }
    image_format = _IMAGE_FORMATS.get(extension)
    if image_format:
        return {
            "image": {"format": image_format, "source": {"bytes": body}}
        }
    raise ValueError(
        f"Bedrock document classification does not support .{extension or 'unknown'} files"
    )


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    import boto3

    upload = upload_context(event)
    response = boto3.client("s3").get_object(Bucket=upload["bucket"], Key=upload["key"])
    result: dict[str, Any]
    try:
        document = _bedrock_document(upload["filename"], response["Body"].read())
    except ValueError as exc:
        if not upload["filename"].lower().endswith((".tif", ".tiff")):
            raise
        result = {
            "type": "unknown",
            "confidence": 0.0,
            "reviewReason": str(exc),
        }
    else:
        try:
            result = invoke_bedrock_json(
                "Classify this fictional financial-practice document as exactly one of "
                "invoice, receipt, void_check, w9, payout_statement, or unknown. "
                "Return only JSON with keys type and confidence, where confidence is 0 to 1.",
                document,
            )
            document_type, confidence = validate_classification(result)
        except ValueError as exc:
            result = {
                "type": "unknown",
                "confidence": 0.0,
                "reviewReason": str(exc),
            }
            document_type, confidence = "unknown", 0.0
    if result["type"] == "unknown" and result.get("confidence") == 0.0:
        document_type, confidence = "unknown", 0.0
    else:
        document_type, confidence = validate_classification(result)
    from shared import repo

    repo.update_document(
        upload["practiceId"],
        upload["documentId"],
        type=document_type,
        status="extracting",
        confidence=confidence,
    )
    return {
        **upload,
        "documentType": document_type,
        "confidence": confidence,
        "reviewReason": result.get("reviewReason"),
    }
