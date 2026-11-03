"""Extract reported figures from the restated financial statements in a prospectus.

Reads only what the document prints: every figure keeps its page, the label and the
row text it came from. Nothing is calculated here (see app/calc.py for that).

Column positions in extracted tables are unreliable (headers and values are often
offset), so periods come from the dates in the page header, and a row is used only
when it has exactly one value slot per period.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Document, ExtractedFigure, Page, PageTable

METHOD = "statement-rows v1"

STATEMENT_TITLES = {
    "profit_and_loss": re.compile(
        r"^\s*restated (consolidated |standalone )?statement of profit and loss", re.I
    ),
    "balance_sheet": re.compile(
        r"^\s*restated (consolidated |standalone )?statement of assets and liabilities", re.I
    ),
    "cash_flow": re.compile(
        r"^\s*restated (consolidated |standalone )?(cash flow statement|statement of cash flows)",
        re.I,
    ),
}

# (metric, statement, label pattern, balance-sheet section or None, unit override)
# Labels are matched after normalising: lower case, spaces collapsed, list markers removed.
METRICS: list[tuple[str, str, re.Pattern[str], str | None, str | None]] = [
    (
        "revenue_from_operations",
        "profit_and_loss",
        re.compile(r"^revenue from operations$"),
        None,
        None,
    ),
    ("other_income", "profit_and_loss", re.compile(r"^other income$"), None, None),
    ("total_income", "profit_and_loss", re.compile(r"^total income\b"), None, None),
    ("finance_costs", "profit_and_loss", re.compile(r"^finance costs?$"), None, None),
    (
        "depreciation_amortisation",
        "profit_and_loss",
        re.compile(r"^depreciation and amorti[sz]ation( expense)?$"),
        None,
        None,
    ),
    ("profit_before_tax", "profit_and_loss", re.compile(r"^profit before tax\b"), None, None),
    ("total_tax_expense", "profit_and_loss", re.compile(r"^total tax expense\b"), None, None),
    (
        "profit_after_tax",
        "profit_and_loss",
        re.compile(r"^(restated )?profit (after tax|for the (period|year))"),
        None,
        None,
    ),
    ("eps_basic", "profit_and_loss", re.compile(r"^basic\b"), None, "INR per share"),
    ("eps_diluted", "profit_and_loss", re.compile(r"^diluted\b"), None, "INR per share"),
    ("equity_share_capital", "balance_sheet", re.compile(r"^equity share capital$"), None, None),
    ("total_equity", "balance_sheet", re.compile(r"^total equity\b(?!.*liabilities)"), None, None),
    (
        "borrowings_non_current",
        "balance_sheet",
        re.compile(r"^borrowings$"),
        "non_current_liabilities",
        None,
    ),
    (
        "borrowings_current",
        "balance_sheet",
        re.compile(r"^borrowings$"),
        "current_liabilities",
        None,
    ),
    (
        "cash_and_cash_equivalents",
        "balance_sheet",
        re.compile(r"^cash and cash equivalents$"),
        None,
        None,
    ),
    ("total_assets", "balance_sheet", re.compile(r"^total assets\b"), None, None),
    (
        "net_cash_from_operating_activities",
        "cash_flow",
        re.compile(
            r"^net cash (from|generated from|\(used in\)/generated from"
            r"|generated from/\(used in\)) operating activities"
        ),
        None,
        None,
    ),
]

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_MONTH_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\b(?:\s*,?\s*(\d)\s?(\d))?", re.I)
_YEAR_RE = re.compile(r"\b(20\d\d)\b")
_UNIT_RE = re.compile(r"(₹|rs\.?|inr|rupees)\s*(in\s+)?(million|lakhs?|crores?)", re.I)
_DASH = re.compile(r"^-+$|^—$|^nil$", re.I)
_NUMBER = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?%?$")


@dataclass(frozen=True)
class Period:
    end: date
    months: int  # length for flow statements; 0 means "as at" (balance sheet)

    @property
    def label(self) -> str:
        if self.months == 0:
            return f"as at {self.end.isoformat()}"
        if self.months == 12 and self.end.month == 3:
            return f"FY{self.end.year}"
        return f"{self.months}M ended {self.end.isoformat()}"


@dataclass
class Figure:
    metric: str
    period: Period
    value: Decimal
    unit: str
    page_no: int
    table_ref: str
    source_text: str


def rejoin_split_capitals(text: str) -> str:
    """PDF text sometimes splits a leading capital from its word: 'M arch', 'T otal'."""
    return re.sub(r"\b([A-Z]) ([a-z]{2,})", r"\1\2", text)


def normalise_label(text: str) -> str:
    text = re.sub(r"\s+", " ", rejoin_split_capitals(text).lower()).strip()
    # Leading list markers: "a)", "(b)", "ii)", "i.", "1)"
    text = re.sub(r"^(\(?[a-z]{1,4}\)|\(?\d{1,2}\)|[ivx]{1,4}\.)\s*", "", text)
    return text.strip(" :")


def parse_number(cell: str) -> Decimal | None:
    """'(1,234.50)' -> -1234.50. Dashes mean nil in prospectus tables; returned as None."""
    text = re.sub(r"\s+", "", cell)
    if not text or _DASH.match(text) or not _NUMBER.match(text):
        return None
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-")
    digits = text.strip("()%-").replace(",", "")
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return -value if negative else value


def _is_value_slot(cell: str | None) -> bool:
    if cell is None:
        return False
    text = re.sub(r"\s+", "", cell)
    return bool(text) and bool(_DASH.match(text) or _NUMBER.match(text))


def find_periods(header_text: str, statement: str) -> list[Period]:
    """Periods in header order. Months and years are paired by position, which copes
    with headers split over lines ('March 31, March 31,' ... '2026 2025')."""
    header_text = rejoin_split_capitals(header_text)
    months = [
        (m.group(1).lower(), (m.group(2) or "") + (m.group(3) or ""))
        for m in _MONTH_RE.finditer(header_text)
    ]
    years = [int(y) for y in _YEAR_RE.findall(header_text)]
    if not months or len(months) != len(years):
        return []
    periods = []
    for (month_name, day), year in zip(months, years, strict=True):
        month = MONTHS[month_name]
        # Where the day is printed away from the month, use month end: restated
        # periods in Indian prospectuses end on the last day of a month
        end = date(year, month, int(day) if day else calendar.monthrange(year, month)[1])
        if statement == "balance_sheet":
            periods.append(Period(end, 0))
        else:
            # Indian fiscal year ends 31 March; shorter periods run from 1 April
            periods.append(Period(end, 12 if month == 3 else (month - 3) % 12))
    return periods


def find_unit(page_text: str) -> str | None:
    match = _UNIT_RE.search(page_text)
    if match is None:
        return None
    scale = match.group(3).lower().rstrip("s")
    return f"INR {scale}"


def statement_type(page_text: str) -> str | None:
    head = page_text[:200]
    for name, pattern in STATEMENT_TITLES.items():
        if pattern.search(head):
            return name
    return None


def _is_label(cell: str) -> bool:
    """Has a real word; roman numerals like 'III' are list markers, not labels."""
    text = cell.strip()
    return bool(re.search(r"[a-zA-Z]{3}", text)) and not re.fullmatch(r"[ivxIVX]+[).]?", text)


def _section(label: str, current: str | None) -> str | None:
    if re.match(r"^non[- ]?current liabilities", label):
        return "non_current_liabilities"
    if re.match(r"^current liabilities", label):
        return "current_liabilities"
    if re.match(r"^(equity|non[- ]?current assets|current assets)", label):
        return None
    return current


def extract_from_table(
    rows: list[list[str | None]],
    statement: str,
    periods: list[Period],
    unit: str,
    page_no: int,
    table_index: int,
) -> list[Figure]:
    figures: list[Figure] = []
    seen: set[tuple[str, Period]] = set()
    section: str | None = None
    for row_index, row in enumerate(rows):
        label_cell = next((c for c in row if c and _is_label(c)), None)
        if label_cell is None:
            continue
        label = normalise_label(label_cell)
        section = _section(label, section)
        after_label = row[row.index(label_cell) + 1 :]
        slots = [c for c in after_label if _is_value_slot(c)]
        if len(slots) != len(periods):
            continue
        for metric, metric_statement, pattern, required_section, unit_override in METRICS:
            if metric_statement != statement or not pattern.search(label):
                continue
            if required_section is not None and section != required_section:
                continue
            for period, slot in zip(periods, slots, strict=True):
                value = parse_number(slot or "")
                if value is None or (metric, period) in seen:
                    continue
                seen.add((metric, period))
                figures.append(
                    Figure(
                        metric=metric,
                        period=period,
                        value=value,
                        unit=unit_override or unit,
                        page_no=page_no,
                        table_ref=f"page {page_no} table {table_index} row {row_index}",
                        source_text=" | ".join(c for c in row if c).replace("\n", " "),
                    )
                )
            break
    return figures


def detect_basis(session: Session, document_id: int) -> str:
    """Restated consolidated if the statements say so; standalone only when the
    document states it has no subsidiaries (or says standalone); otherwise 'other'."""
    texts = session.scalars(select(Page.text).where(Page.document_id == document_id))
    has_consolidated = has_standalone = False
    for text in texts:
        head = text[:200].lower()
        if "restated consolidated" in head:
            has_consolidated = True
        if "restated standalone" in head or re.search(r"does not have any subsidiar", text, re.I):
            has_standalone = True
    if has_consolidated:
        return "restated_consolidated"
    return "standalone" if has_standalone else "other"


def extract_document(session: Session, document_id: int) -> list[ExtractedFigure]:
    """Replace this method's figures for one document with a fresh extraction."""
    document = session.get(Document, document_id)
    if document is None:
        raise ValueError(f"No document {document_id}")
    basis = detect_basis(session, document_id)

    session.execute(
        delete(ExtractedFigure).where(
            ExtractedFigure.document_id == document_id, ExtractedFigure.extraction_method == METHOD
        )
    )

    stored: list[ExtractedFigure] = []
    pages = session.scalars(
        select(Page).where(Page.document_id == document_id).order_by(Page.page_no)
    )
    for page in pages:
        statement = statement_type(page.text)
        if statement is None:
            continue
        unit = find_unit(page.text)
        tables = session.scalars(
            select(PageTable)
            .where(PageTable.document_id == document_id, PageTable.page_no == page.page_no)
            .order_by(PageTable.table_index)
        )
        for table in tables:
            # Header = page text before the table's first data row
            first_label = next(
                (
                    normalise_label(c)
                    for r in table.rows
                    for c in r
                    if c
                    and parse_number(c) is None
                    and re.search(r"[a-z]{3}", c.lower())
                    and any(_is_value_slot(x) for x in r)
                ),
                None,
            )
            header = page.text
            if first_label:
                cut = page.text.lower().find(first_label[:20])
                header = page.text[:cut] if cut > 0 else page.text
            periods = find_periods(header, statement)
            if not periods or unit is None:
                continue
            for fig in extract_from_table(
                table.rows, statement, periods, unit, page.page_no, table.table_index
            ):
                row = ExtractedFigure(
                    document_id=document_id,
                    page_no=fig.page_no,
                    table_ref=fig.table_ref,
                    metric=fig.metric,
                    period=fig.period.label,
                    basis=basis,
                    value=fig.value,
                    unit=fig.unit,
                    source_text=fig.source_text,
                    extraction_method=METHOD,
                    confidence=Decimal("0.9"),
                )
                session.add(row)
                stored.append(row)
    session.commit()
    return stored
