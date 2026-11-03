"""Data model from CLAUDE.md.

Reported figures (extracted_figures) and calculated metrics (calculated_metrics) are
kept in separate tables. Every extracted figure, risk and chunk stores its source
document and page number.
"""

from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 384

DOC_TYPES = ("DRHP", "RHP", "addendum", "corrigendum", "prospectus")
BASES = ("restated_consolidated", "standalone", "other")
RISK_ORIGINS = ("disclosed", "ai")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint(_in("doc_type", DOC_TYPES), name="ck_documents_doc_type"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(String(20))
    filing_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    page_count: Mapped[int] = mapped_column(Integer)


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no", name="uq_pages_document_page"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class PageTable(Base):
    """A table as found on a page, stored cell by cell before any interpretation."""

    __tablename__ = "page_tables"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "page_no", "table_index", name="uq_page_tables_document_page_index"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_no: Mapped[int] = mapped_column(Integer)
    table_index: Mapped[int] = mapped_column(Integer)
    rows: Mapped[list[list[str | None]]] = mapped_column(JSONB)
    n_rows: Mapped[int] = mapped_column(Integer)
    n_cols: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float))
    extraction_method: Mapped[str] = mapped_column(Text)


class ExtractedFigure(Base):
    """A figure as reported in a document. Never computed."""

    __tablename__ = "extracted_figures"
    __table_args__ = (CheckConstraint(_in("basis", BASES), name="ck_extracted_figures_basis"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column(Integer)
    table_ref: Mapped[str | None] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text, index=True)
    period: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(32))
    value: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))


class CalculatedMetric(Base):
    """A value computed in Python from extracted_figures rows."""

    __tablename__ = "calculated_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    metric: Mapped[str] = mapped_column(Text, index=True)
    period: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text)
    formula: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    input_figure_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    value: Mapped[Decimal] = mapped_column(Numeric)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = (CheckConstraint(_in("origin", RISK_ORIGINS), name="ck_risks_origin"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16))


class Ipo(Base):
    __tablename__ = "ipos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company: Mapped[str] = mapped_column(Text)
    open_date: Mapped[date | None] = mapped_column(Date)
    close_date: Mapped[date | None] = mapped_column(Date)
    allotment_date: Mapped[date | None] = mapped_column(Date)
    listing_date: Mapped[date | None] = mapped_column(Date)
    price_band_low: Mapped[Decimal | None] = mapped_column(Numeric)
    price_band_high: Mapped[Decimal | None] = mapped_column(Numeric)
    lot_size: Mapped[int | None] = mapped_column(Integer)
    fresh_issue: Mapped[Decimal | None] = mapped_column(Numeric)
    ofs: Mapped[Decimal | None] = mapped_column(Numeric)
    issue_size: Mapped[Decimal | None] = mapped_column(Numeric)


class SubscriptionSnapshot(Base):
    __tablename__ = "subscription_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[str] = mapped_column(Text)
    times_subscribed: Mapped[Decimal] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(Text)


class GmpSnapshot(Base):
    """Grey market premium as reported. Unofficial; never predicted by IPO Lens."""

    __tablename__ = "gmp_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gmp_amount: Mapped[Decimal] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text, server_default="unofficial, as reported")


class Lockin(Base):
    __tablename__ = "lockins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="CASCADE"), index=True)
    holder_class: Mapped[str] = mapped_column(Text)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    expiry_date: Mapped[date] = mapped_column(Date)
    rule_reference: Mapped[str] = mapped_column(Text)
    source_page: Mapped[int | None] = mapped_column(Integer)


class DocDiff(Base):
    __tablename__ = "doc_diffs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(Text)
    drhp_value: Mapped[str | None] = mapped_column(Text)
    rhp_value: Mapped[str | None] = mapped_column(Text)
    drhp_page: Mapped[int | None] = mapped_column(Integer)
    rhp_page: Mapped[int | None] = mapped_column(Integer)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
