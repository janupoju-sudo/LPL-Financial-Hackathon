"""Environment-driven configuration. Values are read at import time."""
import os

TABLE_NAME = os.environ.get("TABLE_NAME", "ledgerline-dev")
DOCS_BUCKET = os.environ.get("DOCS_BUCKET", "")
DEFAULT_PRACTICE_ID = os.environ.get("DEFAULT_PRACTICE_ID", "p1")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "default")
APPROVE_SM_ARN = os.environ.get("APPROVE_SM_ARN", "")
REVIEW_CONFIDENCE_THRESHOLD = float(os.environ.get("REVIEW_CONFIDENCE_THRESHOLD", "0.8"))
ALLOW_SELF_APPROVAL = os.environ.get("ALLOW_SELF_APPROVAL", "false").lower() == "true"
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "1"))
PRESIGN_EXPIRY_SECONDS = int(os.environ.get("PRESIGN_EXPIRY_SECONDS", "900"))
