from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any SQLAlchemy URL works; Postgres in Docker, SQLite for quick local runs.
    database_url: str = "postgresql+psycopg://smartfin:smartfin@localhost:5432/smartfin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
