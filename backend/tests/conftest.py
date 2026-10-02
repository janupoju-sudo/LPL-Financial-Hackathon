import json
import os

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1", "AWS_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
    "TABLE_NAME": "ledgerline-test", "EVENT_BUS_NAME": "default",
    "DOCS_BUCKET": "ledgerline-test-docs", "DEFAULT_PRACTICE_ID": "p1",
    "APPROVE_SM_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test",
})

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

from shared import ddb, events, workflow  # noqa: E402


class FakeSfn:
    def __init__(self):
        self.started, self.resumed = [], []

    def start_execution(self, **kw):
        self.started.append(json.loads(kw["input"]))
        return {"executionArn": f"arn:exec:{len(self.started)}"}

    def send_task_success(self, taskToken, output):
        self.resumed.append((taskToken, json.loads(output)))


@pytest.fixture
def aws():
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="ledgerline-test", BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                  {"AttributeName": "SK", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                       {"AttributeName": "SK", "KeyType": "RANGE"}],
        )
        ddb.reset_clients()
        events._client = None
        fake = FakeSfn()
        workflow.set_client(fake)
        yield fake
        workflow.set_client(None)


def api_event(route_key, path=None, body=None, query=None, groups=("owner",), sub="user-owner"):
    return {
        "routeKey": route_key,
        "pathParameters": path or {},
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "sub": sub, "email": f"{sub}@harborpoint.example",
            "cognito:groups": "[" + " ".join(groups) + "]",
        }}}},
    }


def body_of(resp):
    return json.loads(resp["body"])
