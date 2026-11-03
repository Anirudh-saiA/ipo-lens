"""Split each page into overlapping chunks and store them with local embeddings, so answers
can be grounded in specific pages. A chunk never spans two pages: every chunk keeps the
one page it came from."""

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Chunk, Page
from app.models_ai import Embedder

CHUNK_CHARS = 900
OVERLAP_CHARS = 150
MIN_PAGE_CHARS = 40  # skip blank and near-blank pages


def split_page(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Chunks of about `size` characters, broken at line ends where possible, with
    `overlap` characters repeated so a fact split across a boundary is in one chunk."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < MIN_PAGE_CHARS:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + size // 2, end)
            if newline != -1:
                end = newline
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def index_document(session: Session, document_id: int, embedder: Embedder, batch: int = 32) -> int:
    """Replace a document's chunks. Returns the number of chunks stored."""
    session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    pending: list[Chunk] = []
    stored = 0
    pages = session.scalars(
        select(Page).where(Page.document_id == document_id).order_by(Page.page_no)
    )

    def flush() -> None:
        nonlocal stored
        vectors = embedder.embed([c.text for c in pending], kind="document")
        for chunk, vector in zip(pending, vectors, strict=True):
            chunk.embedding = vector
            session.add(chunk)
        stored += len(pending)
        pending.clear()

    for page in pages:
        for text in split_page(page.text):
            pending.append(Chunk(document_id=document_id, page_no=page.page_no, text=text))
            if len(pending) >= batch:
                flush()
    if pending:
        flush()
    session.commit()
    return stored
