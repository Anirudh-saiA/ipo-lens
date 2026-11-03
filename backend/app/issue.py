"""Extract the structure of the offer from a prospectus: sizes, fresh issue vs offer for
sale, face value, sellers, bid dates and use of proceeds. Each fact keeps its page and the
text it came from. '[●]' means the document leaves the value to be filled in later
(price band, bid lot and amounts usually arrive in an addendum); it is stored as printed
and never replaced by a guess.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.financials import MONTHS, Word, _lines, find_unit
from app.models import IssueFact, Page, PageTable

METHOD = "issue-structure v1"
PLACEHOLDER = "[●]"
NOT_DISCLOSED = "[●] (not disclosed in this document)"

_AMOUNT = re.compile(
    r"aggregating\s+up\s+to\s*(?:₹|rs\.?|inr)?\s*(\[●\]|[\d,]+(?:\.\d+)?)\s*(million|crores?|lakhs?)",
    re.I,
)
_SHARES = re.compile(r"up\s+to\s*(\[●\]|[\d,]+)\s*equity\s+shares", re.I)
_FACE_VALUE = re.compile(r"face\s+value\s+(?:of\s+)?₹\s*(\d+(?:\.\d+)?)", re.I)
_DATE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s*(\d{1,2})\s*,?\s*(20\d\d)", re.I)
# "Price band of ₹142 to ₹150" or "PRICE BAND: ₹ 142 TO ₹ 150 PER EQUITY SHARE"
_PRICE_BAND = re.compile(
    r"price\s+band\s*(?::|of)\s*₹\s*([\d,]+(?:\.\d+)?)\s*(?:to|-|–)\s*₹\s*([\d,]+(?:\.\d+)?)",
    re.I,
)
# "Bids can be made for a minimum of 100 Equity Shares"
_BID_LOT = re.compile(r"minimum\s+of\s+([\d,]+)\s+equity\s+shares", re.I)


@dataclass
class Fact:
    field: str
    page_no: int
    value_text: str
    value_number: Decimal | None = None
    unit: str | None = None
    label: str | None = None
    source_text: str = ""


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _number(text: str) -> Decimal | None:
    return None if text == PLACEHOLDER else Decimal(text.replace(",", ""))


def _unit(word: str) -> str:
    return "INR " + word.lower().rstrip("s")


# --- cover table: fresh issue, offer for sale, total ---------------------------------

_COLUMN_FIELDS = [
    (re.compile(r"fresh\s+issue", re.I), "fresh_issue"),
    (re.compile(r"offer\s+for", re.I), "offer_for_sale"),
    (re.compile(r"total", re.I), "total_issue"),
]


def cover_facts(page_no: int, rows: list[list[str | None]]) -> list[Fact]:
    """The 'Details of the issue' table: a header row naming the columns, then one row of
    values. Cells are matched by order, since merged cells shift column indexes."""
    facts: list[Fact] = []
    for index, row in enumerate(rows):
        header = [c for c in row if c and c.strip()]
        if not (header and re.fullmatch(r"type", header[0].strip(), re.I)):
            continue
        fields = []
        for cell in header[1:]:
            fields.append(next((f for p, f in _COLUMN_FIELDS if p.search(cell)), None))
        if "fresh_issue" not in fields:
            continue
        values_row = next(
            (
                [c for c in r if c and c.strip()]
                for r in rows[index + 1 : index + 6]
                if len([c for c in r if c and c.strip()]) >= len(header) - 1
                # a wrapped heading row ("SIZE | SALE SIZE") is not the values row
                and re.search(
                    r"up\s+to|aggregat|not\s+applicable", " ".join(c or "" for c in r), re.I
                )
            ),
            None,
        )
        if values_row is None:
            continue
        for field, cell in zip(fields, values_row[1:], strict=False):
            if field is None:
                continue
            facts += _size_facts(field, cell, page_no)
        break
    return facts


def _size_facts(field: str, cell: str, page_no: int) -> list[Fact]:
    text = _flat(cell)
    if re.fullmatch(r"not\s+applicable", text, re.I):
        return [Fact(f"{field}_amount", page_no, "Not applicable", Decimal(0), None, None, text)]
    facts = []
    if amount := _AMOUNT.search(text):
        value = amount.group(1)
        facts.append(
            Fact(
                f"{field}_amount",
                page_no,
                NOT_DISCLOSED if value == PLACEHOLDER else value,
                _number(value),
                _unit(amount.group(2)),
                None,
                text,
            )
        )
    if shares := _SHARES.search(text):
        value = shares.group(1)
        facts.append(
            Fact(
                f"{field}_shares",
                page_no,
                NOT_DISCLOSED if value == PLACEHOLDER else value,
                _number(value),
                "equity shares",
                None,
                text,
            )
        )
    return facts


def seller_facts(page_no: int, rows: list[list[str | None]]) -> list[Fact]:
    """'Details of the offer for sale': one row per selling shareholder."""
    facts = []
    in_section = False
    for row in rows:
        cells = [c for c in row if c and c.strip()]
        if not cells:
            continue
        if re.search(r"details of the offer for sale", cells[0], re.I):
            in_section = True
            continue
        if not in_section:
            continue
        joined = _flat(" ".join(cells))
        amount = _AMOUNT.search(joined)
        if amount is None or not re.search(r"selling", joined, re.I):
            continue
        value = amount.group(1)
        facts.append(
            Fact(
                "offer_for_sale_by",
                page_no,
                NOT_DISCLOSED if value == PLACEHOLDER else value,
                _number(value),
                _unit(amount.group(2)),
                _flat(cells[0]),
                joined,
            )
        )
    return facts


# --- dates -----------------------------------------------------------------------------

_DATE_LABELS = [
    (re.compile(r"anchor\s+investor\s+bid", re.I), "anchor_bid_date"),
    (re.compile(r"opens\s+on", re.I), "bid_open_date"),
    (re.compile(r"closes\s+on", re.I), "bid_close_date"),
]


def date_facts(page_no: int, rows: list[list[str | None]]) -> list[Fact]:
    """Bid/offer dates from the cover table. A date may share the label's cell or sit in
    the cells after it, up to the next label."""
    facts = []
    for row in rows:
        cells = [_flat(c) for c in row if c and c.strip()]
        for i, cell in enumerate(cells):
            field = next((f for p, f in _DATE_LABELS if p.search(cell)), None)
            if field is None:
                continue
            label_end = next(p for p, f in _DATE_LABELS if f == field).search(cell)
            assert label_end is not None
            window = [cell[label_end.end() :]]
            for nxt in cells[i + 1 :]:
                if any(p.search(nxt) for p, _ in _DATE_LABELS):
                    break
                window.append(nxt)
            match = _DATE.search(" ".join(window))
            if match is None:
                continue
            month, day, year = match.groups()
            when = date(int(year), MONTHS[month.lower()], int(day))
            facts.append(
                Fact(field, page_no, when.isoformat(), None, None, None, _flat(" ".join(cells)))
            )
    return facts


# --- use of proceeds -----------------------------------------------------------------

_MONEY = re.compile(r"^\(?[\d,]*\d[,.]\d+\)?$|^\[●\]$")
_NOT_AN_OBJECT = re.compile(
    r"^(gross proceeds|net proceeds|(less:?\s*)?\(?less\)?|(issue|offer) related expenses|total)",
    re.I,
)
_MARKER = re.compile(r"^(\d{1,2}\.?|\(?[ivx]{1,4}\)|[a-h]\))$", re.I)


def _is_money(text: str) -> bool:
    return bool(_MONEY.match(text.rstrip("*")))


def proceeds_facts(pages: list[tuple[int, list[Word], str]]) -> list[Fact]:
    """Objects and amounts from the first table on the 'Objects of the issue' pages that
    lists them. Read from word positions so wrapped labels stay with their amounts."""
    facts: list[Fact] = []
    in_table = False
    pending: list[str] = []
    for page_no, words, page_text in pages:
        unit = find_unit(page_text) or "INR million"
        lines = _lines(words)
        i = 0
        while i < len(lines):
            line = lines[i]
            texts = [str(w[0]) for w in line]
            joined = " ".join(texts)
            # A column header ('Sr. Particulars Estimated Amount'), not a heading such as
            # 'PARTICULARS OF THE ISSUE'
            if re.search(r"\bParticulars\b", joined) and len(texts) <= 12:
                if facts:
                    return facts  # the next table (e.g. yearly deployment) repeats them
                in_table, pending = True, []
                i += 1
                continue
            if not in_table:
                i += 1
                continue
            first_money = next((k for k, t in enumerate(texts) if _is_money(t)), None)
            if first_money is None:
                pending = texts
                i += 1
                continue
            label_words = [t for t in texts[:first_money] if not _MARKER.match(t)]
            if not label_words:
                label_words = pending
            label = " ".join(label_words)
            if _NOT_AN_OBJECT.match(label):
                if facts and re.match(r"^(net proceeds|total)", label, re.I):
                    return facts
                pending = []
                i += 1
                continue
            # Continuation lines: no amounts, starting lowercase or '(' + lowercase
            j = i + 1
            while j < len(lines):
                nxt = [str(w[0]) for w in lines[j]]
                unfinished = re.search(r"(,|\band|\bof|\bfor|\bthe|\bi\.e\.)$", label)
                if any(_is_money(t) for t in nxt) or not (
                    re.match(r"^\(?[a-z]", nxt[0]) or unfinished
                ):
                    break
                label += " " + " ".join(nxt)
                j += 1
            amount = texts[first_money].rstrip("*")
            label = re.sub(r"\s*(\(\d\)|\*)+$", "", _flat(label)).strip(" ,")
            facts.append(
                Fact(
                    "use_of_proceeds",
                    page_no,
                    NOT_DISCLOSED if amount == PLACEHOLDER else amount,
                    _number(amount),
                    unit,
                    label,
                    _flat(f"{label} {amount}"),
                )
            )
            pending = []
            i = j
    return facts


# --- document level ----------------------------------------------------------------------


def _price_band_fact(pages: list[Page]) -> Fact | None:
    """The price band, if printed; otherwise where the document says it is to be announced."""
    for page in pages:
        if match := _PRICE_BAND.search(page.text):
            low, high = match.groups()
            return Fact(
                "price_band",
                page.page_no,
                f"{low} to {high}",
                None,
                "INR per share",
                None,
                _flat(match.group(0)),
            )
    for page in pages:
        if match := re.search(r"price\s+band[^.]{0,200}", page.text, re.I):
            return Fact(
                "price_band",
                page.page_no,
                NOT_DISCLOSED,
                None,
                "INR per share",
                None,
                _flat(match.group(0)),
            )
    return None


def extract_issue(session: Session, document_id: int) -> list[IssueFact]:
    """Replace this document's issue facts with a fresh extraction."""
    session.execute(
        delete(IssueFact).where(
            IssueFact.document_id == document_id, IssueFact.extraction_method == METHOD
        )
    )
    pages = list(
        session.scalars(select(Page).where(Page.document_id == document_id).order_by(Page.page_no))
    )
    front = [p for p in pages if p.page_no <= 6]
    facts: list[Fact] = []
    seen: set[str] = set()
    for page in front:
        tables = session.scalars(
            select(PageTable)
            .where(PageTable.document_id == document_id, PageTable.page_no == page.page_no)
            .order_by(PageTable.table_index)
        )
        for table in tables:
            for fact in (
                cover_facts(page.page_no, table.rows)
                + seller_facts(page.page_no, table.rows)
                + date_facts(page.page_no, table.rows)
            ):
                key = fact.field if fact.field != "offer_for_sale_by" else f"ofs:{fact.label}"
                if key not in seen:  # the first statement of a fact in the document wins
                    seen.add(key)
                    facts.append(fact)
        if (match := _FACE_VALUE.search(page.text)) and "face_value" not in seen:
            seen.add("face_value")
            facts.append(
                Fact(
                    "face_value",
                    page.page_no,
                    match.group(1),
                    Decimal(match.group(1)),
                    "INR per share",
                    None,
                    _flat(match.group(0)),
                )
            )
    if (band := _price_band_fact(front)) is not None:
        facts.append(band)
    for page in front:
        if lot := _BID_LOT.search(page.text):
            facts.append(
                Fact(
                    "bid_lot",
                    page.page_no,
                    lot.group(1),
                    _number(lot.group(1)),
                    "equity shares",
                    None,
                    _flat(lot.group(0)),
                )
            )
            break

    start = next(
        (
            p.page_no
            for p in pages
            # The section heading is in capitals; mentions in other sections are not
            if re.search(r"OBJECTS\s+OF\s+THE\s+(ISSUE|OFFER)", p.text[:300])
        ),
        None,
    )
    if start is not None:
        objects = [
            (p.page_no, p.words or [], p.text) for p in pages if start <= p.page_no <= start + 2
        ]
        facts += proceeds_facts(objects)

    stored = []
    for f in facts:
        row = IssueFact(
            document_id=document_id,
            page_no=f.page_no,
            field=f.field,
            label=f.label,
            value_text=f.value_text,
            value_number=f.value_number,
            unit=f.unit,
            source_text=f.source_text[:1000],
            extraction_method=METHOD,
        )
        session.add(row)
        stored.append(row)
    session.commit()
    return stored
