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
    metrics_projector_batch_size: int = 500
    queue_backlog_degraded_threshold: int = 100
    index_stale_after_seconds: float = 3600
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )

    # --- LLM / Embedding / Rerank providers (OpenAI-compatible) ---
    # Set llm_provider to "openai_compatible" (and fill base_url/api_key/model) to
    # replace the heuristic DocumentHeuristicCompiler with a real LLM compiler.
    # Leave provider as "none" to keep the current deterministic pipeline.
    llm_provider: str = "none"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    embedding_provider: str = "none"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    rerank_provider: str = "none"
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""

    def llm_enabled(self) -> bool:
        return self.llm_provider == "openai_compatible" and bool(
            self.llm_base_url and self.llm_model
        )

    def embedding_enabled(self) -> bool:
        return self.embedding_provider == "openai_compatible" and bool(
            self.embedding_base_url and self.embedding_model
        )

    def rerank_enabled(self) -> bool:
        return self.rerank_provider == "openai_compatible" and bool(
            self.rerank_base_url and self.rerank_model
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
