import csv
import io
import json
import unittest
import zipfile

from export import package
from financials import api
from fixtures import DOCUMENTS, PRACTICE, sample_entries


class Export(unittest.TestCase):
    def build(self, fetch=lambda key: b"%PDF-1.4 sample " + key.encode()):
        e = sample_entries()
        fin = api.build_financials(e, "2026-Q3", PRACTICE)
        data, summary = package.build_zip("2026-Q3", "Harbor Point Wealth", DOCUMENTS, e, fin, fetch)
        return zipfile.ZipFile(io.BytesIO(data)), summary

    def test_contents(self):
        z, summary = self.build()
        names = set(z.namelist())
        self.assertIn("ledger.csv", names)
        self.assertIn("financials.json", names)
        self.assertIn("README.txt", names)
        self.assertIn("documents/invoice/Orion_INV-2291.pdf", names)
        self.assertIn("documents/payout_statement/LPL_Payout_Sep2026.pdf", names)
        self.assertNotIn("documents/w9/Orion_W9.pdf", names)  # June, not referenced in Q3
        self.assertEqual(summary["missing"], [])

    def test_ledger_csv_balances(self):
        z, summary = self.build()
        rows = list(csv.DictReader(io.StringIO(z.read("ledger.csv").decode())))
        self.assertEqual(len(rows), summary["ledgerLines"])
        self.assertTrue(all(r["date"].startswith("2026-0") and "07" <= r["date"][5:7] <= "09" for r in rows))
        debit = sum(float(r["debit"]) for r in rows)
        credit = sum(float(r["credit"]) for r in rows)
        self.assertAlmostEqual(debit, credit, places=2)
        self.assertEqual(json.loads(z.read("financials.json"))["period"], "2026-Q3")

    def test_missing_file_is_listed_not_fatal(self):
        def fetch(key):
            if key == "uploads/d1.pdf":
                raise FileNotFoundError(key)
            return b"x"
        z, summary = self.build(fetch)
        self.assertEqual(summary["missing"], ["Orion_INV-2291.pdf"])
        self.assertIn("Could not include: Orion_INV-2291.pdf", z.read("README.txt").decode())


if __name__ == "__main__":
    unittest.main()
