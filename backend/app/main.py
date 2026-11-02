from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine

DISCLAIMER = "Research aid, not investment advice."

app = FastAPI(title="IPO Lens API", version="0.1.0", description=DISCLAIMER)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
)


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    """Liveness plus a database check. Returns 503 when Postgres is unreachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if database == "ok" else "degraded", "database": database}
