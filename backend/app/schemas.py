from datetime import date

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    doc_type: str
    filing_date: date | None
    source_url: str | None
    sha256: str
    page_count: int


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    table_index: int
    rows: list[list[str | None]]
    n_rows: int
    n_cols: int
    extraction_method: str


class PageOut(BaseModel):
    document_id: int
    page_no: int
    text: str
    tables: list[TableOut]
