"""POST /ask logic (task D5): guardrail the question, build context, ask Claude,
guardrail the answer, and return {answer, citations:[{documentId, label, snippet}]}.

The model call and the guardrail are passed in, so this runs in tests without AWS.
  llm(system, user, schema) -> dict matching ANSWER_SCHEMA
  guard(text, source) -> (intervened: bool, text)   source is "INPUT" or "OUTPUT"
"""

from datetime import date

from . import context

SYSTEM = """You answer questions from the owner of an independent financial advisory practice about the practice's own finances: revenue, expenses, margin, payouts, bills and vendors.

Use only the ledger summary and documents in the user message. If they don't contain what's needed, say what is missing instead of guessing. Give specific numbers in dollars and percentages, and name the two or three biggest drivers when asked why something changed. Keep answers to a short paragraph.

Do not give investment advice or recommendations about clients' accounts or securities. This tool covers the practice's books only; say so if asked.

In "citations", list the bracketed ids of the documents you relied on, only from the list provided. Use an empty list if none apply."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "citations"],
    "additionalProperties": False,
}

BLOCKED_QUESTION = ("I can only answer questions about your practice's own books, "
                    "like revenue, expenses, payouts and bills.")
REFUSED = "I couldn't answer that one. Try asking about a specific period or account."


class Refused(Exception):
    """The model declined the request (stop_reason "refusal")."""


def ask(question: str, entries, documents, today: date, llm, guard) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Ask a question first.")

    blocked, _ = guard(question, "INPUT")
    if blocked:
        return {"answer": BLOCKED_QUESTION, "citations": [], "period": None}

    ctx = context.build(question, entries, documents, today)
    user = f"{ctx['text']}\n\nQUESTION\n{question}"
    try:
        out = llm(SYSTEM, user, ANSWER_SCHEMA)
    except Refused:
        return {"answer": REFUSED, "citations": [], "period": ctx["period"]}

    _, answer = guard(out["answer"], "OUTPUT")  # masked text if PII was found

    by_id = {context.doc_id(d): d for d in ctx["documents"]}
    seen, citations = set(), []
    for doc_id in out.get("citations", []):
        if doc_id in by_id and doc_id not in seen:  # drop ids the model made up
            seen.add(doc_id)
            d = by_id[doc_id]
            citations.append({"documentId": doc_id, "label": context.doc_label(d),
                              "snippet": context.doc_snippet(d)})
    return {"answer": answer, "citations": citations, "period": ctx["period"]}
