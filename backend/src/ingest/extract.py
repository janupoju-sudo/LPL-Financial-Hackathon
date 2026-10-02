import hashlib
import json
import os
import time
from typing import Any, Mapping

from .common import state_context


def _get_textract_result(
    client: Any, method: str, job_id: str, context: Any
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    next_token = None
    while True:
        parameters: dict[str, Any] = {"JobId": job_id}
        if next_token:
            parameters["NextToken"] = next_token
        page = getattr(client, method)(**parameters)
        status = page.get("JobStatus")
        if status == "FAILED":
            raise RuntimeError(
                f"Textract job {job_id} failed: {page.get('StatusMessage', 'no details')}"
            )
        if status not in {"SUCCEEDED", "PARTIAL_SUCCESS"}:
            remaining = (
                context.get_remaining_time_in_millis()
                if context is not None
                else 840_000
            )
            if remaining < 5_000:
                raise TimeoutError(f"Textract job {job_id} exceeded Lambda time")
            time.sleep(min(max(int(os.getenv("TEXTRACT_POLL_SECONDS", "2")), 1), 10))
            continue

        for key, value in page.items():
            if key not in {"NextToken", "JobStatus"}:
                if isinstance(value, list):
                    result.setdefault(key, []).extend(value)
                else:
                    result[key] = value
        next_token = page.get("NextToken")
        if not next_token:
            result["JobStatus"] = status
            return result


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    import boto3

    upload = state_context(event)
    document_type = event["classification"]["data"]["documentType"]
    client = boto3.client("textract")
    token = hashlib.sha256(
        f"{upload['bucket']}/{upload['key']}/{document_type}".encode()
    ).hexdigest()[:64]
    location = {"S3Object": {"Bucket": upload["bucket"], "Name": upload["key"]}}

    if document_type in {"invoice", "receipt"}:
        started = client.start_expense_analysis(
            DocumentLocation=location,
            ClientRequestToken=token,
        )
        job_id = started["JobId"]
        method = "get_expense_analysis"
    else:
        started = client.start_document_analysis(
            DocumentLocation=location,
            FeatureTypes=["FORMS", "TABLES"],
            ClientRequestToken=token,
        )
        job_id = started["JobId"]
        method = "get_document_analysis"

    result = _get_textract_result(client, method, job_id, context)
    analysis_key = (
        f"processing/{upload['practiceId']}/{upload['documentId']}/textract.json"
    )
    boto3.client("s3").put_object(
        Bucket=upload["bucket"],
        Key=analysis_key,
        Body=json.dumps(result, separators=(",", ":")).encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return {"textractKey": analysis_key, "jobId": job_id}
