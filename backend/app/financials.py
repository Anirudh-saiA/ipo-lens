"""Extract reported figures from the restated financial statements in a prospectus.

Reads only what the document prints: every figure keeps its page, the label and the
row text it came from. Nothing is calculated here (see app/calc.py for that).

Two ways to read a statement page, both feeding the same row matcher:
- tables: for statements drawn with ruling lines. Column positions in extracted tables
  are unreliable, so periods come from the dates in the page header and a row is used
  only when it has exactly one value per period.
- words: for statements drawn without lines. Columns are rebuilt from the x positions of
  the numbers, and each date in the header is assigned to the column it sits above.
The words method runs only on pages where the tables method found nothing.
"""

import calendar
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Document, ExtractedFigure, Page, PageTable

METHOD = "statement-rows v1"
WORDS_METHOD = "statement-words v1"

_TITLE_PREFIX = r"^\s*(summary of )?restated (consolidated |standalone )?"
# Also "SUMMARY OF PROFIT AND LOSS ON RESTATED CONSOLIDATED BASIS" (Acevector)
_BASIS_SUFFIX = r"\s+on\s+restated\s+(consolidated|standalone)\s+basis"
STATEMENT_TITLES = {
    "profit_and_loss": re.compile(
        _TITLE_PREFIX
        + r"statement of profit (and|&) loss|^\s*summary of profit (and|&) loss"
        + _BASIS_SUFFIX,
        re.I,
    ),
    "balance_sheet": re.compile(
        _TITLE_PREFIX + r"statement of assets and liabilities"
        r"|^\s*summary of assets and liabilities" + _BASIS_SUFFIX,
        re.I,
    ),
    "cash_flow": re.compile(
        _TITLE_PREFIX + r"(cash flow statement|statement of cash flows?)"
        r"|^\s*summary of cash flows?" + _BASIS_SUFFIX,
        re.I,
    ),
}


@dataclass(frozen=True)
class MetricRule:
    metric: str
    statement: str
    pattern: re.Pattern[str]
    section: str | None = None  # balance-sheet section the row must sit in
    unit: str | None = None  # overrides the page unit (per-share values)


