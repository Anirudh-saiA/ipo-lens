"""One entry per IPO (company): its documents, its status from the bid dates printed in the
prospectus, the price band if any document prints one, and headline figures for the latest
fiscal year. Everything shown keeps the page it came from.

Status is computed here, in Python, from the document's own dates; no market data source is
used (hard rule 9: ask before adding a scraping source).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, Document, ExtractedFigure, IssueFact

# Which document's facts win when two disagree: the latest filed, then by type
_DOC_ORDER = {"prospectus": 0, "corrigendum": 1, "addendum": 2, "RHP": 3, "DRHP": 4}


@dataclass
class Cited:
    value: str
    unit: str | None
    document_id: int
    page_no: int
    label: str  # hard rule 4 output label
    period: str | None = None


@dataclass
class Ipo:
    company: str
    primary_document_id: int
    documents: list[Document]
    status: str  # upcoming, open, closed, unknown
    bid_open: Cited | None = None
    bid_close: Cited | None = None
    price_band: Cited | None = None
    headline: dict[str, Cited] = field(default_factory=dict)


def ipo_status(today: date, opens: date | None, closes: date | None) -> str:
    if opens is None or closes is None:
        return "unknown"
    if today < opens:
        return "upcoming"
    if today <= closes:
        return "open"
    return "closed"


def _fact(session: Session, documents: list[Document], field_name: str) -> IssueFact | None:
    """The fact from the most authoritative document that prints it with a value."""
    ranked = sorted(
        documents,
        key=lambda d: (-(d.filing_date or date.min).toordinal(), _DOC_ORDER.get(d.doc_type, 9)),
    )
    for doc in ranked:
        facts = session.scalars(
            select(IssueFact).where(IssueFact.document_id == doc.id, IssueFact.field == field_name)
        ).all()
        disclosed = [f for f in facts if "[●]" not in f.value_text]
        if disclosed:
            return disclosed[0]
    return None


def _headline(session: Session, document_id: int) -> dict[str, Cited]:
    """Revenue, EBITDA and profit after tax for the latest full fiscal year."""
    figures = session.scalars(
        select(ExtractedFigure)
        .where(
            ExtractedFigure.document_id == document_id,
            ExtractedFigure.metric.in_(["revenue_from_operations", "profit_after_tax"]),
            ExtractedFigure.period.like("FY%"),
        )
        .order_by(ExtractedFigure.page_no, ExtractedFigure.id)
    ).all()
    years = sorted({f.period for f in figures}, reverse=True)
    if not years:
        return {}
    latest = years[0]
    out: dict[str, Cited] = {}
    for f in figures:
        if f.period == latest and f.metric not in out:
            out[f.metric] = Cited(
                str(f.value),
                f.unit,
                document_id,
                f.page_no,
                "verified fact (from the document)",
                latest,
            )
    ebitda = session.scalar(
        select(CalculatedMetric).where(
            CalculatedMetric.document_id == document_id,
            CalculatedMetric.metric == "ebitda",
            CalculatedMetric.period == latest,
        )
    )
    if ebitda is not None:
        pages = sorted(
            {
                f.page_no
                for f in session.scalars(
                    select(ExtractedFigure).where(ExtractedFigure.id.in_(ebitda.input_figure_ids))
                )
            }
        )
        out["ebitda"] = Cited(
            str(ebitda.value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            ebitda.unit,
            document_id,
            pages[0] if pages else 0,
            "calculated metric",
            latest,
        )
    return out


def list_ipos(session: Session, today: date) -> list[Ipo]:
    documents = session.scalars(select(Document).order_by(Document.company, Document.id)).all()
    by_company: dict[str, list[Document]] = {}
    for doc in documents:
        by_company.setdefault(doc.company.strip().lower(), []).append(doc)

    ipos = []
    for docs in by_company.values():
        primary = next((d for d in docs if d.doc_type == "RHP"), None) or docs[0]
        opens, closes = (
            _fact(session, docs, "bid_open_date"),
            _fact(session, docs, "bid_close_date"),
        )
        band = _fact(session, docs, "price_band")

        def cited(f: IssueFact | None) -> Cited | None:
            if f is None:
                return None
            return Cited(
                f.value_text, f.unit, f.document_id, f.page_no, "verified fact (from the document)"
            )

        ipos.append(
            Ipo(
                company=primary.company,
                primary_document_id=primary.id,
                documents=docs,
                status=ipo_status(
                    today,
                    date.fromisoformat(opens.value_text) if opens else None,
                    date.fromisoformat(closes.value_text) if closes else None,
                ),
                bid_open=cited(opens),
                bid_close=cited(closes),
                price_band=cited(band),
                headline=_headline(session, primary.id),
            )
        )
    order = {"open": 0, "upcoming": 1, "closed": 2, "unknown": 3}
    return sorted(
        ipos,
        key=lambda i: (
            order[i.status],
            -(date.fromisoformat(i.bid_open.value) if i.bid_open else date.min).toordinal(),
        ),
    )
