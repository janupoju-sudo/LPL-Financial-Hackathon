"""Local server for D's endpoints using the fictional sample data. No AWS needed.

    cd backend && pip install -r requirements-dev.txt   # once (boto3 for C's shared code)
    python3 dev_server.py                               # http://localhost:8787

Lets the frontend call the real financials code before DynamoDB, Bedrock and
S3 exist. Ask returns a canned sample answer unless USE_BEDROCK=1 is set.

  GET  /financials?period=2026-Q3
  GET  /revenue/reconciliation?period=2026-09
  POST /ask      {"question": "..."}
  POST /export   {"period": "2026-Q3"}
"""

import json
import os
import re
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE / "src"), str(HERE / "tests")]

import fixtures  # noqa: E402
from shared import ddb, repo  # noqa: E402

PORT = int(os.environ.get("PORT", 8787))
EXPORT_DIR = HERE / ".dev-exports"
TODAY = date(2026, 10, 2)  # the sample data runs through Sep 2026

ENTRIES = fixtures.sample_entries()

# Swap C's DynamoDB reads for the sample data. Nothing touches AWS.
ddb.get_ledger_entries = lambda pid, start, end: [e for e in ENTRIES if str(start) <= e["date"] <= str(end)]
ddb.get_practice = lambda pid: {**fixtures.PRACTICE, "feeSchedule": fixtures.FEE_SCHEDULE}
ddb.get_revenue_lines = lambda pid, period: fixtures.PAYOUT_SEP if period == "2026-09" else []
repo.list_documents = lambda pid, doc_type=None, q=None: fixtures.DOCUMENTS

from ask import answer  # noqa: E402
from export.package import build_zip  # noqa: E402
from financials import api, handler as fin  # noqa: E402


def sample_llm(system, user, schema):
    """Canned answer built from the context, so the UI has something real-looking."""
    margin = re.search(r"Operating margin: (.+)", user)
    drivers = re.search(r"BIGGEST CHANGES: (.+)", user)
    ids = re.findall(r"^\[([^\]]+)\]", user, re.M)
    text = "Sample answer (Bedrock not connected). "
    if margin:
        text += f"Operating margin was {margin[1]}. "
    if drivers:
        text += f"The biggest changes were in {drivers[1]}."
    return {"answer": text, "citations": ids[:3]}


def no_guard(text, source):
    return False, text


if os.environ.get("USE_BEDROCK") == "1":
    from ask import bedrock
    LLM, GUARD = bedrock.claude_json, bedrock.apply_guardrail
else:
    LLM, GUARD = sample_llm, no_guard


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _lambda(self, route, query):
        r = fin.handler({"routeKey": route, "queryStringParameters": {k: v[0] for k, v in query.items()}})
        self._send(r["statusCode"], json.loads(r["body"]))

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path == "/financials":
            q.setdefault("period", ["2026-Q3"])
            return self._lambda("GET /financials", q)
        if url.path == "/revenue/reconciliation":
            q.setdefault("period", ["2026-09"])
            return self._lambda("GET /revenue/reconciliation", q)
        if url.path.startswith("/exports/"):
            f = EXPORT_DIR / Path(url.path).name
            if f.exists():
                return self._send(200, f.read_bytes(), "application/zip")
        self._send(404, {"error": f"No route for GET {url.path}"})

    def do_POST(self):
        url = urlparse(self.path)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "Body must be JSON."})
        try:
            if url.path == "/ask":
                docs = repo.list_documents("p1")
                return self._send(200, answer.ask(body.get("question", ""), ENTRIES, docs, TODAY, LLM, GUARD))
            if url.path == "/export":
                period = body.get("period", "2026-Q3")
                fin_body = api.build_financials(ENTRIES, period, ddb.get_practice("p1"))
                data, summary = build_zip(period, fixtures.PRACTICE["name"], fixtures.DOCUMENTS, ENTRIES,
                                          fin_body, lambda key: b"SAMPLE - FICTIONAL DATA\n" + key.encode())
                EXPORT_DIR.mkdir(exist_ok=True)
                name = f"{period}.zip"
                (EXPORT_DIR / name).write_bytes(data)
                return self._send(200, {"downloadUrl": f"http://localhost:{PORT}/exports/{name}", **summary})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": f"No route for POST {url.path}"})


if __name__ == "__main__":
    print(f"D endpoints on http://localhost:{PORT} (sample data, Ask: {'Bedrock' if LLM is not sample_llm else 'canned'})")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
