from datetime import date
from decimal import Decimal as D

import pytest

from app.financials import (
    Period,
    extract_from_table,
    find_periods,
    find_unit,
    normalise_label,
    parse_number,
    statement_type,
)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1,234.56", D("1234.56")),
        ("(218.38)", D("-218.38")),
        ("2999.70", D("2999.70")),
        ("29.85%", D("29.85")),
        ("3 1", D("31")),
        ("-", None),
        ("--", None),
        ("", None),
        ("June 30, 2026", None),
    ],
)
def test_parse_number(cell: str, expected: D | None) -> None:
    assert parse_number(cell) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a) Revenue from operations", "revenue from operations"),
        ("T otal Income (A)", "total income (a)"),
        ("ii) Cash and cash equivalents", "cash and cash equivalents"),
        ("(a) Equity share capital", "equity share capital"),
        ("Depreciation and amortisation\nexpense", "depreciation and amortisation expense"),
    ],
)
def test_normalise_label(raw: str, expected: str) -> None:
    assert normalise_label(raw) == expected


def test_periods_from_split_header() -> None:
    # Page 92: months and years on different lines
    header = "June 30, 2026 March 31, March 31, March 31,\nParticulars\n2026 2025 2024"
    assert [p.label for p in find_periods(header, "cash_flow")] == [
        "3M ended 2026-06-30",
        "FY2026",
        "FY2025",
        "FY2024",
    ]


def test_periods_rejoin_split_month_and_use_month_end() -> None:
    # Page 91 prints "M arch"; page 90 prints the day apart from the month
    assert find_periods("June 30, 2026 March 31, 2026 M arch 31, 2024", "profit_and_loss")[
        -1
    ] == Period(date(2024, 3, 31), 12)
    balance = find_periods("As at June As at March\nNo. 30, 2026 3 1, 2026", "balance_sheet")
    assert [p.label for p in balance] == ["as at 2026-06-30", "as at 2026-03-31"]


def test_periods_refuse_mismatched_header() -> None:
    assert find_periods("March 31, 2026 March 31", "profit_and_loss") == []


def test_unit_and_statement_detection() -> None:
    assert find_unit("RESTATED CASH FLOW STATEMENT\n(₹ in Million)") == "INR million"
    assert find_unit("(Rs. in lakhs)") == "INR lakh"
    assert find_unit("no unit here") is None
    assert statement_type("RESTATED STATEMENT OF PROFIT AND LOSS\n(₹ in million)") == (
        "profit_and_loss"
    )
    assert statement_type("CERTAIN ITEMS IN THE RESTATED STATEMENT OF ASSETS") is None


PERIODS = [Period(date(2026, 3, 31), 12), Period(date(2025, 3, 31), 12)]


def test_extract_handles_offset_columns_and_dashes() -> None:
    rows: list[list[str | None]] = [
        ["Particulars", "", "March 31, 2026", None, "March 31, 2025", None],
        ["a) Revenue from operations", "12,668.18", None, "10,557.07", None, None],
        ["b) Tax impact", "-", None, "(0.13)", None, None],
        ["Profit for the year E=(C-D)", "305.39", None, "286.72", None, None],
        ["Basic (₹)", "7.64", None, "7.24", None, None],
    ]
    figures = extract_from_table(rows, "profit_and_loss", PERIODS, "INR million", 91, 0)
    got = {(f.metric, f.period.label): (f.value, f.unit) for f in figures}
    assert got == {
        ("revenue_from_operations", "FY2026"): (D("12668.18"), "INR million"),
        ("revenue_from_operations", "FY2025"): (D("10557.07"), "INR million"),
        ("profit_after_tax", "FY2026"): (D("305.39"), "INR million"),
        ("profit_after_tax", "FY2025"): (D("286.72"), "INR million"),
        ("eps_basic", "FY2026"): (D("7.64"), "INR per share"),
        ("eps_basic", "FY2025"): (D("7.24"), "INR per share"),
    }
    assert all(f.page_no == 91 for f in figures)


def test_extract_skips_rows_with_wrong_number_of_values() -> None:
    rows: list[list[str | None]] = [["Revenue from operations", "12,668.18", None]]
    assert extract_from_table(rows, "profit_and_loss", PERIODS, "INR million", 1, 0) == []


def test_extract_tells_current_from_non_current_borrowings() -> None:
    balance = [Period(date(2026, 3, 31), 0), Period(date(2025, 3, 31), 0)]
    rows: list[list[str | None]] = [
        ["II", "Non-Current Liabilities", "", ""],
        ["", "i) Borrowings", "522.89", "392.25"],
        ["", "III", "Current liabilities", ""],
        ["", "i) Borrowings", "2,861.65", "2,377.36"],
    ]
    figures = extract_from_table(rows, "balance_sheet", balance, "INR million", 90, 0)
    got = {(f.metric, f.period.label): f.value for f in figures}
    assert got[("borrowings_non_current", "as at 2026-03-31")] == D("522.89")
    assert got[("borrowings_current", "as at 2026-03-31")] == D("2861.65")
