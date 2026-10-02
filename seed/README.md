# E8 demo document pack

This folder generates the local sample PDF set used for B8 testing and demo validation.

## Generate the documents

```bash
cd /Users/advika/LPL-Financial-Hackathon
. backend/.venv/bin/activate
python seed/generate_docs.py --output-dir seed/docs
```

The script writes seven PDFs and a manifest at `seed/docs/manifest.json`.

## B8 checklist

- Upload: confirm each PDF can be uploaded as a document and lands in the correct S3 prefix with the expected document type.
- Extraction: verify vendor, amount, invoice number, date, and GL account fields match the expected values in the manifest.
- Vendor matching: Orion Software LLC matches an existing vendor; Brightline Marketing is a new vendor and must trigger onboarding requirements.
- Approval / hold / resume: $450 Orion invoice auto-approves; $1,850 Orion invoice requires partner/owner approval; Brightline invoice remains on hold until both W-9 and void check are present.
- Ledger posting: approved invoices post to the correct expense/AP ledger entries with the intended September 2026 dates.
- Reconciliation: the payout statement shows contract 4471 actual 247800, expected 289000, variance -41200 cents, status "short".

## Output folder

- `seed/docs/` contains the generated PDFs and the manifest.
- `seed/docs/previews/` contains PNG renderings for visual inspection.
