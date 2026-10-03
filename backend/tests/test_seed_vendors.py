"""Offline seed tests: no SDK, credentials, table, or network required."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed


class VendorRepository:
    def __init__(self):
        self.practices = {}
        self.counter = 0

    def list_vendors(self, practice):
        return list(self.practices.get(practice, {}).values())

    def find_vendor_by_name(self, practice, name):
        return next((v for v in self.list_vendors(practice)
                     if v["name"].casefold() == name.casefold()), None)

    def create_vendor(self, practice, name, **fields):
        self.counter += 1
        vendor = dict(vendorId=f"ven-{self.counter}", name=name, aliases=[], billCount=0, **fields)
        self.practices.setdefault(practice, {})[vendor["vendorId"]] = vendor
        return vendor

    def list_rules(self, practice):
        raise AssertionError("vendors-only must not read/write rules")


class SeedVendorTests(unittest.TestCase):
    def setUp(self):
        self.repo = VendorRepository()
        shared = types.ModuleType("shared")
        shared.repo = self.repo
        def forbidden(*args, **kwargs):
            raise AssertionError("vendors-only must not replace practice metadata")
        shared.ddb = types.SimpleNamespace(put_item=forbidden)
        self.modules = patch.dict(sys.modules, {"shared": shared})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_fresh_practice_meets_target_and_retains_workflow_names(self):
        vendors = seed.seed_vendors("p1")
        self.assertEqual(len(vendors), 9)
        self.assertEqual(len({v["name"].casefold() for v in vendors}), 9)
        for vendor in vendors:
            self.assertIn(vendor["default_gl_account"],
                          {"6100", "6200", "6300", "6400", "6500", "6600", "6700", "6900"})
        for name in ("Orion Software LLC", "Seaport Office Partners", "LPL Financial",
                     "Brightline Marketing", "Clearwater Compliance Advisors (FICTIONAL)"):
            self.assertIsNotNone(self.repo.find_vendor_by_name("p1", name))
        brightline = self.repo.find_vendor_by_name("p1", "Brightline Marketing")
        self.assertFalse(brightline["hasW9"])
        self.assertFalse(brightline["hasVoidCheck"])
        self.assertNotIn("bankLast4", brightline)

    def test_rerun_preserves_vendor_state_and_custom_vendors(self):
        seed.seed_vendors("p1")
        brightline = self.repo.find_vendor_by_name("p1", "Brightline Marketing")
        brightline.update(hasW9=True, hasVoidCheck=True, bankLast4="1234",
                         billCount=7, aliases=["brightline agency"])
        self.repo.create_vendor("p1", "Existing Custom Vendor", default_gl_account="6900")
        before = {v["vendorId"]: dict(v) for v in self.repo.list_vendors("p1")}
        self.assertEqual(len(seed.seed_vendors("p1")), 10)
        self.assertEqual({v["vendorId"]: v for v in self.repo.list_vendors("p1")}, before)

    def test_selected_practice_isolated(self):
        self.repo.create_vendor("p2", "Existing Custom Vendor", default_gl_account="6900")
        before = [dict(v) for v in self.repo.list_vendors("p2")]
        seed.seed_vendors("p1")
        self.assertEqual(self.repo.list_vendors("p2"), before)
        self.assertEqual(len(self.repo.list_vendors("p1")), 9)

    def test_vendors_only_cli_preserves_meta_and_rules(self):
        with patch.object(sys, "argv", ["seed.py", "--table", "offline-placeholder",
                                       "--practice", "p1", "--vendors-only"]), \
             patch.dict(os.environ), redirect_stdout(StringIO()) as output:
            seed.main()
        self.assertIn("9 vendors", output.getvalue())
        self.assertEqual(len(self.repo.list_vendors("p1")), 9)


if __name__ == "__main__":
    unittest.main()
