import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import engine


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


DB_AVAILABLE = _db_available()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if DB_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="Postgres not reachable; run: docker compose up -d db")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)
