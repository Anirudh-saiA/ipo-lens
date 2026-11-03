"""Extract the disclosed risk factors from a prospectus, each with its number and page.

The risk section runs from the 'Risk Factors' heading to the next section ('SECTION III').
Risk headings are numbered 1, 2, 3 ... in order; numbered rows inside tables and numbered
lists inside a risk are ignored, by skipping words that sit inside detected tables and by
accepting only the next number in sequence.

Categories are assigned by keyword rules, not by an AI model, and say so in
category_method. A risk matching no rule is 'uncategorised' rather than guessed.
"""

import re
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.financials import Word, _lines, page_head
from app.models import Page, PageTable, Risk

CATEGORY_METHOD = "keyword rules v1"

# First matching rule wins, so the most specific categories come first
CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "customer_concentration",
        re.compile(
            r"(customers?|clients?)\b.{0,80}\b(significant (portion|part|percentage)|top \w+|"
            r"limited number|concentrat|substantial (portion|part))|"
            r"(significant (portion|part)|substantial (portion|part)|top \w+|limited number)"
            r".{0,80}\b(customers?|clients?)\b|"
            r"(depend|reliance|rely)\w*.{0,40}\b(a few|single|key|major|certain) "
            r"(customers?|clients?)",
            re.I,
        ),
    ),
    (
        "legal",
        re.compile(
            r"litigation|\blegal\b|proceedings|criminal|court|"
            r"tax proceedings|claims? against|disputes?",
            re.I,
        ),
    ),
    (
        "regulatory",
        re.compile(
            r"regulat|licen[cs]e|approvals?|permits?|consents?|compliance|sebi|rbi\b|"
            r"government polic|environmental (law|norm)|spectrum|tariff",
            re.I,
        ),
    ),
    (
        "financial",
        re.compile(
            r"indebted|borrowings?|debt\b|loans?|cash flows?|working capital|interest rate|"
            r"financ|credit rating|losses|profitab|foreign (exchange|currency)|currency|"
            r"dividend|contingent liabilit|capital expenditure|funding",
            re.I,
        ),
    ),
    (
        "industry",
        re.compile(
            r"industry|competition|competitive|competitors|demand for|market conditions|"
            r"econom|cyclical|commodity|raw material prices?|price volatility",
            re.I,
        ),
    ),
    (
        "operational",
        re.compile(
            r"suppl(y|ier)|manufactur|facilit(y|ies)|employees|key (managerial|personnel)|"
            r"information technology|it systems?|cyber|data|operations?|insurance|"
            r"intellectual property|third[- ]part|contracts?|disruption",
            re.I,
        ),
    ),
]

_HEADING = re.compile(r"^(\d{1,3})\.$")
_SECTION_START = re.compile(r"^\s*(section\s+[iv]+\W*)?risk\s+factors", re.I)
_SECTION_END = re.compile(r"^\s*section\s+(iii|3|iv|4)\b", re.I)


@dataclass
class RiskHeading:
    number: int
    page_no: int
    text: str


# Where a heading turns from its cause to the standard list of effects ("... which could
# adversely affect our business, results of operations and financial condition")
_EFFECT_CLAUSE = re.compile(
    r"\b(could|may|might|would|will|can)\b|\b(adversely|materially|negatively)\s+(affect|impact)",
    re.I,
)


def cause(text: str) -> str:
    """The part of a heading that names the risk, without the standard effects clause,
    which mentions 'financial condition' in nearly every heading."""
    match = _EFFECT_CLAUSE.search(text)
    return text[: match.start()] if match and match.start() > 20 else text


def categorise(text: str) -> str:
    subject = cause(text)
    return next(
        (name for name, pattern in CATEGORY_RULES if pattern.search(subject)), "uncategorised"
    )


def _outside_tables(words: list[Word], boxes: list[list[float]]) -> list[Word]:
    def inside(word: Word) -> bool:
        x = (float(word[1]) + float(word[2])) / 2
        y = float(word[3]) + 2
        return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)

    return [w for w in words if not inside(w)]


def headings(pages: list[tuple[int, list[Word]]]) -> list[RiskHeading]:
    """Numbered risk headings in order. A heading is the numbered line plus following
    lines up to the end of its first sentence (at most six lines)."""
    found: list[RiskHeading] = []
    expected = 1
    for page_no, words in pages:
        lines = _lines(words)
        for i, line in enumerate(lines):
            first = str(line[0][0])
            match = _HEADING.match(first)
            if match is None:
                continue
            number = int(match.group(1))
            if number not in (expected, expected + 1):  # allow one missed heading, no more
                continue
            parts = [" ".join(str(w[0]) for w in line[1:])]
            j = i + 1
            while not re.search(r"[.?]$", parts[-1].strip()) and j < len(lines) and j - i < 6:
                parts.append(" ".join(str(w[0]) for w in lines[j]))
                j += 1
            text = re.sub(r"\s+", " ", " ".join(parts)).strip()
            # Headings start like a sentence; some start with a figure ("90.06% of our ...")
            if len(text) < 20 or not re.match(r"^[A-Z0-9“\"(₹]", text):
                continue  # too short or not a sentence: a list item, not a risk heading
            found.append(RiskHeading(number, page_no, text))
            expected = number + 1
    return found


def risk_section(pages: list[Page]) -> list[Page]:
    start = next((i for i, p in enumerate(pages) if _SECTION_START.search(page_head(p.text))), None)
    if start is None:
        return []
    end = next(
        (i for i in range(start + 1, len(pages)) if _SECTION_END.search(page_head(pages[i].text))),
        len(pages),
    )
    return pages[start:end]


def extract_risks(session: Session, document_id: int) -> list[Risk]:
    """Replace this document's disclosed risks with a fresh extraction."""
    session.execute(delete(Risk).where(Risk.document_id == document_id, Risk.origin == "disclosed"))
    pages = list(
        session.scalars(select(Page).where(Page.document_id == document_id).order_by(Page.page_no))
    )
    section = risk_section(pages)
    prepared = []
    for page in section:
        boxes = list(
            session.scalars(
                select(PageTable.bbox).where(
                    PageTable.document_id == document_id, PageTable.page_no == page.page_no
                )
            )
        )
        prepared.append((page.page_no, _outside_tables(page.words or [], boxes)))
    stored = []
    for heading in headings(prepared):
        risk = Risk(
            document_id=document_id,
            page_no=heading.page_no,
            number=heading.number,
            text=heading.text,
            category=categorise(heading.text),
            category_method=CATEGORY_METHOD,
            origin="disclosed",
        )
        session.add(risk)
        stored.append(risk)
    session.commit()
    return stored
