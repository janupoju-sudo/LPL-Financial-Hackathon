import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal, Mapping, NotRequired, TypedDict


class RevenueLine(TypedDict):
    id: str
    source: Literal["advisory", "commission", "trail"]
    label: str
    actual: int
    docId: str
    ref: NotRequired[str]


_AMOUNT_HEADERS = {
    "actual",
    "amount",
    "amountpaid",
    "commissionamount",
    "netamount",
    "payout",
    "payment",
}
_LABEL_HEADERS = {
    "description",
    "detail",
    "income",
    "product",
    "revenuetype",
    "transaction",
    "type",
}
_SOURCE_HEADERS = {"category", "revenuetype", "source", "type"}
_REF_HEADERS = {
    "accountnumber",
    "contract",
    "contractnumber",
    "productnumber",
    "productid",
    "policy",
    "policynumber",
    "ref",
    "reference",
}
_ID_HEADERS = {"lineid", "payoutid", "transactionid"}


def parse_payout_lines(
    textract_response: Mapping[str, Any], doc_id: str
) -> list[RevenueLine]:
    """Convert Textract TABLES output for a payout statement to revenue lines."""
    if not doc_id.strip():
        raise ValueError("doc_id must not be empty")

    blocks = {
        block["Id"]: block
        for block in textract_response.get("Blocks", [])
        if isinstance(block, Mapping) and isinstance(block.get("Id"), str)
    }
    result: list[RevenueLine] = []
    line_number = 0

    for table in blocks.values():
        if table.get("BlockType") != "TABLE":
            continue

        rows = _table_rows(table, blocks)
        if not rows:
            continue

        header_row = rows[0]
        headers = {
            column: _normalize_header(value)
            for column, value in header_row.items()
        }
        amount_column = _find_column(headers, _AMOUNT_HEADERS)
        label_column = _find_column(headers, _LABEL_HEADERS)
        if amount_column is None or label_column is None:
            continue

        for row in rows[1:]:
            values = {headers[column]: value for column, value in row.items()}
            label = row.get(label_column, "").strip()
            if not label or _normalize_header(label) in {"total", "grandtotal"}:
                continue
            if _normalize_header(label) in set(headers.values()):
                continue

            amount_text = row.get(amount_column, "").strip()
            if not amount_text:
                continue

            source = _revenue_source(
                _column_value(values, headers, _SOURCE_HEADERS) or label
            )
            actual = _amount_to_cents(amount_text)
            ref = _column_value(values, headers, _REF_HEADERS)
            if not ref:
                ref = _reference_from_label(label)

            line_number += 1
            line_id = _column_value(values, headers, _ID_HEADERS)
            revenue_line: RevenueLine = {
                "id": line_id or f"{doc_id}-line-{line_number}",
                "source": source,
                "label": label,
                "actual": actual,
                "docId": doc_id,
            }
            if ref:
                revenue_line["ref"] = ref
            result.append(revenue_line)

    return result


def _table_rows(
    table: Mapping[str, Any], blocks: Mapping[str, Mapping[str, Any]]
) -> list[dict[int, str]]:
    rows: dict[int, dict[int, str]] = {}
    for relationship in table.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue
        for cell_id in relationship.get("Ids", []):
            cell = blocks.get(cell_id)
            if not cell or cell.get("BlockType") != "CELL":
                continue
            row_index = cell.get("RowIndex")
            column_index = cell.get("ColumnIndex")
            if not isinstance(row_index, int) or not isinstance(column_index, int):
                raise ValueError("Textract CELL is missing row or column index")
            rows.setdefault(row_index, {})[column_index] = _cell_text(cell, blocks)
    return [rows[index] for index in sorted(rows)]


def _cell_text(
    cell: Mapping[str, Any], blocks: Mapping[str, Mapping[str, Any]]
) -> str:
    words: list[str] = []
    for relationship in cell.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue
        for child_id in relationship.get("Ids", []):
            child = blocks.get(child_id)
            if not child:
                continue
            if child.get("BlockType") == "WORD":
                text = child.get("Text")
                if isinstance(text, str):
                    words.append(text)
            elif child.get("BlockType") == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    words.append("SELECTED")
    return " ".join(words)


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _find_column(headers: Mapping[int, str], names: set[str]) -> int | None:
    return next((column for column, name in headers.items() if name in names), None)


def _column_value(
    values: Mapping[str, str],
    headers: Mapping[int, str],
    names: set[str],
) -> str:
    for column, header in headers.items():
        if header in names:
            value = values.get(header, "").strip()
            if value:
                return value
    return ""


def _revenue_source(value: str) -> Literal["advisory", "commission", "trail"]:
    normalized = value.casefold()
    if "trail" in normalized:
        return "trail"
    if "advisory" in normalized:
        return "advisory"
    if "commission" in normalized:
        return "commission"
    raise ValueError(f"Unrecognized payout revenue source: {value!r}")


def _amount_to_cents(value: str) -> int:
    cleaned = value.strip().replace(",", "").replace("$", "")
    is_negative = cleaned.startswith("(") and cleaned.endswith(")")
    if is_negative:
        cleaned = cleaned[1:-1].strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid payout amount: {value!r}") from exc
    cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return -cents if is_negative else cents


def _reference_from_label(label: str) -> str:
    match = re.search(
        r"(?:contract|product|policy|account|#)\s*(?:no\.?\s*)?[#…]*\s*(\d+)",
        label,
        re.I,
    )
    if match:
        return match.group(1)
    match = re.search(r"(?<!\d)(\d{3,})(?!\d)\s*$", label)
    if match:
        return match.group(1)
    return ""