# Labels are matched after normalising: lower case, spaces collapsed, list markers removed.
# Order matters: where two rules give the same metric, the earlier rule wins, wherever
# its row appears on the page (e.g. "profit for the year" beats "profit after tax",
# which in consolidated statements comes before the share of associates).
METRICS: list[MetricRule] = [
    MetricRule(
        # "Revenue from operations", or "Revenue From Operations (Net)" (BLS Polymers)
        "revenue_from_operations",
        "profit_and_loss",
        re.compile(r"^revenue from operations( \(net\))?$"),
    ),
    MetricRule("other_income", "profit_and_loss", re.compile(r"^other income$")),
    MetricRule("total_income", "profit_and_loss", re.compile(r"^total income\b")),
    MetricRule("finance_costs", "profit_and_loss", re.compile(r"^finance costs?$")),
    MetricRule(
        "depreciation_amortisation",
        "profit_and_loss",
        re.compile(r"^depreciation and amorti[sz]ation( expenses?)?$"),
    ),
    # Loss-making companies print "loss" in the label ("Restated loss before tax"), with
    # the amount in brackets; the brackets make the value negative.
    MetricRule(
        "profit_before_tax",
        "profit_and_loss",
        re.compile(r"^(restated )?(profit|loss)(\s?/\s?\((loss|profit)\))? before tax"),
    ),
    # Only when no "before tax" line exists (Jio prints "before share of ... and tax")
    MetricRule(
        "profit_before_tax",
        "profit_and_loss",
        re.compile(r"^(restated )?(profit|loss)(\s?/\s?\((loss|profit)\))? before share of"),
    ),
    # Profit before one-off exceptional items: EBITDA starts from this when printed
    MetricRule(
        "profit_before_exceptional_items_and_tax",
        "profit_and_loss",
        re.compile(
            r"^(restated )?(profit|loss)(\s?/\s?\((loss|profit)\))? before exceptional items"
            r" and tax"
        ),
    ),
    MetricRule("total_tax_expense", "profit_and_loss", re.compile(r"^total tax expenses?\b")),
    MetricRule(
        "profit_after_tax",
        "profit_and_loss",
        re.compile(
            r"^(restated )?(net )?(profit|loss)(\s?/\s?\((loss|profit)\))? for the (period|year)"
        ),
    ),
    MetricRule(
        "profit_after_tax",
        "profit_and_loss",
        re.compile(r"^(restated )?(profit|loss)(\s?/\s?\((loss|profit)\))? after tax"),
    ),
    MetricRule("eps_basic", "profit_and_loss", re.compile(r"^basic\b"), unit="INR per share"),
    MetricRule("eps_diluted", "profit_and_loss", re.compile(r"^diluted\b"), unit="INR per share"),
    MetricRule("equity_share_capital", "balance_sheet", re.compile(r"^equity share capital$")),
    MetricRule("other_equity", "balance_sheet", re.compile(r"^other equity$")),
    MetricRule(
        "non_controlling_interest", "balance_sheet", re.compile(r"^non[- ]controlling interests?$")
    ),
    MetricRule("total_equity", "balance_sheet", re.compile(r"^total equity\b(?!.*liabilities)")),
    MetricRule(
        "borrowings_non_current",
        "balance_sheet",
        re.compile(r"^borrowings$"),
        section="non_current_liabilities",
    ),
    MetricRule(
        "borrowings_current",
        "balance_sheet",
        re.compile(r"^borrowings$"),
        section="current_liabilities",
    ),
    # Deferred payments for spectrum and similar: debt-like, but not borrowings
    MetricRule(
        "deferred_payment_liabilities_non_current",
        "balance_sheet",
        re.compile(r"^deferred payment liabilit(y|ies)$"),
        section="non_current_liabilities",
    ),
    MetricRule(
        "deferred_payment_liabilities_current",
        "balance_sheet",
        re.compile(r"^deferred payment liabilit(y|ies)$"),
        section="current_liabilities",
    ),
    MetricRule(
        "cash_and_cash_equivalents", "balance_sheet", re.compile(r"^cash and cash equivalents$")
    ),
    MetricRule("total_assets", "balance_sheet", re.compile(r"^total assets\b")),
    MetricRule(
        "net_cash_from_operating_activities",
        "cash_flow",
        re.compile(
            # "net cash from", "net cash flows generated from", "(used in)/generated from"
            r"^net cash (flows? )?[a-z/() ]*\boperating activities"
        ),
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
# "8.69*": an asterisk marks a footnote such as "not annualised"
_NUMBER = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?%?\*?$")


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
    method: str = METHOD


@dataclass
class Row:
    """One line of a statement: its label and its value cells, before any matching."""

    label: str  # normalised
    slots: list[str]  # value cells in column order; empty for heading rows
    source_text: str
    ref: str


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
    text = text.rstrip("*")
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


def _period(year: int, month: int, day: int | None, statement: str) -> Period:
    # Where the day is printed away from the month, use month end: restated
    # periods in Indian prospectuses end on the last day of a month
    end = date(year, month, day or calendar.monthrange(year, month)[1])
    if statement == "balance_sheet":
        return Period(end, 0)
    # Indian fiscal year ends 31 March; shorter periods run from 1 April
    return Period(end, 12 if month == 3 else (month - 3) % 12)


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
    return [
        _period(year, MONTHS[name], int(day) if day else None, statement)
        for (name, day), year in zip(months, years, strict=True)
    ]


def find_unit(page_text: str) -> str | None:
    match = _UNIT_RE.search(page_text)
    if match is None:
        return None
    scale = match.group(3).lower().rstrip("s")
    return f"INR {scale}"


def page_head(page_text: str, length: int = 200) -> str:
    """Start of a page, without a stray leading number some PDFs repeat on every page
    (BLS Polymers' RHP text starts each page with '24')."""
    return re.sub(r"^\s*\d{1,4}\s+", "", page_text[: length + 10])[:length]


def statement_type(page_text: str) -> str | None:
    """The statement a page holds, from a title at the top of the page or a short title
    line further down (a statement can start mid-page). Mentions inside sentences, such as
    'see Restated Statement of Profit and Loss on page 91', are not titles."""
    head = page_head(page_text)
    for name, pattern in STATEMENT_TITLES.items():
        if pattern.search(head):
            return name
    for line in page_text.splitlines()[:80]:
        line = line.strip()
        if len(line) > 110 or re.search(r"\bon page\b|\bsee\b", line, re.I):
            continue
        for name, pattern in STATEMENT_TITLES.items():
            if pattern.search(line):
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


def match_rows(
    rows: list[Row], statement: str, periods: list[Period], unit: str, page_no: int, method: str
) -> list[Figure]:
    """Turn statement rows into figures. A row is used only if it has one value per period."""
    best: dict[tuple[str, Period], tuple[int, Figure]] = {}
    section: str | None = None
    for row in rows:
        section = _section(row.label, section)
        if len(row.slots) != len(periods):
            continue
        for priority, rule in enumerate(METRICS):
            if rule.statement != statement or not rule.pattern.search(row.label):
                continue
            if rule.section is not None and section != rule.section:
                continue
            for period, slot in zip(periods, row.slots, strict=True):
                value = parse_number(slot)
                key = (rule.metric, period)
                if value is None or (key in best and best[key][0] <= priority):
                    continue
                best[key] = (
                    priority,
                    Figure(
                        metric=rule.metric,
                        period=period,
                        value=value,
                        unit=rule.unit or unit,
                        page_no=page_no,
                        table_ref=row.ref,
                        source_text=row.source_text,
                        method=method,
                    ),
                )
            break
    return [figure for _, figure in best.values()]


# --- reading rows from ruled tables ---------------------------------------------


def rows_from_table(rows: list[list[str | None]], page_no: int, table_index: int) -> list[Row]:
    out = []
    for row_index, cells in enumerate(rows):
        label_cell = next((c for c in cells if c and _is_label(c)), None)
        if label_cell is None:
            continue
        after_label = cells[cells.index(label_cell) + 1 :]
        out.append(
            Row(
                label=normalise_label(label_cell),
                slots=[c for c in after_label if c is not None and _is_value_slot(c)],
                source_text=" | ".join(c for c in cells if c).replace("\n", " "),
                ref=f"page {page_no} table {table_index} row {row_index}",
            )
        )
    return out


def extract_from_table(
    rows: list[list[str | None]],
    statement: str,
    periods: list[Period],
    unit: str,
    page_no: int,
    table_index: int,
) -> list[Figure]:
    return match_rows(
        rows_from_table(rows, page_no, table_index), statement, periods, unit, page_no, METHOD
    )


# --- reading rows from word positions --------------------------------------------

Word = list[str | float]  # [text, x0, x1, top]


def _lines(words: list[Word], tolerance: float = 3.0) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (float(w[3]), float(w[1]))):
        if lines and abs(float(lines[-1][0][3]) - float(word[3])) <= tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: float(w[1])) for line in lines]


