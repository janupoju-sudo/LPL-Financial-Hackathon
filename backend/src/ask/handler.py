"""POST /ask (D5). Body: {"question": "..."}."""

from datetime import date

from shared import ddb, repo
from shared.auth import get_caller
from shared.http import HttpError, parse_body, router

from .answer import ask


def ask_books(event):
    from . import bedrock  # imported here so tests can run without the anthropic SDK

    caller = get_caller(event)
    today = date.today()
    entries = ddb.get_ledger_entries(caller.practice_id, f"{today.year - 2}-01-01", today.isoformat())
    documents = repo.list_documents(caller.practice_id)
    try:
        result = ask(parse_body(event).get("question", ""), entries, documents, today,
                     llm=bedrock.claude_json, guard=bedrock.apply_guardrail)
    except ValueError as e:
        raise HttpError(400, str(e))
    return 200, result


handler = router({"POST /ask": ask_books})
