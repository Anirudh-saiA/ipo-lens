"""calculated metrics document and period

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03 23:33:27.344270
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calculated_metrics", sa.Column("document_id", sa.BigInteger(), nullable=False))
    op.add_column("calculated_metrics", sa.Column("period", sa.Text(), nullable=False))
    op.add_column("calculated_metrics", sa.Column("unit", sa.Text(), nullable=False))
    op.add_column("calculated_metrics", sa.Column("note", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_calculated_metrics_document_id"),
        "calculated_metrics",
        ["document_id"],
        unique=False,
    )
    # Named as Postgres names it by default, so databases already migrated match
    op.create_foreign_key(
        "calculated_metrics_document_id_fkey",
        "calculated_metrics",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "calculated_metrics_document_id_fkey", "calculated_metrics", type_="foreignkey"
    )
    op.drop_index(op.f("ix_calculated_metrics_document_id"), table_name="calculated_metrics")
    op.drop_column("calculated_metrics", "note")
    op.drop_column("calculated_metrics", "unit")
    op.drop_column("calculated_metrics", "period")
    op.drop_column("calculated_metrics", "document_id")
