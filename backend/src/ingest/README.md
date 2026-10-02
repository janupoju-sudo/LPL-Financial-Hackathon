# Document ingest (role B)

`statemachines/ingest_document.asl.json` orchestrates these handlers:

| Step | Lambda handler |
| --- | --- |
| Classify | `ingest.classify.handler` |
| Extract with Textract | `ingest.extract.handler` |
| Normalize | `ingest.normalize.handler` |
| Vendor match | `ingest.match_vendor.handler` |
| Prepare invoice/receipt bill | `ingest.route.prepare_bill` |
| Finalize vendor docs/payout or bill | `ingest.route.handler` |
| Mark a failed document for review | `ingest.failure.handler` |

Set `BEDROCK_MODEL_ID` to an enabled model approved for the hackathon account. The
provided service list allows Claude Opus 5, but does not list Claude Opus 5.5; do not
hardcode an unapproved model ID. The extractor Lambda needs a timeout long enough to
poll Textract asynchronous jobs (up to 15 minutes).

The state machine/event rule needs permission to invoke these Lambdas and
`CreateBillFunction`. The Lambdas need access to Textract analysis APIs, Bedrock
inference, the uploads/processing objects in the documents bucket, and the shared
repository/ledger resources. The S3 EventBridge rule should match only `uploads/`
keys; Textract results are written under `processing/` to avoid retriggering ingest.

No EC2 instances or other manually managed servers are required.
