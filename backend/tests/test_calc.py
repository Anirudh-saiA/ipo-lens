from decimal import Decimal as D

import pytest

from app import calc
from app.models import ExtractedFigure


def test_ebitda_adds_back_finance_costs_and_depreciation() -> None:
    # BCSSL FY2026, RHP page 91
    assert calc.ebitda(D("407.88"), D("357.08"), D("126.01")) == D("890.97")


def test_adjusted_ebitda_removes_other_income() -> None:
    assert calc.adjusted_ebitda(D("890.97"), D("30.07")) == D("860.90")


def test_total_debt_is_borrowings_only() -> None:
    # Matches "Total Debt" 3,384.54 in the RHP ratio table, page 401
    assert calc.total_debt(D("522.89"), D("2861.65")) == D("3384.54")


def test_margin_pct() -> None:
    assert calc.margin_pct(D("305.39"), D("12668.18")).quantize(D("0.01")) == D("2.41")


def test_margin_handles_losses() -> None:
    assert calc.margin_pct(D("-50"), D("1000")) == D("-5")


def test_margin_refuses_zero_revenue() -> None:
    with pytest.raises(ZeroDivisionError):
        calc.margin_pct(D("1"), D("0"))


def test_return_on_average_equity() -> None:
    # Matches "Return on Equity Ratio" 29.85% for FY2026, page 401
    roe = calc.return_on_average_equity_pct(D("305.39"), D("830.47"), D("1215.81"))
    assert roe.quantize(D("0.01")) == D("29.85")


def test_return_on_average_equity_refuses_non_positive_equity() -> None:
    with pytest.raises(ZeroDivisionError):
        calc.return_on_average_equity_pct(D("10"), D("-100"), D("50"))


def test_return_on_net_worth() -> None:
    assert calc.return_on_net_worth_pct(D("50"), D("200")) == D("25")


def test_return_on_net_worth_refuses_negative_net_worth() -> None:
    with pytest.raises(ZeroDivisionError):
        calc.return_on_net_worth_pct(D("50"), D("-1"))


def test_debt_to_equity() -> None:
    # Matches 2.78 for FY2026, page 401
    assert calc.debt_to_equity(D("3384.54"), D("1215.81")).quantize(D("0.01")) == D("2.78")


def test_debt_to_equity_refuses_non_positive_equity() -> None:
    with pytest.raises(ZeroDivisionError):
        calc.debt_to_equity(D("100"), D("0"))


def _fig(fid: int, metric: str, period: str, value: str) -> ExtractedFigure:
    return ExtractedFigure(id=fid, metric=metric, period=period, value=D(value))


def _figures(*items: ExtractedFigure) -> dict[tuple[str, str], ExtractedFigure]:
    return {(f.metric, f.period): f for f in items}


def test_compute_period_links_inputs_and_dates_balance_metrics() -> None:
    figures = _figures(
        _fig(1, "profit_after_tax", "FY2026", "305.39"),
        _fig(2, "revenue_from_operations", "FY2026", "12668.18"),
        _fig(3, "total_equity", "as at 2026-03-31", "1215.81"),
        _fig(4, "total_equity", "as at 2025-03-31", "830.47"),
        _fig(5, "borrowings_non_current", "as at 2026-03-31", "522.89"),
        _fig(6, "borrowings_current", "as at 2026-03-31", "2861.65"),
    )
    results = {r.metric: r for r in calc.compute_period(figures, "FY2026")}

    assert [f.id for f in results["pat_margin_pct"].inputs] == [1, 2]
    assert results["return_on_equity_pct"].value == D("29.8483")
    assert results["debt_to_equity"].period == "as at 2026-03-31"
    assert results["debt_to_equity"].note is None
    # No profit before tax, so no EBITDA: missing inputs are skipped, never guessed
    assert "ebitda" not in results


def test_part_year_ratios_are_labelled_not_annualised() -> None:
    period = "3M ended 2026-06-30"
    figures = _figures(
        _fig(1, "profit_after_tax", period, "150.75"),
        _fig(2, "revenue_from_operations", period, "3970.80"),
    )
    (result,) = calc.compute_period(figures, period)
    assert result.metric == "pat_margin_pct"
    assert result.note == "Part-year period; not annualised."


def test_roe_needs_opening_equity() -> None:
    figures = _figures(
        _fig(1, "profit_after_tax", "FY2024", "211.38"),
        _fig(2, "total_equity", "as at 2024-03-31", "543.59"),
    )
    metrics = {r.metric for r in calc.compute_period(figures, "FY2024")}
    assert "return_on_equity_pct" not in metrics  # March 2023 equity is not in the RHP
    assert "return_on_net_worth_pct" in metrics
