"""initial data model

Revision ID: 0001
Revises:
Create Date: 2026-11-03 02:27:05.845972
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "calculated_metrics",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("input_figure_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_calculated_metrics_metric"), "calculated_metrics", ["metric"], unique=False
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "doc_type IN ('DRHP', 'RHP', 'addendum', 'corrigendum', 'prospectus')",
            name="ck_documents_doc_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_table(
        "ipos",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("open_date", sa.Date(), nullable=True),
        sa.Column("close_date", sa.Date(), nullable=True),
        sa.Column("allotment_date", sa.Date(), nullable=True),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("price_band_low", sa.Numeric(), nullable=True),
        sa.Column("price_band_high", sa.Numeric(), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("fresh_issue", sa.Numeric(), nullable=True),
        sa.Column("ofs", sa.Numeric(), nullable=True),
        sa.Column("issue_size", sa.Numeric(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_table(
        "doc_diffs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ipo_id", sa.BigInteger(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("drhp_value", sa.Text(), nullable=True),
        sa.Column("rhp_value", sa.Text(), nullable=True),
        sa.Column("drhp_page", sa.Integer(), nullable=True),
        sa.Column("rhp_page", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["ipo_id"], ["ipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_doc_diffs_ipo_id"), "doc_diffs", ["ipo_id"], unique=False)
    op.create_table(
        "extracted_figures",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("table_ref", sa.Text(), nullable=True),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.CheckConstraint(
            "basis IN ('restated_consolidated', 'standalone', 'other')",
            name="ck_extracted_figures_basis",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_extracted_figures_document_id"), "extracted_figures", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_extracted_figures_metric"), "extracted_figures", ["metric"], unique=False
    )
    op.create_table(
        "gmp_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ipo_id", sa.BigInteger(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gmp_amount", sa.Numeric(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), server_default="unofficial, as reported", nullable=False),
        sa.ForeignKeyConstraint(["ipo_id"], ["ipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gmp_snapshots_ipo_id"), "gmp_snapshots", ["ipo_id"], unique=False)
    op.create_table(
        "lockins",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ipo_id", sa.BigInteger(), nullable=False),
        sa.Column("holder_class", sa.Text(), nullable=False),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("rule_reference", sa.Text(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["ipo_id"], ["ipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lockins_ipo_id"), "lockins", ["ipo_id"], unique=False)
    op.create_table(
        "pages",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_no", name="uq_pages_document_page"),
    )
    op.create_table(
        "risks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.CheckConstraint("origin IN ('disclosed', 'ai')", name="ck_risks_origin"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risks_document_id"), "risks", ["document_id"], unique=False)
    op.create_table(
        "subscription_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ipo_id", sa.BigInteger(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("times_subscribed", sa.Numeric(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["ipo_id"], ["ipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subscription_snapshots_ipo_id"), "subscription_snapshots", ["ipo_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscription_snapshots_ipo_id"), table_name="subscription_snapshots")
    op.drop_table("subscription_snapshots")
    op.drop_index(op.f("ix_risks_document_id"), table_name="risks")
    op.drop_table("risks")
    op.drop_table("pages")
    op.drop_index(op.f("ix_lockins_ipo_id"), table_name="lockins")
    op.drop_table("lockins")
    op.drop_index(op.f("ix_gmp_snapshots_ipo_id"), table_name="gmp_snapshots")
    op.drop_table("gmp_snapshots")
    op.drop_index(op.f("ix_extracted_figures_metric"), table_name="extracted_figures")
    op.drop_index(op.f("ix_extracted_figures_document_id"), table_name="extracted_figures")
    op.drop_table("extracted_figures")
    op.drop_index(op.f("ix_doc_diffs_ipo_id"), table_name="doc_diffs")
    op.drop_table("doc_diffs")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("ipos")
    op.drop_table("documents")
    op.drop_index(op.f("ix_calculated_metrics_metric"), table_name="calculated_metrics")
    op.drop_table("calculated_metrics")
    op.execute("DROP EXTENSION IF EXISTS vector")
