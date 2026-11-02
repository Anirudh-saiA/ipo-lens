from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# connect_timeout keeps /health from hanging when Postgres is down
engine = create_engine(
    settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
