"""Tiny router + response helpers for API Gateway HTTP API (payload v2)."""
import base64
import json
import traceback

from .ddb import from_ddb


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(from_ddb(body), default=str),
    }


def parse_body(event) -> dict:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise HttpError(400, "Request body must be valid JSON")
    if not isinstance(body, dict):
        raise HttpError(400, "Request body must be a JSON object")
    return body


def path_param(event, name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name)
    if not value:
        raise HttpError(400, f"Missing path parameter: {name}")
    return value


def query_param(event, name: str, default=None):
    return (event.get("queryStringParameters") or {}).get(name, default)


def router(routes: dict):
    """routes maps routeKey (e.g. 'GET /bills/{id}') -> fn(event) returning (status, body)."""
    def handler(event, context=None):
        fn = routes.get(event.get("routeKey", ""))
        if fn is None:
            return response(404, {"error": f"No route for {event.get('routeKey')}"})
        try:
            status, body = fn(event)
            return response(status, body)
        except HttpError as err:
            return response(err.status, {"error": err.message})
        except Exception:
            traceback.print_exc()
            return response(500, {"error": "Internal server error"})
    return handler
