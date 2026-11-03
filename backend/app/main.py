from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.models import (
    CalculatedMetric,
    Document,
    ExtractedFigure,
    IssueFact,
    Page,
    PageTable,
    Risk,
)
from app.schemas import (
    DocumentOut,
    FigureOut,
    FinancialsOut,
    IssueFactOut,
    MetricOut,
    PageOut,
    RiskOut,
    TableOut,
)

SessionDep = Annotated[Session, Depends(get_session)]

DISCLAIMER = "Research aid, not investment advice."

app = FastAPI(title="IPO Lens API", version="0.1.0", description=DISCLAIMER)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
)


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    """Liveness plus a database check. Returns 503 when Postgres is unreachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if database == "ok" else "degraded", "database": database}


@app.get("/documents")
def list_documents(session: SessionDep) -> list[DocumentOut]:
    documents = session.scalars(select(Document).order_by(Document.id))
    return [DocumentOut.model_validate(d) for d in documents]


@app.get("/documents/{document_id}")
def get_document(document_id: int, session: SessionDep) -> DocumentOut:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentOut.model_validate(document)


@app.get("/documents/{document_id}/pages/{page_no}")
def get_page(document_id: int, page_no: int, session: SessionDep) -> PageOut:
    """Text and tables of one page, as stored. page_no is 1-based."""
    page = session.scalar(
        select(Page).where(Page.document_id == document_id, Page.page_no == page_no)
    )
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    tables = session.scalars(
        select(PageTable)
        .where(PageTable.document_id == document_id, PageTable.page_no == page_no)
        .order_by(PageTable.table_index)
    )
    return PageOut(
        document_id=document_id,
        page_no=page_no,
        text=page.text,
        tables=[TableOut.model_validate(t) for t in tables],
    )


@app.get("/documents/{document_id}/issue")
def get_issue_facts(document_id: int, session: SessionDep) -> list[IssueFactOut]:
    """Offer structure, dates and use of proceeds, each with its page."""
    facts = session.scalars(
        select(IssueFact)
        .where(IssueFact.document_id == document_id)
        .order_by(IssueFact.page_no, IssueFact.id)
    )
    return [IssueFactOut.model_validate(f) for f in facts]


@app.get("/documents/{document_id}/risks")
def get_risks(document_id: int, session: SessionDep) -> list[RiskOut]:
    """Risk factors as disclosed, in document order, each with its page."""
    risks = session.scalars(
        select(Risk).where(Risk.document_id == document_id).order_by(Risk.number, Risk.id)
    )
    return [RiskOut.model_validate(r) for r in risks]


@app.get("/documents/{document_id}/financials")
def get_financials(document_id: int, session: SessionDep) -> FinancialsOut:
    """Reported figures (each with its page) and Python-calculated metrics (each with its
    formula and the pages of the figures it was computed from)."""
    figures = list(
        session.scalars(
            select(ExtractedFigure)
            .where(ExtractedFigure.document_id == document_id)
            .order_by(ExtractedFigure.page_no, ExtractedFigure.id)
        )
    )
    pages = {f.id: f.page_no for f in figures}
    metrics = []
    for m in session.scalars(
        select(CalculatedMetric)
        .where(CalculatedMetric.document_id == document_id)
        .order_by(CalculatedMetric.metric, CalculatedMetric.period)
    ):
        out = MetricOut.model_validate(m)
        out.input_pages = sorted({pages[i] for i in m.input_figure_ids if i in pages})
        out.value_display = m.value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        metrics.append(out)
    return FinancialsOut(figures=[FigureOut.model_validate(f) for f in figures], metrics=metrics)
