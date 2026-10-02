"""AWS calls for Ask: Claude on Amazon Bedrock and the Bedrock Guardrail (D8).

Env vars:
  AWS_REGION           set by Lambda
  ASK_MODEL_ID         defaults to anthropic.claude-opus-5-5
  GUARDRAIL_ID         from D8; if unset, the guardrail step is skipped (local testing)
  GUARDRAIL_VERSION    defaults to DRAFT
"""

import json
import os

import boto3
from anthropic import AnthropicBedrockMantle

from .answer import Refused

MODEL_ID = os.environ.get("ASK_MODEL_ID", "anthropic.claude-opus-5-5")

_claude = None
_runtime = None


def claude_json(system: str, user: str, schema: dict) -> dict:
    global _claude
    _claude = _claude or AnthropicBedrockMantle(aws_region=os.environ["AWS_REGION"])
    resp = _claude.messages.create(
        model=MODEL_ID,
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
