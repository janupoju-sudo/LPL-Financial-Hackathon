"""Seed the minimum the backend needs: practice META, default rules, demo vendors.

Usage:  python scripts/seed.py --table ledgerline-dev [--practice p1]
Role E's seed_ddb.py adds ledger history on top of this.
Use --vendors-only to add missing demo vendors without replacing META or rules.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# Fictional demo vendors. Keep the four workflow names and onboarding flags stable.
DEMO_VENDORS = (
    ("Orion Software LLC", "6300", True, True, "4821"),
    ("Seaport Office Partners", "6200", True, True, "1190"),
    ("LPL Financial", "6400", True, True, "0007"),
    ("Brightline Marketing", "6500", False, False, None),
    ("Clearwater Compliance Advisors (FICTIONAL)", "6600", True, True, "8623"),
    ("Horizon Managed IT LLC", "6300", True, True, "4142"),
    ("Oakridge Payroll Services", "6100", True, True, "7734"),
    ("Pinecrest Office Supply LLC", "6900", True, True, "6285"),
    ("Waypoint Business Travel LLC", "6700", True, True, "9056"),
)


def seed_vendors(practice_id):
    """Add missing vendors; retain existing IDs, onboarding, aliases and bill counts."""
    from shared import repo

    for name, gl, w9, void, last4 in DEMO_VENDORS:
        if not repo.find_vendor_by_name(practice_id, name):
            repo.create_vendor(practice_id, name, default_gl_account=gl,
                               hasW9=w9, hasVoidCheck=void,
                               **({"bankLast4": last4} if last4 else {}))
    return repo.list_vendors(practice_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--practice", default="p1")
    ap.add_argument("--vendors-only", action="store_true",
                    help="add missing demo vendors only; preserve practice settings, rules and history")
    args = ap.parse_args()
    os.environ["TABLE_NAME"] = args.table

    from shared import ddb, repo

    p = args.practice
    if args.vendors_only:
        vendors = seed_vendors(p)
        print(f"Seeded vendors for practice {p} into {args.table}: {len(vendors)} vendors")
        return
    ddb.put_item(p, "META", {
        "practiceId": p, "name": "Harbor Point Wealth (FICTIONAL)", "owner": "Maya Chen",
        "aum": 250_000_000, "clientCount": 180, "top10Share": 0.22, "staffCount": 4,
        # Expected revenue for reconciliation (D4). Amounts/aum in integer cents. E may replace.
        "feeSchedule": [
            {"id": "adv", "label": "Advisory fees", "source": "advisory",
             "basis": "fixed", "amount": 182_400_00, "frequency": "monthly"},
            {"id": "mf-comm", "label": "Mutual fund commissions", "source": "commission",
             "basis": "fixed", "amount": 14_200_00, "frequency": "monthly"},
            {"id": "12b1", "label": "12b-1 trails", "source": "trail", "ref": "12b1",
             "basis": "fixed", "amount": 6_150_00, "frequency": "monthly"},
            {"id": "va-4471", "label": "Variable annuity trail, contract ...4471", "source": "trail",
             "ref": "4471", "basis": "aum", "aum": 1_156_000_00, "annualRate": 0.01,
             "frequency": "quarterly", "billingMonths": [3, 6, 9, 12]},
        ],
    })
    repo.list_rules(p)  # writes DEFAULT_RULES if none exist
    seed_vendors(p)
    print(f"Seeded practice {p} into {args.table}: META, {len(repo.list_rules(p))} rules, "
          f"{len(repo.list_vendors(p))} vendors")


if __name__ == "__main__":
    main()