def _split_line(line: list[Word]) -> tuple[list[Word], list[Word]] | None:
    """Label words then value words. None if text follows a value (a prose line)."""
    label: list[Word] = []
    values: list[Word] = []
    for word in line:
        if _is_value_slot(str(word[0])):
            values.append(word)
        elif values:
            return None
        else:
            label.append(word)
    return label, values


def _columns(lines: list[list[Word]]) -> list[tuple[float, float]] | None:
    """Value columns as (left, right) spans, from lines carrying the most common number of
    values. Numbers are right-aligned, so their right edges line up per column."""
    splits = [s for s in (_split_line(line) for line in lines) if s and len(s[1]) >= 2]
    if not splits:
        return None
    width = Counter(len(values) for _, values in splits).most_common(1)[0][0]
    full = [values for _, values in splits if len(values) == width]
    spans = []
    for i in range(width):
        lefts = [float(v[i][1]) for v in full]
        rights = [float(v[i][2]) for v in full]
        spans.append((min(lefts), max(rights)))
    if any(spans[i][1] >= spans[i + 1][0] + 5 for i in range(width - 1)):
        return None  # columns overlap: positions are not consistent enough to trust
    return spans


def _column_of(word: Word, spans: list[tuple[float, float]], slack: float = 12.0) -> int | None:
    """Column a word sits in: overlapping span first, else the nearest span within slack."""
    x0, x1 = float(word[1]), float(word[2])
    overlaps = [min(x1, r) - max(x0, left) for left, r in spans]
    best = max(range(len(spans)), key=lambda i: overlaps[i])
    if overlaps[best] > 0:
        return best
    gaps = [max(left - x1, x0 - r) for left, r in spans]
    nearest = min(range(len(spans)), key=lambda i: gaps[i])
    return nearest if gaps[nearest] <= slack else None


