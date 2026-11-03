"""issue facts and risk numbers

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04 00:33:38.804690
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issue_facts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("value_number", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_issue_facts_document_id"), "issue_facts", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_issue_facts_field"), "issue_facts", ["field"], unique=False)
    op.add_column("risks", sa.Column("number", sa.Integer(), nullable=True))
    op.add_column("risks", sa.Column("category_method", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("risks", "category_method")
    op.drop_column("risks", "number")
    op.drop_index(op.f("ix_issue_facts_field"), table_name="issue_facts")
    op.drop_index(op.f("ix_issue_facts_document_id"), table_name="issue_facts")
    op.drop_table("issue_facts")
