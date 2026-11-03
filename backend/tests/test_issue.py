"""Issue structure extraction, on rows shaped like the three RHPs' cover pages."""

from decimal import Decimal as D

from app.issue import (
    NOT_DISCLOSED,
    cover_facts,
    date_facts,
    proceeds_facts,
    seller_facts,
)

# Fusion CX RHP page 1: fresh issue plus offer for sale, amounts printed, shares [●]
FUSION_COVER: list[list[str | None]] = [
    ["Type", "Fresh Issue Size", "Offer for Sale", "Total Offer size", None, "Eligibility"],
    [
        "Fresh\nIssue and\nOffer for\nSale",
        "Up to [●] Equity\nShares of face\nvalue ₹ 1 each\naggregating up to ₹\n5,000.00 million",
        "Up to [●]\nEquity Shares\nof face value ₹ 1\neach\naggregating up\nto ₹ 2,020.00\nmillion",
        "Up to [●] Equity\nShares of face value\n₹ 1 each\naggregating up to ₹\n7,020.00 million",
        None,
        "The Offer is being made pursuant to Regulation 6(2)",
    ],
    ["DETAILS OF THE OFFER FOR SALE", None],
    ["Name of the Promoter Selling", None, "Type", None, "Number of Equity Shares Offered"],
    [
        "P N S Business Private Limited",
        None,
        "Promoter Selling\nShareholder",
        None,
        "Up to [●] Equity Shares aggregating up to ₹\n1,010.00 million",
        "0.13",
    ],
]


def by_field(facts: list) -> dict[str, tuple[str, D | None]]:  # type: ignore[type-arg]
    return {f.field: (f.value_text, f.value_number) for f in facts}


def test_cover_reads_fresh_issue_and_offer_for_sale() -> None:
    got = by_field(cover_facts(1, FUSION_COVER))
    assert got["fresh_issue_amount"] == ("5,000.00", D("5000.00"))
    assert got["offer_for_sale_amount"] == ("2,020.00", D("2020.00"))
    assert got["total_issue_amount"] == ("7,020.00", D("7020.00"))
    assert got["fresh_issue_shares"] == (NOT_DISCLOSED, None)  # [●] is never guessed


def test_cover_not_applicable_and_shares_only() -> None:
    # Jio Platforms RHP page 1: share count printed, amount [●], no offer for sale
    rows: list[list[str | None]] = [
        ["TYPE", None, "FRESH ISSUE\nSIZE", None, "", "OFFER FOR", "TOTAL ISSUE", "ELIGIBILITY"],
        [
            "Fresh Issue",
            None,
            "Up to\n270,000,000\nEquity Shares of\nface value of ₹10\n"
            "aggregating up to\n₹[●] million",
            None,
            "Not applicable",
            "Up to\n270,000,000\nEquity Shares aggregating up to\n₹[●] million",
            "The Issue is being made pursuant to Regulation 6(1)",
        ],
    ]
    got = by_field(cover_facts(1, rows))
    assert got["fresh_issue_shares"] == ("270,000,000", D("270000000"))
    assert got["fresh_issue_amount"] == (NOT_DISCLOSED, None)
    assert got["offer_for_sale_amount"] == ("Not applicable", D("0"))


def test_selling_shareholders() -> None:
    (fact,) = seller_facts(1, FUSION_COVER)
    assert (fact.label, fact.value_number, fact.unit) == (
        "P N S Business Private Limited",
        D("1010.00"),
        "INR million",
    )


def test_dates_in_same_cell_or_next_cell() -> None:
    rows: list[list[str | None]] = [
        # BCSSL page 4: label and date share a cell
        [
            "ANCHOR INVESTOR BIDDING DATE: Wednesday,\nOctober 28, 2026*",
            "BID / ISSUE OPENS ON#: Thursday, October\n29, 2026",
            None,
            "BID / ISSUE CLOSES ON#: Monday, November 02,\n2026**",
        ],
    ]
    got = by_field(date_facts(4, rows))
    assert got["anchor_bid_date"][0] == "2026-10-28"
    assert got["bid_open_date"][0] == "2026-10-29"
    assert got["bid_close_date"][0] == "2026-11-02"

    # Jio page 4: the date is in the next cell
    rows = [
        ["BID/ ISSUE OPENS ON", None, "", "WEDNESDAY,\nOCTOBER 21, 2026", "BID/ ISSUE CLOSES ON"]
    ]
    assert by_field(date_facts(4, rows))["bid_open_date"][0] == "2026-10-21"


def test_date_split_across_rows_is_not_guessed() -> None:
    # Fusion page 2 splits the anchor date over two rows: no year in this row, so no fact
    rows: list[list[str | None]] = [["ANCHOR INVESTOR BID/", "Tuesday,", "BID/OFFER\nOPENS ON"]]
    assert date_facts(2, rows) == []


def _line(top: float, *texts: str) -> list[list[str | float]]:
    words: list[list[str | float]] = []
    x = 60.0
    for text in texts:
        words.append([text, x, x + 6 * len(text), top])
        x += 6 * len(text) + 5
    return words


def test_proceeds_keep_wrapped_labels_and_stop_at_net_proceeds() -> None:
    # Jio Platforms RHP page 116: the object's label wraps above and below its amounts
    words = (
        _line(10, "Gross", "Proceeds", "*", "[●]")
        + _line(20, "S.", "No.", "Particulars", "Total", "estimated")
        + _line(30, "Prepayment,", "in", "full", "or", "in", "part,", "of", "outstanding")
        + _line(40, "1.", "275,000", "275,000")
        + _line(50, "borrowings", "availed", "by", "RJIL")
        + _line(60, "2.", "General", "corporate", "purposes*", "[●]", "[●]")
        + _line(70, "Net", "Proceeds", "[●]", "[●]")
        + _line(80, "Particulars", "Fiscal", "2027")
        + _line(90, "1.", "Something", "repeated", "100.00")
    )
    facts = proceeds_facts([(116, words, "(in ₹ million)")])
    assert [(f.label, f.value_number) for f in facts] == [
        ("Prepayment, in full or in part, of outstanding borrowings availed by RJIL", D("275000")),
        ("General corporate purposes", None),
    ]
    assert all(f.page_no == 116 and f.unit == "INR million" for f in facts)
