from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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


class IssueFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_no: int
    field: str
    label: str | None
    value_text: str
    value_number: Decimal | None
    unit: str | None
    source_text: str
    # Hard rule 4: every output says what kind of statement it is
    output_label: str = "verified fact (from the document)"


class RiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int | None
    page_no: int
    text: str
    origin: str
    category: str
    category_method: str | None
    output_label: str = "company claim (disclosed risk factor)"


class FigureOut(BaseModel):
    """A number as reported in the document."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    metric: str
    period: str
    basis: str
    value: Decimal
    unit: str
    page_no: int
    source_text: str
    output_label: str = "verified fact (from the document)"


class MetricOut(BaseModel):
    """A number calculated in Python from reported figures."""

    model_config = ConfigDict(from_attributes=True)

    metric: str
    period: str
    value: Decimal
    unit: str
    formula: str
    note: str | None
    input_figure_ids: list[int]
    input_pages: list[int] = []
    # Rounded half-up to 2 places in Python, for display; value keeps full precision
    value_display: Decimal | None = None
    output_label: str = "calculated metric"


class FinancialsOut(BaseModel):
    figures: list[FigureOut]
    metrics: list[MetricOut]


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AnswerOut(BaseModel):
    question: str
    answer: str
    pages: list[int]
    abstained: bool
    reason: str | None
    model: str | None
    # AI-written text, grounded in the cited pages; numbers checked against those pages
    output_label: str = "AI interpretation"
    disclaimer: str = "Research aid, not investment advice."


class CitedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: str
    unit: str | None
    document_id: int
    page_no: int
    label: str
    period: str | None = None


class DocumentRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: str
    filing_date: date | None


class IpoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company: str
    primary_document_id: int
    documents: list[DocumentRef]
    status: str
    bid_open: CitedOut | None
    bid_close: CitedOut | None
    price_band: CitedOut | None
    headline: dict[str, CitedOut]
    as_of: date
