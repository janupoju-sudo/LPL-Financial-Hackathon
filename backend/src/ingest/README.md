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

`backend/template.yaml` now contains the B functions, policies, model-ID parameter,
Step Functions integration, and upload trigger. D's Ask function uses the same
`BedrockModelId` parameter; neither path contains a default model ID.

The S3 EventBridge rule matches only `uploads/` keys; Textract results are written
under `processing/` to avoid retriggering ingest. Step Functions invokes the
existing `CreateBillFunction` for invoices/receipts.

When using E's `e/infra` branch, retain `backend/scripts/seed_ddb.py` but do not merge
its `backend/template.yaml` as-is: that file re-adds D resources already present in
`main`. Transfer the seed script separately when E is ready.

No EC2 instances or other manually managed servers are required.
