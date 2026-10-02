"""Best-effort EventBridge publishing on the app bus."""
import json

import boto3

from . import config
from .ddb import from_ddb

_client = None


def _events():
    global _client
    if _client is None:
        _client = boto3.client("events")
    return _client


def put_event(detail_type: str, detail: dict, source: str = "ledgerline.backend") -> None:
    try:
        _events().put_events(Entries=[{
            "Source": source,
            "DetailType": detail_type,
            "Detail": json.dumps(from_ddb(detail), default=str),
            "EventBusName": config.EVENT_BUS_NAME,
        }])
    except Exception as exc:  # events are informational; never fail the request on them
        print(f"[events] failed to publish {detail_type}: {exc}")
