"""Chart of accounts for an independent advisor practice (task D1, shared with C).

Codes follow the usual small-business ranges:
1xxx assets, 2xxx liabilities, 3xxx equity, 4xxx revenue, 6xxx expenses.
Keep codes stable once data is seeded. Bill.glAccount must be an expense (6xxx) code.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    type: str  # asset | liability | equity | revenue | expense
    recurring: bool = False  # revenue only: counts toward recurring revenue %
    cash: bool = False  # asset only: counts as cash for the cash flow statement


CHART = [
    # Assets
    Account("1000", "Operating cash", "asset", cash=True),
    Account("1100", "Payouts receivable", "asset"),
    Account("1200", "Prepaid expenses", "asset"),
    # Liabilities
    Account("2000", "Accounts payable", "liability"),
    Account("2100", "Credit card payable", "liability"),
    Account("2200", "Accrued payroll", "liability"),
    # Equity
    Account("3000", "Owner's equity", "equity"),
    Account("3100", "Owner distributions", "equity"),
    # Revenue
    Account("4100", "Advisory fees", "revenue", recurring=True),
    Account("4200", "Commissions", "revenue"),
    Account("4300", "Trails", "revenue", recurring=True),
    Account("4900", "Other income", "revenue"),
    # Expenses
    Account("6100", "Staff and payroll", "expense"),
    Account("6200", "Rent and occupancy", "expense"),
    Account("6300", "Technology", "expense"),
    Account("6400", "LPL platform fees", "expense"),
    Account("6500", "Marketing", "expense"),
    Account("6600", "Compliance and licensing", "expense"),
    Account("6700", "Travel and entertainment", "expense"),
    Account("6900", "Other expenses", "expense"),
]

ACCOUNTS = {a.code: a for a in CHART}

# Well-known codes the ledger posting and workflow code uses (C9).
CASH = "1000"
ACCOUNTS_PAYABLE = "2000"
CREDIT_CARD_PAYABLE = "2100"
DEFAULT_EXPENSE = "6900"
REVENUE_ACCOUNTS = {"advisory": "4100", "commission": "4200", "trail": "4300", "other": "4900"}


def get(code: str) -> Account:
    try:
        return ACCOUNTS[code]
    except KeyError:
        raise ValueError(f"Unknown account code {code!r}") from None


def is_valid(code) -> bool:
    return str(code) in ACCOUNTS


def is_expense(code) -> bool:
    return is_valid(code) and ACCOUNTS[str(code)].type == "expense"


def name(code) -> str:
    return ACCOUNTS[str(code)].name if is_valid(code) else "Unknown"


def kind(code) -> str:
    return ACCOUNTS[str(code)].type if is_valid(code) else "unknown"
