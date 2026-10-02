import unittest

from ingest.payout_parser import parse_payout_lines


def _word(block_id: str, text: str) -> dict[str, str]:
    return {"BlockType": "WORD", "Id": block_id, "Text": text}


def _cell(
    block_id: str, row: int, column: int, word_ids: list[str]
) -> dict[str, object]:
    return {
        "BlockType": "CELL",
        "Id": block_id,
        "RowIndex": row,
        "ColumnIndex": column,
        "Relationships": [{"Type": "CHILD", "Ids": word_ids}],
    }


def _textract_table(rows: list[list[str]]) -> dict[str, list[dict[str, object]]]:
    blocks: list[dict[str, object]] = [
        {
            "BlockType": "TABLE",
            "Id": "table",
            "Relationships": [
                {
                    "Type": "CHILD",
                    "Ids": [
                        f"cell-{row}-{column}"
                        for row in range(1, len(rows) + 1)
                        for column in range(1, len(rows[0]) + 1)
                    ],
                }
            ],
        }
    ]
    for row_index, row_values in enumerate(rows, start=1):
        for column_index, text in enumerate(row_values, start=1):
            word_id = f"word-{row_index}-{column_index}"
            blocks.append(_word(word_id, text))
            blocks.append(
                _cell(
                    f"cell-{row_index}-{column_index}",
                    row_index,
                    column_index,
                    [word_id],
                )
            )
    return {"Blocks": blocks}


class ParsePayoutLinesTests(unittest.TestCase):
    def test_maps_textract_rows_to_revenue_lines_in_cents(self) -> None:
        self.assertEqual(
            parse_payout_lines(
                _textract_table(
                    [
                        ["Description", "Amount"],
                        ["VA trail 4471", "$2,478.00"],
                    ]
                ),
                "d3",
            ),
            [
                {
                    "id": "d3-line-1",
                    "source": "trail",
                    "ref": "4471",
                    "label": "VA trail 4471",
                    "actual": 247800,
                    "docId": "d3",
                }
            ],
        )

    def test_parses_parenthesized_negative_amount_as_cents(self) -> None:
        lines = parse_payout_lines(
            _textract_table(
                [
                    ["Description", "Amount"],
                    ["Advisory fee adjustment", "($10.25)"],
                ]
            ),
            "d3",
        )
        self.assertEqual(lines[0]["actual"], -1025)

    def test_rejects_unrecognized_revenue_source(self) -> None:
        response = {
            "Blocks": [
                {
                    "BlockType": "TABLE",
                    "Id": "table",
                    "Relationships": [
                        {"Type": "CHILD", "Ids": ["h1", "h2", "r1", "r2"]}
                    ],
                },
                _cell("h1", 1, 1, ["description"]),
                _word("description", "Description"),
                _cell("h2", 1, 2, ["amount"]),
                _word("amount", "Amount"),
                _cell("r1", 2, 1, ["label"]),
                _word("label", "Miscellaneous income"),
                _cell("r2", 2, 2, ["value"]),
                _word("value", "$10.00"),
            ]
        }
        with self.assertRaisesRegex(ValueError, "Unrecognized payout revenue source"):
            parse_payout_lines(response, "d3")

    def test_preserves_explicit_other_revenue_source(self) -> None:
        lines = parse_payout_lines(
            _textract_table(
                [
                    ["Type", "Description", "Amount"],
                    ["Other", "Other income", "$12.34"],
                ]
            ),
            "d4",
        )
        self.assertEqual(lines[0]["source"], "other")
        self.assertEqual(lines[0]["label"], "Other income")
        self.assertEqual(lines[0]["actual"], 1234)


if __name__ == "__main__":
    unittest.main()
