from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives in the repo root, one level above backend/
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    database_url: str = "postgresql+psycopg://ipolens:ipolens_dev@localhost:54329/ipolens"


settings = Settings()
