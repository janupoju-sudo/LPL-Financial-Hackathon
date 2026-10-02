"""Step Functions helpers: start the ApproveBill workflow and resume waiting tasks."""
import json
import time

import boto3

from . import config

_client = None


def sfn():
    global _client
    if _client is None:
        _client = boto3.client("stepfunctions")
    return _client


def set_client(client):
    """Tests inject a fake client here."""
    global _client
    _client = client


def start_approval(practice_id: str, bill_id: str) -> str:
    resp = sfn().start_execution(
        stateMachineArn=config.APPROVE_SM_ARN,
        name=f"{bill_id}-{int(time.time() * 1000)}",
        input=json.dumps({"practiceId": practice_id, "billId": bill_id}),
    )
    return resp["executionArn"]


def resume(task_token: str, output: dict) -> None:
    """output.decision: 'approve' | 'reject' | 'reevaluate'."""
    sfn().send_task_success(taskToken=task_token, output=json.dumps(output, default=str))
