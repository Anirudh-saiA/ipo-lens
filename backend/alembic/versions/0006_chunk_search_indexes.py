"""chunk search indexes

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Full-text search over chunk text (keyword half of hybrid retrieval)
    op.execute("CREATE INDEX ix_chunks_text_fts ON chunks USING gin (to_tsvector('english', text))")
    # Approximate nearest-neighbour search over embeddings (meaning half)
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_chunks_embedding_hnsw")
    op.execute("DROP INDEX ix_chunks_text_fts")
