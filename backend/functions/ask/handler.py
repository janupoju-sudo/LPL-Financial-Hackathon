"""Lambda entry point for POST /ask. Body: {"question": "..."}."""

import json
from datetime import date

from .answer import ask

PRACTICE_ID = "p1"


def _reply(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def lambda_handler(event, _context):
    from shared import ddb  # C1
    from . import bedrock

    try:
        question = json.loads(event.get("body") or "{}").get("question", "")
        today = date.today()
        entries = ddb.get_ledger_entries(PRACTICE_ID, date(today.year - 2, 1, 1), today)
        documents = ddb.list_documents(PRACTICE_ID)
        result = ask(question, entries, documents, today,
                     llm=bedrock.claude_json, guard=bedrock.apply_guardrail)
        return _reply(200, result)
    except ValueError as e:
        return _reply(400, {"error": str(e)})
