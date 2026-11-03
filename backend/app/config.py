from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives in the repo root, one level above backend/
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    database_url: str = "postgresql+psycopg://ipolens:ipolens_dev@localhost:54329/ipolens"

    # Local models through Ollama (free). No paid API is wired; see app/models_ai.py.
    ollama_url: str = "http://localhost:11434"
    embed_model: str = "snowflake-arctic-embed:33m"  # Apache 2.0, 384 dimensions
    qa_model: str = "phi3.5"  # Microsoft Phi-3.5-mini, MIT


settings = Settings()
