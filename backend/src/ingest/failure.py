from typing import Any, Mapping

from .common import state_context


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, str]:
    from shared import repo

    upload = state_context(event)
    classification = event.get("classification", {}).get("data", {})
    document_type = classification.get("documentType", "unknown")
    confidence = classification.get("confidence", 0.0)
    error = event.get("pipelineError", {}).get("Error", "PipelineTaskFailed")
    reason = f"Ingest failed at {error}; manual review is required"
    repo.update_document(
        upload["practiceId"],
        upload["documentId"],
        type=document_type,
        status="needs_review",
        confidence=confidence,
        extracted={"reviewReason": reason},
    )
    return {"status": "needs_review", "reason": reason}
