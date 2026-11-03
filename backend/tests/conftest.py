from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings

# Tests run against <db>_test so migration tests never touch ingested documents.
# This must happen before app.db creates its engine.
_main_url = make_url(settings.database_url)
_test_url = _main_url.set(database=f"{_main_url.database}_test")
settings.database_url = _test_url.render_as_string(hide_password=False)


def _ensure_test_database() -> bool:
    try:
        admin = create_engine(_main_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": _test_url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{_test_url.database}"'))
        admin.dispose()
        return True
    except OperationalError:
        return False


DB_AVAILABLE = _ensure_test_database()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if DB_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="Postgres not reachable; run: docker compose up -d db")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3-page PDF: plain text, a ruled table, and an empty page."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table
    from reportlab.platypus.tables import TableStyle

    path = tmp_path_factory.mktemp("pdf") / "sample.pdf"
    styles = getSampleStyleSheet()
    table = Table(
        [
            ["Particulars", "FY2026", "FY2025"],
            ["Revenue from operations", "1,234.56", "987.65"],
            ["Restated profit for the year", "(12.34)", "45.67"],
        ]
    )
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story = [
        Paragraph("Sample Red Herring Prospectus", styles["Title"]),
        PageBreak(),
        Paragraph("Summary of restated financial information (in million)", styles["Normal"]),
        Spacer(1, 12),
        table,
        PageBreak(),
        Spacer(1, 1),
    ]
    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    return path


@pytest.fixture
def db_session() -> Iterator[Session]:
    from alembic import command
    from alembic.config import Config

    from app.db import engine
    from app.models import Base

    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")
    with Session(engine) as session:
        yield session
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
