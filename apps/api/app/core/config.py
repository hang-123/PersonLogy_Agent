from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_prefix="PKS_",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    gel_dsn: str | None = None
    storage_backend: Literal["memory", "sqlite", "gel"] = "sqlite"
    sqlite_path: str = "../../data/personlogy.sqlite3"
    pdf_storage_root: str = "../../data/files"
    pdf_max_size_bytes: int = 25 * 1024 * 1024
    queue_backend: Literal["memory", "sqlite", "gel"] = "sqlite"
    queue_poll_interval_seconds: float = 2.0
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )

    def dependency_status(self) -> dict[str, str]:
        return {
            "gel": "configured" if self.gel_dsn else "not_configured",
            "storage": self.storage_backend,
            "queue": self.queue_backend,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
