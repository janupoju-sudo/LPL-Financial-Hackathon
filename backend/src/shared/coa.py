"""Chart of accounts for an independent advisor practice (task D1, shared with C).

Codes follow the usual small-business ranges:
1xxx assets, 2xxx liabilities, 3xxx equity, 4xxx revenue, 6xxx expenses.
Keep codes stable once data is seeded. Bill.glAccount must be an expense (6xxx) code.

Expenses are a general ledger with subledgers: each category (6700 Travel and entertainment)
has sub-accounts (6710 Airfare, 6720 Car rides, ...). Invoices and card charges are coded to the
most specific sub-account; the P&L shows each category's total with its breakdown. A posting made
straight to a category code still works and shows as that category's "General" line.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    type: str  # asset | liability | equity | revenue | expense
    recurring: bool = False  # revenue only: counts toward recurring revenue %
    cash: bool = False  # asset only: counts as cash for the cash flow statement
    parent: str | None = None  # expense sub-accounts: the category they roll up into


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
    # Expenses: categories, each followed by its sub-accounts
    Account("6100", "Staff and payroll", "expense"),
    Account("6110", "Salaries and wages", "expense", parent="6100"),
    Account("6120", "Payroll taxes", "expense", parent="6100"),
    Account("6130", "Benefits", "expense", parent="6100"),
    Account("6200", "Rent and occupancy", "expense"),
    Account("6210", "Office rent", "expense", parent="6200"),
    Account("6220", "Utilities", "expense", parent="6200"),
    Account("6300", "Technology", "expense"),
    Account("6310", "Software subscriptions", "expense", parent="6300"),
    Account("6320", "Research and market data", "expense", parent="6300"),
    Account("6330", "Hardware and devices", "expense", parent="6300"),
    Account("6400", "LPL platform fees", "expense"),
    Account("6410", "Platform and admin fees", "expense", parent="6400"),
    Account("6420", "Technology and data fees", "expense", parent="6400"),
    Account("6500", "Marketing", "expense"),
    Account("6510", "Client events", "expense", parent="6500"),
    Account("6520", "Advertising and digital", "expense", parent="6500"),
    Account("6530", "Seminars and sponsorships", "expense", parent="6500"),
    Account("6600", "Compliance and licensing", "expense"),
    Account("6610", "Licensing and registration", "expense", parent="6600"),
    Account("6620", "E&O insurance", "expense", parent="6600"),
    Account("6630", "Compliance consultants", "expense", parent="6600"),
    Account("6700", "Travel and entertainment", "expense"),
    Account("6710", "Airfare", "expense", parent="6700"),
    Account("6720", "Car rides", "expense", parent="6700"),
    Account("6730", "Ground transportation", "expense", parent="6700"),
    Account("6740", "Parking", "expense", parent="6700"),
    Account("6750", "Lodging", "expense", parent="6700"),
    Account("6760", "Meals and entertainment", "expense", parent="6700"),
    Account("6900", "Other expenses", "expense"),
    Account("6910", "Office supplies", "expense", parent="6900"),
    Account("6920", "Bank and card fees", "expense", parent="6900"),
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


def category(code) -> str:
    """The category an expense rolls up into: 6740 -> 6700. Categories return themselves."""
    acct = ACCOUNTS.get(str(code))
    return acct.parent if acct and acct.parent else str(code)


def subaccounts(category_code: str) -> list[Account]:
    return [a for a in CHART if a.parent == category_code]


def expense_menu() -> str:
    """The expense chart as indented text, for AI prompts: categories with their sub-accounts."""
    rows = []
    for a in CHART:
        if a.type == "expense" and not a.parent:
            rows.append(f"{a.code} {a.name}")
            rows += [f"  {c.code} {c.name}" for c in subaccounts(a.code)]
    return "\n".join(rows)