def _header_token(word: Word) -> str:
    return rejoin_split_capitals(str(word[0])).strip(",. ").lower()


def _merge_touching(line: list[Word], gap: float = 1.0) -> list[Word]:
    """Rejoin pieces PDF text split apart without a space: '3' '1,' -> '31,', 'M' 'arch'."""
    merged: list[Word] = []
    for word in line:
        if merged and float(word[1]) - float(merged[-1][2]) < gap:
            last = merged[-1]
            merged[-1] = [f"{last[0]}{word[0]}", last[1], word[2], last[3]]
        else:
            merged.append(list(word))
    return merged


def _owning_month(
    word: Word, before: list[Word], month_words: list[tuple[Word, int | None]]
) -> int | None:
    """Column of the month a day or year belongs to, if it can be told by position."""
    x0, x1 = float(word[1]), float(word[2])
    for candidate in reversed(before):  # same line: the nearest month to the left
        if _header_token(candidate) in MONTHS:
            if x0 - float(candidate[2]) <= 40:
                return next((c for w, c in month_words if w is candidate or w == candidate), None)
            break
    for month, column in month_words:  # another line: a month directly above or below
        if min(x1, float(month[2])) - max(x0, float(month[1])) > 0:
            return column
    return None


def _periods_from_year_line(lines: list[list[Word]], k: int, statement: str) -> list[Period]:
    """Periods from the one header line that holds exactly k years (k = value columns).

    On that line, a month or day belongs to the first year to its right. A month or day on
    another line belongs to the column whose year is nearest horizontally. In a range
    ('April 1, 2026 to June 30, 2026') the later date wins. A column with a day and year but
    no month takes the header's month only if every month in the header is the same."""
    year_lines = [
        line
        for line in lines
        if sum(re.fullmatch(r"20\d\d", _header_token(w)) is not None for w in line) == k
    ]
    if len(year_lines) != 1:
        return []
    (year_line,) = year_lines
    year_words = [w for w in year_line if re.fullmatch(r"20\d\d", _header_token(w))]
    centres = [(float(w[1]) + float(w[2])) / 2 for w in year_words]
    years = [int(_header_token(w)) for w in year_words]
    months: list[int | None] = [None] * k
    days: list[int | None] = [None] * k
    fiscal = False

    def nearest(word: Word) -> int:
        centre = (float(word[1]) + float(word[2])) / 2
        return min(range(k), key=lambda i: abs(centres[i] - centre))

    for line in lines:
        for word in line:
            text = _header_token(word)
            if text == "fiscal":
                fiscal = True
                continue
            is_month = text in MONTHS
            if not is_month and not re.fullmatch(r"[0-3]?\d", text):
                continue
            if line is year_line:
                right = [i for i, y in enumerate(year_words) if float(y[1]) >= float(word[2]) - 1]
                if not right:
                    continue
                column = right[0]
            else:
                column = nearest(word)
            if is_month:
                months[column] = MONTHS[text]
            else:
                days[column] = int(text)

    found = {m for m in months if m is not None}
    periods = []
    for month, day, year in zip(months, days, years, strict=True):
        if month is None:
            if len(found) == 1 and day is not None:
                month = next(iter(found))  # "For the year ended March / 31, 2024" wraps
            elif fiscal:
                month, day = 3, 31
            else:
                return []
        periods.append(_period(year, month, day, statement))
    return periods


