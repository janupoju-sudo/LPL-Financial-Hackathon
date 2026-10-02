"""AWS calls for Ask: Claude on Amazon Bedrock and the Bedrock Guardrail (D8).

Env vars:
  AWS_REGION           set by Lambda
  ASK_MODEL_ID         required; set to an approved, enabled Bedrock model ID
  GUARDRAIL_ID         from D8; if unset, the guardrail step is skipped (local testing)
  GUARDRAIL_VERSION    defaults to DRAFT
"""

import json
import os

import boto3

from .answer import Refused

_claude = None
_runtime = None


def model_id() -> str:
    value = os.environ.get("ASK_MODEL_ID", "").strip()
    if not value:
        raise RuntimeError(
            "ASK_MODEL_ID must be set to a model approved and enabled for this account"
        )
    return value


def claude_json(system: str, user: str, schema: dict) -> dict:
    global _claude
    if _claude is None:
        # Imported here so the rest of the backend (and its tests) don't need the SDK.
        from anthropic import AnthropicBedrockMantle
        _claude = AnthropicBedrockMantle(aws_region=os.environ["AWS_REGION"])
    resp = _claude.messages.create(
        model=model_id(),
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
    )
    if resp.stop_reason == "refusal":
        raise Refused(getattr(resp.stop_details, "category", None))
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def apply_guardrail(text: str, source: str) -> tuple[bool, str]:
    """Runs the Bedrock Guardrail on a question (INPUT) or answer (OUTPUT).
    Returns (intervened, text), where text is the guardrail's blocked message
    or PII-masked version when it intervened."""
    guardrail_id = os.environ.get("GUARDRAIL_ID")
    if not guardrail_id:
        return False, text
    global _runtime
    _runtime = _runtime or boto3.client("bedrock-runtime")
    r = _runtime.apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=os.environ.get("GUARDRAIL_VERSION", "DRAFT"),
        source=source,
        content=[{"text": {"text": text}}],
    )
    if r.get("action") == "GUARDRAIL_INTERVENED":
        return True, " ".join(o.get("text", "") for o in r.get("outputs", [])) or text
    return False, text
