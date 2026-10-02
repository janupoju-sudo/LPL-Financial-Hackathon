# E8 demo document pack

This folder generates the local sample PDF set used for B8 testing and demo validation.

## Generate the documents

```bash
cd /Users/advika/LPL-Financial-Hackathon
. backend/.venv/bin/activate
python seed/generate_docs.py --output-dir seed/docs
```

The script writes seven workflow samples, 16 supporting source PDFs under
`seed/docs/sources/`, and a manifest at `seed/docs/manifest.json`. The source
manifest records stable document IDs and planned S3 keys for the lease amendment,
July-September compliance invoices, and September 2025-August 2026 payout
statements.

The PDFs are local only. Their manifest upload status is `pending`, and the seeded
DynamoDB document records use `status=pending_upload`. No S3 objects or working
download links exist until the team uploads these files. Planned keys follow
`uploads/<practiceId>/<documentId>/<filename>`; for example:
`uploads/p1/doc_lease_amendment_2026_07/lease_amendment_effective_2026-07-01.pdf`.

## B8 checklist

- Upload: confirm each PDF can be uploaded as a document and lands in the correct S3 prefix with the expected document type.
- Extraction: verify vendor, amount, invoice number, date, and GL account fields match the expected values in the manifest.
- Vendor matching: Orion Software LLC matches an existing vendor; Brightline Marketing is a new vendor and must trigger onboarding requirements.
- Approval / hold / resume: $450 Orion invoice auto-approves; $1,850 Orion invoice requires partner/owner approval; Brightline invoice remains on hold until both W-9 and void check are present.
- Ledger posting: approved invoices post to the correct expense/AP ledger entries with the intended September 2026 dates.
- Reconciliation: the payout statement shows contract 4471 actual 247800, expected 289000, variance -41200 cents, status "short".

## September seed procedures

For a fresh table, seed the twelve-month history through August, then add
September's baseline expenses and payments before uploading the payout:

```bash
cd backend
python scripts/seed_ddb.py --table ledgerline-dev
python scripts/seed_ddb.py --table ledgerline-dev --live-sept
```

If the same seed version already populated history, run only the `--live-sept`
command; stable journal IDs make reruns safe.

This live mode leaves September payout revenue and `REV#2026-09#` records empty
for ingestion. Rent is $12,200/month from July 2026; compliance consulting adds
$2,550/month to account 6600 from July. Earlier months and existing seasonality
are unchanged.

Use fallback only if the live payout upload failed and no successful September
payout data exists:

```bash
python scripts/seed_ddb.py --table ledgerline-dev --include-sept
```

Fallback records the received contract 4471 amount of $2,478, not the $2,890
expected amount. It writes four payout revenue lines through the repository helper
and produces expected 289000, actual 247800, variance -41200 cents. The script
skips fallback revenue if September payout revenue rows or a payout journal are
already present. Do not upload the live statement after choosing fallback; use
only one September payout path for a demo.

The offline modes print Q2's complete margin, Q3's live-mode partial margin, and
Q3's complete fallback margin without contacting AWS:

```bash
cd backend
python scripts/seed_ddb.py --check --live-sept
python scripts/seed_ddb.py --check --include-sept
```

The source-document PDFs link to their journals through stable `DOC#` IDs. July
onward rent and consultant accrual/payment journals are separate to preserve
source attribution without double-counting. The seed refuses to add those split
journals on top of legacy July/August aggregate expense journals; migrate those
records explicitly before using this version against an already-seeded table.

## Output folder

- `seed/docs/` contains the generated PDFs and the manifest.
- `seed/docs/previews/` contains PNG renderings for visual inspection.
