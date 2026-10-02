"""Seed the minimum the backend needs: practice META, default rules, demo vendors.

Usage:  python scripts/seed.py --table ledgerline-dev [--practice p1]
Role E's seed_ddb.py adds ledger history on top of this.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--practice", default="p1")
    args = ap.parse_args()
    os.environ["TABLE_NAME"] = args.table

    from shared import ddb, repo

    p = args.practice
    ddb.put_item(p, "META", {
        "practiceId": p, "name": "Harbor Point Wealth (FICTIONAL)", "owner": "Maya Chen",
        "aum": 250_000_000, "clientCount": 180, "top10Share": 0.22, "staffCount": 4,
    })
    repo.list_rules(p)  # writes DEFAULT_RULES if none exist
    vendors = [
        ("Orion Software LLC", "6300", True, True, "4821"),       # CRM - known vendor, docs on file
        ("Seaport Office Partners", "6200", True, True, "1190"),  # rent
        ("LPL Financial", "6400", True, True, "0007"),            # platform fees
        ("Brightline Marketing", "6500", False, False, None),     # NEW vendor - missing docs (hold demo)
    ]
    for name, gl, w9, void, last4 in vendors:
        if not repo.find_vendor_by_name(p, name):
            repo.create_vendor(p, name, default_gl_account=gl, hasW9=w9, hasVoidCheck=void,
                               **({"bankLast4": last4} if last4 else {}))
    print(f"Seeded practice {p} into {args.table}: META, {len(repo.list_rules(p))} rules, "
          f"{len(repo.list_vendors(p))} vendors")


if __name__ == "__main__":
    main()
