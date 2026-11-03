"""Answer questions about figures and dates from verified data, not from a language model.

A small model picked the wrong line or period from a correct page in 5 of 22 test
questions (profit before tax for profit, a quarter for the year). So when a question asks
for a figure or a date IPO Lens has extracted and checked, the answer is read straight from
the database, with its page. If the figure is not in the data, the answer is "not enough
evidence"; the question is never handed to the model to guess.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, Document, ExtractedFigure, IssueFact

# (key, source, display name, patterns). First match wins, so specific phrases come first.
# source: "figure" (reported), "metric" (calculated in Python), "fact" (issue structure)
INTENTS: list[tuple[str, str, str, re.Pattern[str]]] = [
    (
        "profit_before_tax",
        "figure",
        "Profit before tax",
        re.compile(r"\b(profit|loss) before tax\b|\bpbt\b", re.I),
    ),
    (
        "adjusted_ebitda_margin_pct",
        "metric",
        "Adjusted EBITDA margin",
        re.compile(r"adjusted ebitda margin", re.I),
    ),
    ("ebitda_margin_pct", "metric", "EBITDA margin", re.compile(r"ebitda margin", re.I)),
    ("adjusted_ebitda", "metric", "Adjusted EBITDA", re.compile(r"adjusted ebitda", re.I)),
    ("ebitda", "metric", "EBITDA", re.compile(r"\bebitda\b", re.I)),
    (
        "pat_margin_pct",
        "metric",
        "PAT margin",
        re.compile(r"\b(pat|net profit|profit) margin\b", re.I),
    ),
    (
        "return_on_equity_pct",
        "metric",
        "Return on equity",
        re.compile(r"\broe\b|return on equity", re.I),
    ),
    (
        "return_on_net_worth_pct",
        "metric",
        "Return on net worth",
        re.compile(r"\bronw\b|return on net ?worth", re.I),
    ),
    (
        "debt_to_equity",
        "metric",
        "Debt to equity (borrowings)",
        re.compile(r"debt[- ]to[- ]equity|\bd/e\b", re.I),
    ),
    (
        "total_debt",
        "metric",
        "Total debt (borrowings)",
        re.compile(r"\b(total )?debt\b|\bborrowings\b", re.I),
    ),
    (
        "net_cash_from_operating_activities",
        "figure",
        "Net cash from operating activities",
        re.compile(r"operating (activities|cash ?flow)|cash flow from operations|\bocf\b", re.I),
    ),
    ("eps_basic", "figure", "Basic EPS", re.compile(r"\beps\b|earnings per share", re.I)),
    ("total_income", "figure", "Total income", re.compile(r"\btotal income\b", re.I)),
    ("other_income", "figure", "Other income", re.compile(r"\bother income\b", re.I)),
    (
        "finance_costs",
        "figure",
        "Finance costs",
        re.compile(r"\bfinance costs?\b|interest (cost|expense)", re.I),
    ),
    (
        "depreciation_amortisation",
        "figure",
        "Depreciation and amortisation",
        re.compile(r"\bdepreciation\b", re.I),
    ),
    ("total_assets", "figure", "Total assets", re.compile(r"\btotal assets\b", re.I)),
    (
        "cash_and_cash_equivalents",
        "figure",
        "Cash and cash equivalents",
        re.compile(r"\bcash and cash equivalents\b|\bcash balance\b", re.I),
    ),
    ("total_equity", "figure", "Total equity", re.compile(r"\b(total equity|net ?worth)\b", re.I)),
    (
        "profit_after_tax",
        "figure",
        "Profit after tax",
        re.compile(r"\bprofit\b|\bpat\b|\bnet (income|loss)\b|\bloss for the\b|\bearnings\b", re.I),
    ),
    (
        "revenue_from_operations",
        "figure",
        "Revenue from operations",
        re.compile(r"\brevenue\b|\bsales\b|\bturnover\b", re.I),
    ),
    ("price_band", "fact", "Price band", re.compile(r"price band|issue price|offer price", re.I)),
    (
        "bid_lot",
        "fact",
        "Minimum bid (lot)",
        re.compile(r"\blot\b|minimum (bid|application)", re.I),
    ),
    ("anchor_bid_date", "fact", "Anchor investor bidding date", re.compile(r"\banchor\b", re.I)),
    (
        "bid_open_date",
        "fact",
        "Bid/offer opening date",
        re.compile(r"\b(open|opens|opening)\b", re.I),
    ),
    (
        "bid_close_date",
        "fact",
        "Bid/offer closing date",
        re.compile(r"\b(close|closes|closing)\b", re.I),
    ),
    (
        "offer_for_sale_amount",
        "fact",
        "Offer for sale size",
        re.compile(r"offer for sale|\bofs\b", re.I),
    ),
    ("fresh_issue_amount", "fact", "Fresh issue size", re.compile(r"fresh issue", re.I)),
    (
        "total_issue_amount",
        "fact",
        "Total issue size",
        re.compile(r"(total )?(issue|offer|ipo) size|size of the (issue|offer|ipo)", re.I),
    ),
    ("face_value", "fact", "Face value", re.compile(r"face value", re.I)),
]

_FISCAL = re.compile(
    r"\b(?:fy|fiscal(?: year)?|financial year)\s*'?(\d{2,4})\b|\b20\d\d-(\d{2})\b", re.I
)
_YEAR_ENDED = re.compile(r"(?:year ended|as at|as on)\s+march\s+31,?\s+(20\d\d)", re.I)
_QUARTER = re.compile(
    r"\b(three months|quarter|3m|q1)\b.*?\b(20\d\d)\b|june\s+30,?\s+(20\d\d)", re.I
)


@dataclass
class FactAnswer:
    answer: str
    pages: list[int]
    output_label: str
    found: bool


def detect_intent(question: str) -> tuple[str, str, str] | None:
    """(key, source, name) for a question about a figure or date, else None."""
    for key, source, name, pattern in INTENTS:
        if pattern.search(question):
            return key, source, name
    return None


def detect_period(question: str) -> tuple[str | None, str | None]:
    """(flow period, balance-sheet date) asked for, or (None, None) for 'latest'."""
    if match := _QUARTER.search(question):
        year = match.group(2) or match.group(3)
        return f"3M ended {year}-06-30", f"as at {year}-06-30"
    if match := _YEAR_ENDED.search(question):
        year = match.group(1)
        return f"FY{year}", f"as at {year}-03-31"
    if match := _FISCAL.search(question):
        raw = match.group(1) or match.group(2)
        year = int(raw) if len(raw) == 4 else 2000 + int(raw)
        return f"FY{year}", f"as at {year}-03-31"
    return None, None


def _period_words(period: str) -> str:
    if period.startswith("FY"):
        return f"fiscal {period[2:]}"
    if period.startswith("as at "):
        return period.replace("as at ", "at ")
    return period.replace("3M ended", "the three months ended")


def _money(value: Decimal, unit: str) -> str:
    text = f"{abs(value):,}"
    if unit == "%":
        return f"{'-' if value < 0 else ''}{text}%"
    if unit == "x":
        return f"{text}x"
    if unit == "INR per share":
        return f"{'-' if value < 0 else ''}₹{text} per share"
    if unit.startswith("INR "):
        amount = f"₹{text} {unit[4:]}"
        return f"a loss of {amount}" if value < 0 else amount
    return text


def _basis(session: Session, document_id: int) -> str:
    basis = session.scalar(
        select(ExtractedFigure.basis).where(ExtractedFigure.document_id == document_id).limit(1)
    )
    return {
        "restated_consolidated": "restated consolidated",
        "standalone": "restated standalone",
    }.get(basis or "", "restated")


def answer_from_data(session: Session, document_id: int, question: str) -> FactAnswer | None:
    """An answer from verified data, or None when the question is not about a figure or date
    IPO Lens extracts (those go to the text model)."""
    intent = detect_intent(question)
    if intent is None:
        return None
    key, source, name = intent
    flow, as_at = detect_period(question)

    if source == "fact":
        return _issue_fact(session, document_id, key, name)

    model = ExtractedFigure if source == "figure" else CalculatedMetric
    rows = session.scalars(
        select(model).where(model.document_id == document_id, model.metric == key)
    ).all()
    if not rows:
        return FactAnswer(
            f"{name} is not in the figures IPO Lens extracted from this prospectus.", [], "", False
        )
    by_period: dict[str, ExtractedFigure | CalculatedMetric] = {}
    for r in sorted(rows, key=lambda r: getattr(r, "page_no", 0)):
        assert isinstance(r, ExtractedFigure | CalculatedMetric)
        by_period.setdefault(r.period, r)
    if flow or as_at:
        row = by_period.get(flow or "") or by_period.get(as_at or "")
        if row is None:
            asked = _period_words(flow or as_at or "")
            have = ", ".join(_period_words(p) for p in sorted(by_period))
            return FactAnswer(
                f"Not enough evidence: {name.lower()} for {asked} is not in this prospectus's "
                f"restated statements (available: {have}).",
                [],
                "",
                False,
            )
    else:
        fiscal = sorted(p for p in by_period if p.startswith("FY"))
        dated = sorted(p for p in by_period if p.startswith("as at"))
        latest = (fiscal or dated or sorted(by_period))[-1]
        row = by_period[latest]

    basis = _basis(session, document_id)
    if isinstance(row, ExtractedFigure):
        value = _money(row.value, row.unit)
        return FactAnswer(
            f"{name} for {_period_words(row.period)} was {value} ({basis}, as printed).",
            [row.page_no],
            "verified fact (from the document)",
            True,
        )
    shown = row.value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inputs = session.scalars(
        select(ExtractedFigure.page_no).where(ExtractedFigure.id.in_(row.input_figure_ids))
    ).all()
    note = f" {row.note}" if row.note else ""
    return FactAnswer(
        f"{name} for {_period_words(row.period)} is {_money(shown, row.unit)}, calculated by "
        f"IPO Lens as {row.formula.replace('_', ' ')} from the {basis} statements.{note}",
        sorted(set(inputs)),
        "calculated metric",
        True,
    )


def _issue_fact(session: Session, document_id: int, field: str, name: str) -> FactAnswer:
    # Facts can come from the RHP or a later addendum of the same company
    company = session.scalar(select(Document.company).where(Document.id == document_id))
    doc_ids = list(session.scalars(select(Document.id).where(Document.company == company))) or [
        document_id
    ]
    facts = session.scalars(
        select(IssueFact)
        .where(IssueFact.document_id.in_(doc_ids), IssueFact.field == field)
        .order_by(IssueFact.document_id.desc())
    ).all()
    printed = [f for f in facts if "[●]" not in f.value_text]
    if not printed:
        if facts:
            return FactAnswer(
                f"{name} is not disclosed in this prospectus (printed as [●]); it is usually "
                "published later in a price band advertisement or addendum.",
                [facts[0].page_no],
                "verified fact (from the document)",
                True,
            )
        return FactAnswer(
            f"{name} was not found on the cover pages of this prospectus.", [], "", False
        )
    f = printed[0]
    value = f.value_text
    if f.field.endswith("_date"):
        y, m, d = value.split("-")
        months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        value = f"{months[int(m) - 1]} {int(d)}, {y}"
    elif f.field == "price_band":
        value = "₹" + value.replace(" to ", " to ₹") + " per share"
    elif f.unit == "equity shares":
        value = f"{value} equity shares"
    elif f.unit == "INR per share":
        value = f"₹{value} per share"
    elif f.unit and f.unit.startswith("INR ") and f.value_number is not None:
        value = f"up to ₹{value} {f.unit[4:]}"
    return FactAnswer(
        f"{name}: {value} (as printed in the prospectus).",
        [f.page_no],
        "verified fact (from the document)",
        True,
    )
