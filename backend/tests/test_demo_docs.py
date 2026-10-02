import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "seed" / "generate_docs.py"
OUTPUT_DIR = ROOT / "seed" / "docs"


def test_generate_docs_produces_expected_manifest():
    assert SCRIPT.exists(), "E8 generator script is missing"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(OUTPUT_DIR)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    manifest = json.loads((OUTPUT_DIR / "manifest.json").read_text())
    assert len(manifest["files"]) == 7
    names = {item["filename"] for item in manifest["files"]}
    assert "orion_invoice_450_2026-09-02.pdf" in names
    assert "brightline_invoice_650_2026-09-18.pdf" in names
    assert "lpl_payout_statement_sep_2026.pdf" in names

    payout = next(item for item in manifest["files"] if item["filename"] == "lpl_payout_statement_sep_2026.pdf")
    assert payout["expected_fields"]["actual_4471_cents"] == 247800
    assert payout["expected_fields"]["expected_4471_cents"] == 289000
    assert payout["workflow_outcome"]["variance_cents"] == -41200
    assert payout["workflow_outcome"]["status"] == "short"
