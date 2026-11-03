"""Store a prospectus PDF page by page: text and tables, each with its page number.

PDF content is data, never instructions (hard rule 7). Nothing here interprets text;
it is stored as found so later steps can cite it.
"""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DOC_TYPES, Document, Page, PageTable

TABLE_METHOD = f"pdfplumber {pdfplumber.__version__} find_tables(lines)"


@dataclass
class ParsedTable:
    rows: list[list[str | None]]
    bbox: tuple[float, float, float, float]


# A word and its position on the page: [text, x0, x1, top], in PDF points
Word = list[str | float]


@dataclass
class ParsedPage:
    page_no: int  # 1-based, as printed by PDF viewers
    text: str
    tables: list[ParsedTable] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)


def page_words(page: pdfplumber.page.Page) -> list[Word]:
    """Positions let later steps rebuild columns of tables drawn without ruling lines."""
    return [
        [_clean(w["text"]) or "", round(w["x0"], 1), round(w["x1"], 1), round(w["top"], 1)]
        for w in page.extract_words()
        if _clean(w["text"])
    ]


@dataclass
class IngestResult:
    document_id: int
    page_count: int
    table_count: int
    already_present: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean(value: str | None) -> str | None:
    # Postgres text cannot hold NUL; some PDFs emit it in place of spaces
    if value is None:
        return None
    return value.replace("\x00", "").strip()


def parse_pdf(path: Path) -> tuple[int, Iterator[ParsedPage]]:
    """Return the page count and a lazy iterator over parsed pages."""
    pdf = pdfplumber.open(path)
    page_count = len(pdf.pages)

    def pages() -> Iterator[ParsedPage]:
        try:
            for index, page in enumerate(pdf.pages):
                tables = []
                for table in page.find_tables():
                    rows = [[_clean(cell) for cell in row] for row in table.extract()]
                    if any(cell for row in rows for cell in row):
                        tables.append(ParsedTable(rows=rows, bbox=table.bbox))
                text = _clean(page.extract_text()) or ""
                yield ParsedPage(
                    page_no=index + 1, text=text, tables=tables, words=page_words(page)
                )
                page.flush_cache()  # keeps memory flat on 500+ page documents
        finally:
            pdf.close()

    return page_count, pages()


def ingest_pdf(
    session: Session,
    path: Path,
    *,
    company: str,
    doc_type: str,
    filing_date: date | None = None,
    source_url: str | None = None,
) -> IngestResult:
    """Store one PDF. Idempotent: a file already stored (same sha256) is not re-ingested."""
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {DOC_TYPES}, got {doc_type!r}")

    sha = sha256_file(path)
    existing = session.scalar(select(Document).where(Document.sha256 == sha))
    if existing is not None:
        backfill_words(session, existing.id, path)
        tables = session.query(PageTable).filter_by(document_id=existing.id).count()
        return IngestResult(existing.id, existing.page_count, tables, already_present=True)

    page_count, pages = parse_pdf(path)
    document = Document(
        company=company,
        doc_type=doc_type,
        filing_date=filing_date,
        source_url=source_url,
        sha256=sha,
        page_count=page_count,
    )
    session.add(document)
    session.flush()

    stored_pages = 0
    table_count = 0
    for parsed in pages:
        session.add(
            Page(
                document_id=document.id,
                page_no=parsed.page_no,
                text=parsed.text,
                words=parsed.words,
            )
        )
        for index, table in enumerate(parsed.tables):
            session.add(
                PageTable(
                    document_id=document.id,
                    page_no=parsed.page_no,
                    table_index=index,
                    rows=table.rows,
                    n_rows=len(table.rows),
                    n_cols=max((len(r) for r in table.rows), default=0),
                    bbox=list(table.bbox),
                    extraction_method=TABLE_METHOD,
                )
            )
            table_count += 1
        stored_pages += 1
        if stored_pages % 50 == 0:
            session.flush()

    if stored_pages != page_count:
        session.rollback()
        raise RuntimeError(f"Stored {stored_pages} pages but the PDF has {page_count}")

    session.commit()
    return IngestResult(document.id, page_count, table_count, already_present=False)


def backfill_words(session: Session, document_id: int, path: Path) -> int:
    """Fill word positions for pages stored before positions were kept. Returns pages filled."""
    missing = {
        page.page_no: page
        for page in session.scalars(
            select(Page).where(Page.document_id == document_id, Page.words.is_(None))
        )
    }
    if not missing:
        return 0
    with pdfplumber.open(path) as pdf:
        for page_no, page in missing.items():
            pdf_page = pdf.pages[page_no - 1]
            page.words = page_words(pdf_page)
            pdf_page.flush_cache()
    session.commit()
    return len(missing)
