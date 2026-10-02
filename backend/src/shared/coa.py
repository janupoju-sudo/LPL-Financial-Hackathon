"""Chart of accounts for an independent advisor practice (agreed with Financials / role D).

Keep codes stable once data is seeded. Bill.glAccount must be an expense (6xxx) code.
"""
ACCOUNTS = {
    "1000": ("Operating cash", "asset"),
    "1100": ("Payouts receivable", "asset"),
    "1200": ("Prepaid expenses", "asset"),
    "2000": ("Accounts payable", "liability"),
    "2100": ("Credit card payable", "liability"),
    "2200": ("Accrued payroll", "liability"),
    "3000": ("Owner's equity", "equity"),
    "3100": ("Owner distributions", "equity"),
    "4100": ("Advisory fees", "revenue"),
    "4200": ("Commissions", "revenue"),
    "4300": ("Trails", "revenue"),
    "4900": ("Other income", "revenue"),
    "6100": ("Staff and payroll", "expense"),
    "6200": ("Rent and occupancy", "expense"),
    "6300": ("Technology", "expense"),
    "6400": ("LPL platform fees", "expense"),
    "6500": ("Marketing", "expense"),
    "6600": ("Compliance and licensing", "expense"),
    "6700": ("Travel and entertainment", "expense"),
    "6900": ("Other expenses", "expense"),
}

CASH = "1000"
ACCOUNTS_PAYABLE = "2000"
CREDIT_CARD_PAYABLE = "2100"
DEFAULT_EXPENSE = "6900"
REVENUE_ACCOUNTS = {"advisory": "4100", "commission": "4200", "trail": "4300", "other": "4900"}


def is_valid(code) -> bool:
    return str(code) in ACCOUNTS


def is_expense(code) -> bool:
    return kind(code) == "expense"


def name(code) -> str:
    return ACCOUNTS.get(str(code), ("Unknown", ""))[0]


def kind(code) -> str:
    return ACCOUNTS.get(str(code), ("", "unknown"))[1]