def periods_from_header(
    header: list[list[Word]], spans: list[tuple[float, float]], statement: str
) -> list[Period]:
    """Assign each month, day and year in the header to its column.

    Headers are centred or left-aligned while numbers are right-aligned, so a month goes
    to the column whose region (split at the midpoints between columns) holds its centre.
    A day or year belongs to its month: the month just before it on the same line, else
    a month directly above or below it, else the region it sits in. Where a column shows
    a range ('April 1, 2026 to June 30, 2026'), the later date wins."""
    months: list[int | None] = [None] * len(spans)
    days: list[int | None] = [None] * len(spans)
    years: list[int | None] = [None] * len(spans)
    fiscal = False
    cuts = [(spans[i][1] + spans[i + 1][0]) / 2 for i in range(len(spans) - 1)]

    def region(word: Word) -> int | None:
        centre = (float(word[1]) + float(word[2])) / 2
        if centre < spans[0][0] - 70 or centre > spans[-1][1] + 30:
            return None
        return sum(centre > cut for cut in cuts)

    lines = [_merge_touching(line) for line in header]

    # Preferred: a header line that prints every column's year, left to right. Those years
    # define the columns. Copes with left-aligned headers over right-aligned numbers,
    # where midpoints between number columns put a month in the wrong column.
    anchored = _periods_from_year_line(lines, len(spans), statement)
    if anchored:
        return anchored

    month_words = [
        (word, region(word)) for line in lines for word in line if _header_token(word) in MONTHS
    ]
    for line in lines:
        for index, word in enumerate(line):
            text = _header_token(word)
            if text == "fiscal":
                fiscal = True
                continue
            if text in MONTHS:
                column = region(word)
                if column is not None:
                    months[column] = MONTHS[text]
                continue
            is_year = bool(re.fullmatch(r"20\d\d", text))
            if not is_year and not re.fullmatch(r"[0-3]?\d", text):
                continue
            column = _owning_month(word, line[:index], month_words)
            if column is None:
                column = region(word)
            if column is None:
                continue
            if is_year:
                years[column] = int(text)
            else:
                days[column] = int(text)
    periods = []
    for month, day, year in zip(months, days, years, strict=True):
        if year is None:
            return []
        if month is None:
            if not fiscal:
                return []  # a bare year is ambiguous unless the header says "Fiscal"
            month, day = 3, 31  # "Fiscal 2026" = year ended 31 March 2026
        periods.append(_period(year, month, day, statement))
    return periods


@dataclass
class Layout:
    lines: list[list[Word]]
    spans: list[tuple[float, float]]
    first_data: int  # index of the first line carrying a full row of values
    periods: list[Period]


def read_layout(words: list[Word], statement: str) -> Layout | None:
    """Columns and their periods from word positions. Header text order cannot be trusted
    (a header can read 'April 1, 2026 to ended March 31, ... June 30, 2026 2026 2025'),
    so each date is tied to the column it sits over; in a range, the later date wins."""
    lines = _lines(words)
    spans = _columns(lines)
    if spans is None:
        return None
    first_data = next(
        (
            i
            for i, line in enumerate(lines)
            if (s := _split_line(line)) and s[0] and len(s[1]) == len(spans)
        ),
        None,
    )
    if first_data is None:
        return None
    periods = periods_from_header(lines[:first_data], spans, statement)
    return Layout(lines, spans, first_data, periods) if periods else None


def extract_from_words(words: list[Word], statement: str, unit: str, page_no: int) -> list[Figure]:
    layout = read_layout(words, statement)
    if layout is None:
        return []
    lines, spans, first_data, periods = (
        layout.lines,
        layout.spans,
        layout.first_data,
        layout.periods,
    )

    def place(values: list[Word], slots: list[str | None]) -> bool:
        """Put values into their columns by position; False on a clash or stray value."""
        for value in values:
            column = _column_of(value, spans)
            if column is None or slots[column] is not None:
                return False
            slots[column] = str(value[0])
        return True

    rows: list[Row] = []
    pending: list[Word] = []  # a label line whose values sit on the next line
    skip: set[int] = set()
    for index, line in enumerate(lines[first_data:], start=first_data):
        if index in skip:
            continue
        split = _split_line(line)
        if split is None:
            pending = []
            continue
        label_words, values = split
        if not values:
            pending = label_words
            rows.append(
                Row(
                    normalise_label(_join(label_words)),
                    [],
                    _join(line),
                    f"page {page_no} line {index}",
                )
            )
            continue
        if not label_words:
            label_words, pending = pending, []
        slots: list[str | None] = [None] * len(spans)
        if not place(values, slots):
            slots = []
        elif not all(s is not None for s in slots) and index + 1 < len(lines):
            # A row can spill onto the next line: "Depreciation and amortization 64.74 ..."
            # then "expense 124.58". Join only if the next line continues the label (or has
            # none) and its values land exactly in the empty columns.
            nxt = _split_line(lines[index + 1])
            if nxt is not None and nxt[1]:
                nxt_label = _join(nxt[0])
                if not nxt_label or re.match(r"^[a-z(]", nxt_label):
                    trial = list(slots)
                    if place(nxt[1], trial) and all(s is not None for s in trial):
                        slots = trial
                        label_words = label_words + nxt[0]
                        values = values + nxt[1]
                        skip.add(index + 1)
        rows.append(
            Row(
                label=normalise_label(_join(label_words)),
                slots=[s for s in slots if s is not None]
                if all(s is not None for s in slots)
                else [],
                source_text=_join(label_words + values),
                ref=f"page {page_no} line {index}",
            )
        )
    return match_rows(rows, statement, periods, unit, page_no, WORDS_METHOD)


