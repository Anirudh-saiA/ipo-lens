from app.financials import Word
from app.risks import _outside_tables, categorise, cause, headings


def _line(top: float, text: str, x: float = 54.0) -> list[Word]:
    words: list[Word] = []
    for part in text.split():
        words.append([part, x, x + 6 * len(part), top])
        x += 6 * len(part) + 4
    return words


def test_headings_follow_the_number_sequence() -> None:
    page_30 = (
        # A cross-reference in the introduction must not start the sequence
        _line(10, "36. We have paid for an industry report used in this section.")
        + _line(30, "1. We depend on a single supplier for most of our raw material.")
        + _line(40, "Body text about the supplier.")
        + _line(60, "1. A numbered list inside the risk body, restarting at one.")
        + _line(80, "2. We have high debt and may not be able to")
        + _line(90, "service it.")
    )
    page_31 = _line(10, "4. 90.06% of our revenue comes from customers in two sectors.")
    found = headings([(30, page_30), (31, page_31)])
    assert [(h.number, h.page_no) for h in found] == [(1, 30), (2, 30), (4, 31)]
    assert found[1].text == "We have high debt and may not be able to service it."


def test_table_rows_are_ignored() -> None:
    words = _line(100, "7. Form CHG-1 filed late with additional fees.")
    assert _outside_tables(words, [[40.0, 90.0, 560.0, 200.0]]) == []
    assert _outside_tables(words, [[40.0, 300.0, 560.0, 400.0]]) == words


def test_category_ignores_the_standard_effects_clause() -> None:
    heading = (
        "We are substantially dependent on a single supplier, and any disruption could "
        "adversely affect our business, results of operations and financial condition."
    )
    assert cause(heading).startswith("We are substantially dependent on a single supplier")
    assert categorise(heading) == "operational"  # not 'financial' from the effects clause


def test_categories() -> None:
    assert categorise("We derived 73.54% of our revenue from our top ten customers.") == (
        "customer_concentration"
    )
    assert categorise("Our Promoters are involved in legal and regulatory proceedings.") == "legal"
    assert categorise("We have incurred significant indebtedness.") == "financial"
    assert categorise("Our trade name is shared with other group companies.") == "uncategorised"
