"""The word-position extractor, on a statement laid out like Jio Platforms' RHP page 76:
no ruling lines, a two-level header ('Three months periods ended' / 'Fiscal'), a label
that wraps around its numbers, and EPS values with a footnote asterisk."""

from decimal import Decimal as D

from app.financials import Word, extract_from_words

COLUMNS = [300.0, 350.0, 410.0, 470.0, 530.0]  # right edges of the five value columns


def w(text: str, x1: float, top: float) -> Word:
    return [text, x1 - 6.0 * len(text), x1, top]


def label(text: str, top: float) -> list[Word]:
    out: list[Word] = []
    x = 50.0
    for part in text.split():
        out.append([part, x, x + 6.0 * len(part), top])
        x += 6.0 * len(part) + 4
    return out


def values(cells: list[str], top: float) -> list[Word]:
    return [w(c, x1, top) for c, x1 in zip(cells, COLUMNS, strict=True)]


def jio_like_page() -> list[Word]:
    words: list[Word] = []
    words += label("Summary of restated consolidated statement of profit and loss", 10)
    words += [w("Three", 290, 30), w("months", 330, 30), w("Fiscal", 470, 34)]
    # A small gap between "June" and "30," as in real PDFs (touching pieces get joined)
    words += [w("June", 280, 50), w("30,", 300, 50), w("June", 330, 50), w("30,", 350, 50)]
    words += [w("2026", 410, 55), w("2025", 470, 55), w("2024", 530, 55)]
    words += [w("2026", 300, 60), w("2025", 350, 60)]
    words += label("Income", 80)
    words += label("Revenue from Operations", 90) + values(
        ["391,729", "350,323", "1,468,853", "1,282,184", "1,095,581"], 90
    )
    words += label("Profit Before Share of Profit/ (Loss) of Associate/", 100)
    words += values(["104,271", "95,514", "403,531", "351,273", "288,080"], 106)
    words += label("Joint Venture and Tax", 112)
    words += label("Profit After Tax", 120) + values(
        ["77,641", "71,104", "300,527", "261,203", "214,340"], 120
    )
    words += label("Profit for the period/ year", 130) + values(
        ["77,641", "71,101", "300,491", "261,090", "214,232"], 130
    )
    words += label("Basic (in Rupees)", 140) + values(
        ["8.69*", "7.96*", "33.63", "29.21", "23.96"], 140
    )
    return words


def figures() -> dict[tuple[str, str], D]:
    found = extract_from_words(jio_like_page(), "profit_and_loss", "INR million", 76)
    return {(f.metric, f.period.label): f.value for f in found}


def test_columns_get_their_own_dates() -> None:
    got = figures()
    assert got[("revenue_from_operations", "3M ended 2026-06-30")] == D("391729")
    assert got[("revenue_from_operations", "3M ended 2025-06-30")] == D("350323")
    assert got[("revenue_from_operations", "FY2026")] == D("1468853")
    assert got[("revenue_from_operations", "FY2024")] == D("1095581")


def test_wrapped_label_keeps_its_values() -> None:
    assert figures()[("profit_before_tax", "FY2026")] == D("403531")


def test_profit_for_the_year_beats_profit_after_tax() -> None:
    # "Profit After Tax" comes first on the page but is before the share of associates
    assert figures()[("profit_after_tax", "FY2026")] == D("300491")


def test_footnote_asterisk_is_not_part_of_the_value() -> None:
    assert figures()[("eps_basic", "3M ended 2026-06-30")] == D("8.69")


def test_bare_years_without_fiscal_are_not_guessed() -> None:
    page = [word for word in jio_like_page() if word[0] != "Fiscal"]
    assert extract_from_words(page, "profit_and_loss", "INR million", 76) == []


def test_every_figure_cites_its_page_and_line() -> None:
    found = extract_from_words(jio_like_page(), "profit_and_loss", "INR million", 76)
    assert found and all(f.page_no == 76 and f.table_ref.startswith("page 76 line") for f in found)


def _header(*words: tuple[str, float, float, float]) -> list[list[Word]]:
    from app.financials import _lines

    return _lines([[t, x0, x1, top] for t, x0, x1, top in words])


def test_header_with_ranges_out_of_reading_order() -> None:
    # Fusion CX RHP page 68: reads "April 1, 2026 to ended March 31, ... June 30, 2026
    # 2026 2025 2024" in text order; positions keep each date with its column
    from app.financials import periods_from_header

    spans = [(301.0, 332.0), (376.0, 408.0), (447.0, 484.0), (526.0, 556.0)]
    header = _header(
        ("April", 264, 285, 10),
        ("1,", 287, 294, 10),
        ("2026", 296, 314, 10),
        ("to", 316, 324, 10),
        ("ended", 340, 363, 10),
        ("March", 365, 391, 10),
        ("31,", 394, 405, 10),
        ("ended", 417, 440, 10),
        ("March", 442, 468, 10),
        ("31,", 470, 481, 10),
        ("ended", 491, 514, 10),
        ("March", 516, 542, 10),
        ("31,", 544, 556, 10),
        ("June", 268, 287, 20),
        ("30,", 289, 300, 20),
        ("2026", 302, 320, 20),
        ("2026", 364, 382, 20),
        ("2025", 440, 458, 20),
        ("2024", 514, 532, 20),
    )
    assert [p.label for p in periods_from_header(header, spans, "cash_flow")] == [
        "3M ended 2026-06-30",
        "FY2026",
        "FY2025",
        "FY2024",
    ]


def test_header_rejoins_split_day_and_month() -> None:
    # BCSSL RHP pages 90 and 91 print "3 1, 2024" and "M arch" as separate pieces
    from app.financials import periods_from_header

    spans = [(441.0, 476.0), (505.0, 540.0)]
    header = _header(
        ("March", 447, 476, 10),
        ("March", 511, 540, 10),
        ("31,", 423, 435, 20),
        ("2025", 438, 458, 20),
        ("3", 487, 492, 20),
        ("1,", 492, 499, 20),
        ("2024", 502, 522, 20),
    )
    assert [p.label for p in periods_from_header(header, spans, "balance_sheet")] == [
        "as at 2025-03-31",
        "as at 2024-03-31",
    ]