def _join(words: list[Word]) -> str:
    return " ".join(str(w[0]) for w in words)


# --- document level ----------------------------------------------------------------


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


def _from_tables(session: Session, page: Page, statement: str, unit: str) -> list[Figure]:
    figures: list[Figure] = []
    # Periods come from word positions when stored. Header text order can pair a month
    # with the wrong year without any visible error, so it is used only for pages stored
    # without positions, and never as a fallback when positions disagree or fail.
    layout = read_layout(page.words, statement) if page.words else None
    if page.words and layout is None:
        return []
    tables = session.scalars(
        select(PageTable)
        .where(PageTable.document_id == page.document_id, PageTable.page_no == page.page_no)
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
        if layout is not None:
            periods = layout.periods
        else:
            header = page.text
            if first_label:
                cut = page.text.lower().find(first_label[:20])
                header = page.text[:cut] if cut > 0 else page.text
            periods = find_periods(header, statement)
        if periods:
            figures += extract_from_table(
                table.rows, statement, periods, unit, page.page_no, table.table_index
            )
    return figures


def extract_document(session: Session, document_id: int) -> list[ExtractedFigure]:
    """Replace this module's figures for one document with a fresh extraction."""
    document = session.get(Document, document_id)
    if document is None:
        raise ValueError(f"No document {document_id}")
    basis = detect_basis(session, document_id)

    session.execute(
        delete(ExtractedFigure).where(
            ExtractedFigure.document_id == document_id,
            ExtractedFigure.extraction_method.in_([METHOD, WORDS_METHOD]),
        )
    )

    stored: list[ExtractedFigure] = []
    pages = session.scalars(
        select(Page).where(Page.document_id == document_id).order_by(Page.page_no)
    )
    # A statement can run onto the next page without repeating its title. That page is read
    # as a continuation only if it is the very next page and its columns show exactly the
    # same periods; anything else on an untitled page is ignored.
    previous: tuple[int, str, str, list[Period]] | None = None
    for page in pages:
        statement = statement_type(page.text)
        unit = find_unit(page.text)
        if statement is None and previous is not None and page.page_no == previous[0] + 1:
            _, prev_statement, prev_unit, prev_periods = previous
            cont = read_layout(page.words, prev_statement) if page.words else None
            if cont is not None and cont.periods == prev_periods:
                statement, unit = prev_statement, unit or prev_unit
        if statement is None or unit is None:
            previous = None
            continue
        figures = _from_tables(session, page, statement, unit)
        if page.words:
            # Word positions fill gaps the table reader left (e.g. a row split over two
            # lines); a figure the table reader found is never replaced
            have = {(f.metric, f.period) for f in figures}
            figures += [
                f
                for f in extract_from_words(page.words, statement, unit, page.page_no)
                if (f.metric, f.period) not in have
            ]
        layout = read_layout(page.words, statement) if page.words else None
        previous = (page.page_no, statement, unit, layout.periods) if layout else None
        for fig in figures:
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
                extraction_method=fig.method,
                confidence=Decimal("0.9"),
            )
            session.add(row)
            stored.append(row)
    session.commit()
    return stored
