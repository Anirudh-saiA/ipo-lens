from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import engine
from app.models import Base

pytestmark = pytest.mark.db

BACKEND = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "documents",
    "pages",
    "extracted_figures",
    "calculated_metrics",
    "risks",
    "ipos",
    "subscription_snapshots",
    "gmp_snapshots",
    "lockins",
    "doc_diffs",
    "chunks",
}


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


def test_upgrade_downgrade_upgrade() -> None:
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert EXPECTED_TABLES.isdisjoint(inspect(engine).get_table_names())
    command.upgrade(cfg, "head")
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES


def test_migrations_match_models() -> None:
    command.upgrade(_alembic_config(), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_vector_extension_and_embedding_dim() -> None:
    command.upgrade(_alembic_config(), "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
        col_type = conn.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
            )
        ).scalar()
    assert col_type == "vector(384)"


def test_figures_require_source_page() -> None:
    """Hard rule 2: every extracted figure stores its document and page."""
    command.upgrade(_alembic_config(), "head")
    columns = {c["name"]: c for c in inspect(engine).get_columns("extracted_figures")}
    assert columns["document_id"]["nullable"] is False
    assert columns["page_no"]["nullable"] is False
