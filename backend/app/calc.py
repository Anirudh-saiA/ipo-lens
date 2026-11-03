"""Ratios computed in Python from reported figures (hard rule 3: the LLM never does arithmetic).

Each formula is a plain function over Decimals so it can be unit tested. compute_document()
looks up the inputs for each period, stores the result with the formula and the ids of the
figures it used, and skips (never guesses) a metric whose inputs are missing.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, ExtractedFigure

HUNDRED = Decimal(100)
PLACES = Decimal("0.0001")


def ebitda(profit_before_tax: Decimal, finance_costs: Decimal, depreciation: Decimal) -> Decimal:
    return profit_before_tax + finance_costs + depreciation


def adjusted_ebitda(ebitda_value: Decimal, other_income: Decimal) -> Decimal:
    """EBITDA without other income, as the BCSSL RHP defines Adjusted EBITDA."""
    return ebitda_value - other_income


def total_debt(non_current_borrowings: Decimal, current_borrowings: Decimal) -> Decimal:
    """Borrowings only; lease liabilities excluded, matching the RHP's ratio note."""
    return non_current_borrowings + current_borrowings


def margin_pct(numerator: Decimal, revenue: Decimal) -> Decimal:
    if revenue == 0:
        raise ZeroDivisionError("revenue is zero")
    return numerator / revenue * HUNDRED


def return_on_average_equity_pct(
    profit: Decimal, opening_equity: Decimal, closing_equity: Decimal
) -> Decimal:
    average = (opening_equity + closing_equity) / 2
    if average <= 0:
        raise ZeroDivisionError("average equity is not positive")
    return profit / average * HUNDRED


def return_on_net_worth_pct(profit: Decimal, closing_net_worth: Decimal) -> Decimal:
    if closing_net_worth <= 0:
        raise ZeroDivisionError("net worth is not positive")
    return profit / closing_net_worth * HUNDRED


def debt_to_equity(debt: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        raise ZeroDivisionError("equity is not positive")
    return debt / equity


# --- wiring figures to formulas -------------------------------------------------


@dataclass
class Result:
    metric: str
    period: str
    value: Decimal
    unit: str
    formula: str
    inputs: list[ExtractedFigure]
    note: str | None


def _balance_date(period: str) -> str | None:
    """Flow period -> the balance-sheet date it ends on ('FY2026' -> 'as at 2026-03-31')."""
    if period.startswith("FY"):
        return f"as at {period[2:]}-03-31"
    if " ended " in period:
        return f"as at {period.split(' ended ')[1]}"
    return None


def _previous_year_end(period: str) -> str | None:
    if period.startswith("FY"):
        return f"as at {int(period[2:]) - 1}-03-31"
    return None


def compute_period(figures: dict[tuple[str, str], ExtractedFigure], period: str) -> list[Result]:
    def get(metric: str, p: str | None = period) -> ExtractedFigure | None:
        return figures.get((metric, p)) if p else None

    note = None if period.startswith("FY") else "Part-year period; not annualised."
    results: list[Result] = []

    def add(
        metric: str,
        unit: str,
        formula: str,
        fn: Callable[..., Decimal],
        inputs: list[ExtractedFigure | None],
        value_inputs: list[Decimal] | None = None,
        point_in_time: bool = False,
    ) -> Decimal | None:
        if any(i is None for i in inputs):
            return None  # missing input: say nothing rather than guess
        present = [i for i in inputs if i is not None]
        try:
            value = fn(*(value_inputs if value_inputs is not None else [i.value for i in present]))
        except ZeroDivisionError:
            return None
        # Balance-sheet metrics are dated "as at" and are never annualised
        label = bs if point_in_time and bs else period
        results.append(
            Result(
                metric,
                label,
                value.quantize(PLACES),
                unit,
                formula,
                present,
                None if point_in_time else note,
            )
        )
        return value

    pbt, fin, dep, oth = (
        get("profit_before_tax"),
        get("finance_costs"),
        get("depreciation_amortisation"),
        get("other_income"),
    )
    rev, pat = get("revenue_from_operations"), get("profit_after_tax")
    bs = _balance_date(period)
    eq_close, eq_open = get("total_equity", bs), get("total_equity", _previous_year_end(period))
    b_nc, b_c = get("borrowings_non_current", bs), get("borrowings_current", bs)

    e = add(
        "ebitda",
        "INR million",
        "profit_before_tax + finance_costs + depreciation_amortisation",
        ebitda,
        [pbt, fin, dep],
    )
    if e is not None and oth is not None:
        add(
            "adjusted_ebitda",
            "INR million",
            "ebitda - other_income",
            adjusted_ebitda,
            [pbt, fin, dep, oth],
            [e, oth.value],
        )
        adj = e - oth.value
        add(
            "adjusted_ebitda_margin_pct",
            "%",
            "(ebitda - other_income) / revenue_from_operations * 100",
            margin_pct,
            [pbt, fin, dep, oth, rev],
            [adj, rev.value] if rev else None,
        )
    if e is not None:
        add(
            "ebitda_margin_pct",
            "%",
            "ebitda / revenue_from_operations * 100",
            margin_pct,
            [pbt, fin, dep, rev],
            [e, rev.value] if rev else None,
        )
    add(
        "pat_margin_pct",
        "%",
        "profit_after_tax / revenue_from_operations * 100",
        margin_pct,
        [pat, rev],
    )
    add(
        "return_on_net_worth_pct",
        "%",
        "profit_after_tax / closing total_equity * 100",
        return_on_net_worth_pct,
        [pat, eq_close],
    )
    add(
        "return_on_equity_pct",
        "%",
        "profit_after_tax / average(opening, closing total_equity) * 100",
        return_on_average_equity_pct,
        [pat, eq_open, eq_close],
    )
    d = add(
        "total_debt",
        "INR million",
        "borrowings_non_current + borrowings_current",
        total_debt,
        [b_nc, b_c],
        point_in_time=True,
    )
    if d is not None:
        add(
            "debt_to_equity",
            "x",
            "total_debt / total_equity",
            debt_to_equity,
            [b_nc, b_c, eq_close],
            [d, eq_close.value] if eq_close else None,
            point_in_time=True,
        )
    return results


def compute_document(session: Session, document_id: int) -> list[CalculatedMetric]:
    """Recompute every metric for a document from its stored figures."""
    rows = session.scalars(
        select(ExtractedFigure).where(ExtractedFigure.document_id == document_id)
    )
    figures: dict[tuple[str, str], ExtractedFigure] = {}
    for row in rows:
        figures.setdefault((row.metric, row.period), row)
    flow_periods = sorted({p for _, p in figures if not p.startswith("as at")})

    session.execute(delete(CalculatedMetric).where(CalculatedMetric.document_id == document_id))
    stored = []
    for period in flow_periods:
        for r in compute_period(figures, period):
            metric = CalculatedMetric(
                document_id=document_id,
                metric=r.metric,
                period=r.period,
                unit=r.unit,
                formula=r.formula,
                note=r.note,
                input_figure_ids=[f.id for f in r.inputs],
                value=r.value,
            )
            session.add(metric)
            stored.append(metric)
    session.commit()
    return stored
