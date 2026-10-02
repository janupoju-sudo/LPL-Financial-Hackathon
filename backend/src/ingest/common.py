import json
import os
import re
from pathlib import PurePosixPath
from typing import Any, Mapping


DOCUMENT_TYPES = {
    "invoice",
    "receipt",
    "void_check",
    "w9",
    "payout_statement",
    "unknown",
}


def upload_context(event: Mapping[str, Any]) -> dict[str, str]:
    detail = event.get("detail", {})
    bucket_data = detail.get("bucket", {}) if isinstance(detail, Mapping) else {}
    object_data = detail.get("object", {}) if isinstance(detail, Mapping) else {}
    bucket = bucket_data.get("name") if isinstance(bucket_data, Mapping) else None
    key = object_data.get("key") if isinstance(object_data, Mapping) else None
    bucket = bucket or event.get("bucket")
    key = key or event.get("key") or event.get("s3Key")
    if not isinstance(bucket, str) or not bucket:
        raise ValueError("S3 bucket is required")
    if not isinstance(key, str):
        raise ValueError("S3 object key is required")

    parts = PurePosixPath(key).parts
    if len(parts) != 4 or parts[0] != "uploads" or not parts[1] or not parts[2]:
        raise ValueError(
            "S3 key must be uploads/<practiceId>/<documentId>/<filename>"
        )
    return {
        "bucket": bucket,
        "key": key,
        "practiceId": parts[1],
        "documentId": parts[2],
        "filename": parts[3],
    }


def state_context(event: Mapping[str, Any]) -> dict[str, str]:
    classification = event.get("classification")
    if isinstance(classification, Mapping):
        data = classification.get("data")
        if isinstance(data, Mapping):
            return {
                key: _required_string(data, key)
                for key in ("bucket", "key", "practiceId", "documentId", "filename")
            }
    return upload_context(event)


def bedrock_model_id() -> str:
    model_id = os.environ.get("BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        raise RuntimeError(
            "BEDROCK_MODEL_ID must name a model enabled and approved for this account"
        )
    return model_id


def invoke_bedrock_json(prompt: str, document: dict[str, Any] | None = None) -> dict[str, Any]:
    import boto3

    content: list[dict[str, Any]] = []
    if document:
        content.append(document)
    content.append({"text": prompt})
    response = boto3.client("bedrock-runtime").converse(
        modelId=bedrock_model_id(),
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"temperature": 0, "maxTokens": 1200},
    )
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    text = "\n".join(
        block["text"] for block in blocks if isinstance(block.get("text"), str)
    )
    if not text.strip():
        raise ValueError("Bedrock returned no JSON text")
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text, flags=re.I)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("Bedrock response was not valid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Bedrock JSON response must be an object")
    return result


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Pipeline state is missing {key}")
    return value
