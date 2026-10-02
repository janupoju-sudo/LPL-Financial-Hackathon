import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "seed" / "generate_docs.py"


def test_generate_docs_produces_expected_manifest_and_parser_contract(tmp_path):
    assert SCRIPT.exists(), "E8 generator script is missing"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest["files"]) == 7
    names = {item["filename"] for item in manifest["files"]}
    assert "orion_invoice_450_2026-09-02.pdf" in names
    assert "brightline_invoice_650_2026-09-18.pdf" in names
    assert "lpl_payout_statement_sep_2026.pdf" in names

    payout = next(
        item for item in manifest["files"] if item["filename"] == "lpl_payout_statement_sep_2026.pdf"
    )
    revenue_lines = payout["expected_fields"]["revenueLines"]
    assert len(revenue_lines) == 4
    assert [row["source"] for row in revenue_lines] == [
        "advisory",
        "commission",
        "trail",
        "trail",
    ]
    assert [row.get("ref", "") for row in revenue_lines] == ["", "", "12b1", "4471"]
    assert revenue_lines[0]["actual"] == 18_240_000
    assert revenue_lines[1]["actual"] == 1_420_000
    assert revenue_lines[2]["actual"] == 615_000
    assert revenue_lines[3]["actual"] == 247_800
    assert payout["workflow_outcome"]["total_paid"] == 205_228
    assert payout["workflow_outcome"]["actual_4471_cents"] == 247_800
    assert payout["workflow_outcome"]["expected_4471_cents"] == 289_000
    assert payout["workflow_outcome"]["variance_cents"] == -41_200
    assert payout["workflow_outcome"]["status"] == "short"

    pdf_bytes = (tmp_path / "lpl_payout_statement_sep_2026.pdf").read_bytes().decode("latin-1", "ignore")
    assert "Description" in pdf_bytes
    assert "Source" in pdf_bytes
    assert "Reference" in pdf_bytes
    assert "Amount" in pdf_bytes
    assert "Advisory fees" in pdf_bytes
    assert "Mutual fund commissions" in pdf_bytes
    assert "Monthly 12b-1 trails" in pdf_bytes
    assert "Variable annuity trail, contract 4471" in pdf_bytes
    assert "Total paid" in pdf_bytes
    assert "$205,228" in pdf_bytes
    assert "Expected: $2,890.00" in pdf_bytes or "Expected $2,890.00" in pdf_bytes
    assert "Shortfall: $412.00" in pdf_bytes or "Shortfall $412.00" in pdf_bytes
