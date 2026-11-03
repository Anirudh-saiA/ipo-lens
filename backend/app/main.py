from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.models import Document, Page, PageTable
from app.schemas import DocumentOut, PageOut, TableOut

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
